"""Enrichment over GitHub's GraphQL API.

Supplies what the HACS dataset does not carry: whether a repository is archived,
when it last published a release, how often it releases, how much it is committed
to, and the issue balance.

Two things measured rather than assumed, both of which would have produced silently
wrong data:

* ``releases(last: N)`` returns the OLDEST releases. GitHub's default ordering for
  the connection is descending by creation, so ``last`` takes the tail. Checked on
  robinostlund/homeassistant-volkswagencarnet: without an explicit ``orderBy`` the
  three "latest" releases came back as v4.4.5-v4.4.7 from June 2020, while the real
  newest is v5.5.1 from August 2026. Every query here orders explicitly.
* A batch of 100 repositories with releases and two commit histories makes GitHub
  answer 502. Fifty works and costs ONE rate-limit point per query, so the whole
  corpus costs about 84 points of the 5,000 per hour - measured, not estimated.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from ..config import GITHUB_GRAPHQL_URL, USER_AGENT
from .fetch import SourceError

log = logging.getLogger(__name__)

# 100 per query makes GitHub return 502 once releases and commit histories are in it.
BATCH = 50
MAX_RETRIES = 4
# Enough to characterise the rhythm without inflating node count.
RELEASE_NODES = 30

FRAGMENT = """
fragment repoFields on Repository {
  databaseId
  nameWithOwner
  createdAt
  pushedAt
  isArchived
  isFork
  isDisabled
  forkCount
  homepageUrl
  watchers { totalCount }
  primaryLanguage { name }
  licenseInfo { key }
  openIssues: issues(states: OPEN) { totalCount }
  closedIssues: issues(states: CLOSED) { totalCount }
  releases(first: %d, orderBy: {field: CREATED_AT, direction: DESC}) {
    totalCount
    nodes { publishedAt tagName isPrerelease }
  }
  defaultBranchRef {
    target {
      ... on Commit {
        year: history(since: "%%(year)s") { totalCount }
        quarter: history(since: "%%(quarter)s") { totalCount }
      }
    }
  }
}
""" % RELEASE_NODES


@dataclass
class GithubRepo:
    repo_id: int | None
    name_with_owner: str | None = None
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    released_at: datetime | None = None
    latest_tag: str | None = None
    releases_total: int | None = None
    releases_year: int | None = None
    releases_quarter: int | None = None
    uses_prerelease: bool | None = None
    commits_year: int | None = None
    commits_quarter: int | None = None
    is_archived: bool | None = None
    is_fork: bool | None = None
    is_disabled: bool | None = None
    license_key: str | None = None
    fork_count: int | None = None
    watchers: int | None = None
    open_issues_gh: int | None = None
    closed_issues: int | None = None
    primary_language: str | None = None
    homepage: str | None = None
    unavailable: str | None = None


@dataclass
class EnrichReport:
    requested: int = 0
    resolved: int = 0
    unavailable: int = 0
    renamed: int = 0
    queries: int = 0
    cost: int = 0
    rate_limit_remaining: int | None = None
    errors: list[str] = field(default_factory=list)


def _dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_query(pairs, now: datetime) -> str:
    frag = FRAGMENT % {
        "year": (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quarter": (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    parts = []
    for i, (owner, name) in enumerate(pairs):
        o = owner.replace("\\", "\\\\").replace('"', '\\"')
        n = name.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'  r{i}: repository(owner: "{o}", name: "{n}") {{ ...repoFields }}')
    return frag + "\nquery {\n" + "\n".join(parts) + "\n  rateLimit { cost remaining }\n}\n"


def _post(client: httpx.Client, query: str) -> dict:
    delay = 3.0
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.post(GITHUB_GRAPHQL_URL, json={"query": query})
        except httpx.HTTPError as exc:
            if attempt == MAX_RETRIES - 1:
                raise SourceError(f"GraphQL unreachable: {exc}") from exc
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 401:
            raise SourceError(
                "GitHub rejected the token (401). It was probably revoked or expired."
            )
        if resp.status_code in (403, 429, 502, 503, 504):
            wait = float(resp.headers.get("retry-after", delay))
            log.warning("HTTP %s from GitHub, waiting %.0fs", resp.status_code, wait)
            time.sleep(wait)
            delay *= 2
            continue
        if resp.status_code != 200:
            raise SourceError(f"GraphQL returned HTTP {resp.status_code}: {resp.text[:200]}")

        body = resp.json()
        if body.get("data") is None and body.get("errors"):
            msg = body["errors"][0].get("message", "")
            if "rate limit" in msg.lower():
                log.warning("GraphQL rate limit reached, waiting 60s")
                time.sleep(60)
                delay *= 2
                continue
            raise SourceError(f"GraphQL error: {msg}")
        return body

    raise SourceError("GraphQL did not succeed after several attempts")


def _parse(node: dict, repo_id: int, full_name: str, now: datetime) -> GithubRepo:
    rel = node.get("releases") or {}
    nodes = [n for n in (rel.get("nodes") or []) if n and n.get("publishedAt")]
    dates = sorted((_dt(n["publishedAt"]) for n in nodes), reverse=True)

    year_cut = now - timedelta(days=365)
    quarter_cut = now - timedelta(days=90)
    # A floor, not an exact count: if all RELEASE_NODES fall inside the year the true
    # number is higher. Fine for ranking rhythm, and never presented as exact.
    releases_year = sum(1 for d in dates if d >= year_cut)
    releases_quarter = sum(1 for d in dates if d >= quarter_cut)

    target = (node.get("defaultBranchRef") or {}).get("target") or {}
    lic = node.get("licenseInfo") or {}
    lang = node.get("primaryLanguage") or {}

    return GithubRepo(
        repo_id=repo_id,
        name_with_owner=node.get("nameWithOwner"),
        created_at=_dt(node.get("createdAt")),
        pushed_at=_dt(node.get("pushedAt")),
        released_at=dates[0] if dates else None,
        latest_tag=nodes[0].get("tagName") if nodes else None,
        releases_total=rel.get("totalCount"),
        releases_year=releases_year,
        releases_quarter=releases_quarter,
        uses_prerelease=any(n.get("isPrerelease") for n in nodes) if nodes else None,
        commits_year=(target.get("year") or {}).get("totalCount"),
        commits_quarter=(target.get("quarter") or {}).get("totalCount"),
        is_archived=node.get("isArchived"),
        is_fork=node.get("isFork"),
        is_disabled=node.get("isDisabled"),
        license_key=lic.get("key"),
        fork_count=node.get("forkCount"),
        watchers=(node.get("watchers") or {}).get("totalCount"),
        open_issues_gh=(node.get("openIssues") or {}).get("totalCount"),
        closed_issues=(node.get("closedIssues") or {}).get("totalCount"),
        primary_language=lang.get("name"),
        homepage=node.get("homepageUrl"),
    )


def enrich(repos, token: str, *, batch_size: int = BATCH, progress=None):
    """repos: list of (hacs_repo_id, "owner/name")."""
    report = EnrichReport(requested=len(repos))
    out: list[GithubRepo] = []
    now = datetime.now(timezone.utc)

    client = httpx.Client(
        timeout=120.0,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        for start in range(0, len(repos), batch_size):
            chunk = repos[start : start + batch_size]
            pairs, valid = [], []
            for rid, full_name in chunk:
                if "/" not in full_name:
                    continue
                owner, _, name = full_name.partition("/")
                pairs.append((owner, name))
                valid.append((rid, full_name))
            if not pairs:
                continue

            try:
                body = _post(client, _build_query(pairs, now))
            except SourceError as exc:
                # A batch can be too heavy for GitHub to answer in time - repositories
                # with tens of thousands of issues make the whole query time out at 504.
                # Halving until it goes through costs a few extra queries and saves the
                # run; a single repository that still fails is recorded and skipped.
                if len(valid) == 1:
                    log.error("%s could not be enriched: %s", valid[0][1], exc)
                    report.errors.append(f"{valid[0][1]}: {str(exc)[:120]}")
                    out.append(
                        GithubRepo(repo_id=valid[0][0], name_with_owner=valid[0][1],
                                   unavailable="query_failed")
                    )
                    report.unavailable += 1
                    continue
                mid = len(valid) // 2
                log.warning("Batch of %d failed (%s) - splitting", len(valid),
                            str(exc)[:80])
                for half in (valid[:mid], valid[mid:]):
                    sub, sub_report = enrich(half, token, batch_size=len(half))
                    out.extend(sub)
                    report.resolved += sub_report.resolved
                    report.unavailable += sub_report.unavailable
                    report.renamed += sub_report.renamed
                    report.queries += sub_report.queries
                    report.cost += sub_report.cost
                    report.errors.extend(sub_report.errors)
                    if sub_report.rate_limit_remaining is not None:
                        report.rate_limit_remaining = sub_report.rate_limit_remaining
                if progress:
                    progress(min(start + batch_size, len(repos)), len(repos))
                continue

            report.queries += 1
            data = body.get("data") or {}
            rl = data.get("rateLimit") or {}
            report.cost += rl.get("cost") or 0
            if rl.get("remaining") is not None:
                report.rate_limit_remaining = rl["remaining"]

            for i, (rid, full_name) in enumerate(valid):
                node = data.get(f"r{i}")
                if node is None:
                    # Deleted, renamed away, or made private. A fact, not a failure.
                    out.append(
                        GithubRepo(repo_id=rid, name_with_owner=full_name, unavailable="not_found")
                    )
                    report.unavailable += 1
                    continue
                parsed = _parse(node, rid, full_name, now)
                if parsed.name_with_owner and parsed.name_with_owner.lower() != full_name.lower():
                    report.renamed += 1
                out.append(parsed)
                report.resolved += 1

            if progress:
                progress(min(start + batch_size, len(repos)), len(repos))
    finally:
        client.close()

    log.info(
        "Enrichment: %d of %d resolved, %d gone, %d renamed, %d queries, %d points spent, "
        "%s remaining",
        report.resolved, report.requested, report.unavailable, report.renamed,
        report.queries, report.cost, report.rate_limit_remaining,
    )
    return out, report
