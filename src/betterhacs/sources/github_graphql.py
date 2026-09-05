"""Anreicherung über die GitHub-GraphQL-API.

Liefert die Felder, die im HACS-Datensatz fehlen und ohne die die Wartungsampel
nicht belastbar ist:

- ``isArchived``  das einzige harte Verwaisungs-Signal, fehlt in HACS komplett.
                  Der Hauptgrund für diesen Schritt.
- ``latestRelease.publishedAt`` HACS liefert die Versionsnummer, aber kein Datum.
                  Erst damit ist "committet, aber seit zwei Jahren kein Release"
                  von "seit zwei Jahren tot" zu unterscheiden.
- ``pushedAt``    als Kontrollwert. Ursprünglich war das der Hauptgrund, weil der
                  Entwurf annahm, HACS' ``last_updated`` sei GitHubs ``updated_at``.
                  Eine Stichprobe gegen die API hat das widerlegt: HACS liefert dort
                  bereits exakt ``pushed_at``. Der Wert bleibt als Wächter stehen —
                  weicht er künftig ab, hat sich an der Quelle etwas geändert.
- Nebenbei Lizenz, Fork-Zahl, Sprache, und ob GitHub das Repo überhaupt noch kennt.

Kosten: rund 45 Abfragen für alle ~4.200 Repos, weil sich pro Abfrage 100 Repositories
als benannte Felder abfragen lassen. Das ist der Grund, warum hier GraphQL statt REST
steht — über REST wären es 4.200 einzelne Requests.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from ..config import GITHUB_GRAPHQL_URL, USER_AGENT
from .fetch import SourceError

log = logging.getLogger(__name__)

BATCH = 100
MAX_RETRIES = 4

FRAGMENT = """
fragment repoFields on Repository {
  databaseId
  nameWithOwner
  pushedAt
  isArchived
  isFork
  isDisabled
  forkCount
  homepageUrl
  primaryLanguage { name }
  licenseInfo { key }
  latestRelease { publishedAt tagName }
}
"""


@dataclass
class GithubRepo:
    repo_id: int | None
    name_with_owner: str | None
    pushed_at: datetime | None
    released_at: datetime | None
    latest_tag: str | None
    is_archived: bool | None
    is_fork: bool | None
    is_disabled: bool | None
    license_key: str | None
    fork_count: int | None
    primary_language: str | None
    homepage: str | None
    unavailable: str | None = None


@dataclass
class EnrichReport:
    requested: int = 0
    resolved: int = 0
    unavailable: int = 0
    renamed: int = 0
    queries: int = 0
    rate_limit_remaining: int | None = None
    errors: list[str] = field(default_factory=list)


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_query(pairs: list[tuple[str, str]]) -> str:
    """Baut eine Abfrage mit einem benannten Feld je Repository.

    Die Aliase sind r0..r99 und werden über den Index der Eingabeliste
    wieder zugeordnet — der Name allein taugt nicht, weil GitHub bei einem
    umbenannten Repo den neuen Namen zurückgibt.
    """
    parts = []
    for i, (owner, name) in enumerate(pairs):
        owner_q = owner.replace('"', '\\"')
        name_q = name.replace('"', '\\"')
        parts.append(f'  r{i}: repository(owner: "{owner_q}", name: "{name_q}") {{ ...repoFields }}')
    return FRAGMENT + "\nquery {\n" + "\n".join(parts) + "\n  rateLimit { remaining resetAt cost }\n}\n"


def _post(client: httpx.Client, query: str) -> dict:
    """Eine Abfrage mit Wiederholung. GraphQL beantwortet auch Teilfehler mit HTTP 200,
    deshalb wird der Rumpf und nicht nur der Statuscode geprüft."""
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(GITHUB_GRAPHQL_URL, json={"query": query})
        except httpx.HTTPError as exc:
            if attempt == MAX_RETRIES - 1:
                raise SourceError(f"GraphQL nicht erreichbar: {exc}") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 401:
            raise SourceError(
                "GitHub lehnt das Token ab (401). GITHUB_TOKEN in .env prüfen — "
                "ein Token ganz ohne Scopes reicht."
            )
        # Sekundäres Rate-Limit oder Serverfehler: warten, nicht aufgeben.
        if resp.status_code in (403, 429, 502, 503):
            wait = float(resp.headers.get("retry-after", delay))
            log.warning("HTTP %s von GitHub, warte %.0fs", resp.status_code, wait)
            time.sleep(wait)
            delay *= 2
            continue
        if resp.status_code != 200:
            raise SourceError(f"GraphQL antwortete mit HTTP {resp.status_code}: {resp.text[:200]}")

        body = resp.json()
        # Fehler, die alle Felder betreffen (z.B. Query zu teuer), stehen ohne "data" da.
        if body.get("data") is None and body.get("errors"):
            msg = body["errors"][0].get("message", "")
            if "rate limit" in msg.lower():
                log.warning("GraphQL-Ratenlimit erreicht, warte 60s")
                time.sleep(60)
                delay *= 2
                continue
            raise SourceError(f"GraphQL-Fehler: {msg}")
        return body

    raise SourceError("GraphQL nach mehreren Versuchen nicht erfolgreich")


def enrich(
    repos: list[tuple[int, str]],
    token: str,
    *,
    batch_size: int = BATCH,
    progress=None,
) -> tuple[list[GithubRepo], EnrichReport]:
    """repos: Liste aus (hacs_repo_id, "owner/name")."""
    report = EnrichReport(requested=len(repos))
    out: list[GithubRepo] = []

    client = httpx.Client(
        timeout=90.0,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        for start in range(0, len(repos), batch_size):
            chunk = repos[start : start + batch_size]
            pairs = []
            valid = []
            for rid, full_name in chunk:
                if "/" not in full_name:
                    continue
                owner, _, name = full_name.partition("/")
                pairs.append((owner, name))
                valid.append((rid, full_name))
            if not pairs:
                continue

            body = _post(client, _build_query(pairs))
            report.queries += 1
            data = body.get("data") or {}
            rl = data.get("rateLimit") or {}
            if rl.get("remaining") is not None:
                report.rate_limit_remaining = rl["remaining"]

            for i, (rid, full_name) in enumerate(valid):
                node = data.get(f"r{i}")
                if node is None:
                    # GitHub kennt das Repo nicht mehr: geloescht, privat oder umbenannt.
                    # Das ist eine Information, kein Fehler — sie wird festgehalten.
                    out.append(
                        GithubRepo(
                            repo_id=rid,
                            name_with_owner=full_name,
                            pushed_at=None,
                            released_at=None,
                            latest_tag=None,
                            is_archived=None,
                            is_fork=None,
                            is_disabled=None,
                            license_key=None,
                            fork_count=None,
                            primary_language=None,
                            homepage=None,
                            unavailable="not_found",
                        )
                    )
                    report.unavailable += 1
                    continue

                rel = node.get("latestRelease") or {}
                lic = node.get("licenseInfo") or {}
                lang = node.get("primaryLanguage") or {}
                got_name = node.get("nameWithOwner")
                if got_name and got_name.lower() != full_name.lower():
                    report.renamed += 1

                out.append(
                    GithubRepo(
                        repo_id=rid,
                        name_with_owner=got_name,
                        pushed_at=_dt(node.get("pushedAt")),
                        released_at=_dt(rel.get("publishedAt")),
                        latest_tag=rel.get("tagName"),
                        is_archived=node.get("isArchived"),
                        is_fork=node.get("isFork"),
                        is_disabled=node.get("isDisabled"),
                        license_key=lic.get("key"),
                        fork_count=node.get("forkCount"),
                        primary_language=lang.get("name"),
                        homepage=node.get("homepageUrl"),
                    )
                )
                report.resolved += 1

            if progress:
                progress(min(start + batch_size, len(repos)), len(repos))

            # Teilfehler betreffen einzelne Felder und sind normal (geloeschte Repos).
            for err in body.get("errors", [])[:3]:
                msg = err.get("message", "")
                if "Could not resolve" not in msg and "NOT_FOUND" not in str(err.get("type", "")):
                    report.errors.append(msg[:200])
    finally:
        client.close()

    log.info(
        "Anreicherung: %d von %d aufgelöst, %d nicht mehr erreichbar, %d umbenannt, "
        "%d Abfragen, Restkontingent %s",
        report.resolved,
        report.requested,
        report.unavailable,
        report.renamed,
        report.queries,
        report.rate_limit_remaining,
    )
    return out, report
