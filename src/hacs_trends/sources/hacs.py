"""Primary source: the dataset HACS publishes itself.

https://data-v2.hacs.xyz/<category>/data.json

One request per category covers every repository - so this part needs neither a
token nor rate-limit handling. The endpoint is an internal HACS format without any
guarantee, though (v1 -> v2 has happened before), so it is validated strictly here and
the run stops when the format breaks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..config import CATEGORIES, HACS_DATA_BASE, HACS_DEFAULT_BASE, SCHEMA_CATEGORIES
from .fetch import Fetcher, SourceError

log = logging.getLogger(__name__)

# Fields HACS guarantees for every category. If they are missing, something is wrong.
REQUIRED = ("full_name", "last_fetched")

# Topics HACS filters out itself - they say nothing about the project.
TOPIC_FILTER = {"home-assistant", "homeassistant", "hacs", "home-automation", "hass"}


@dataclass
class HacsRepo:
    id: int
    category: str
    full_name: str
    description: str | None
    manifest_name: str | None
    domain: str | None
    topics: list[str]
    country: str | None
    stars: int | None
    downloads: int | None
    open_issues: int | None
    last_updated: datetime | None
    last_version: str | None
    last_commit: str | None


@dataclass
class HacsFetchReport:
    """What the run actually saw. Goes into sync_runs.counts and makes silent
    regressions visible."""

    per_category: dict[str, int] = field(default_factory=dict)
    not_modified: list[str] = field(default_factory=list)
    skipped_invalid: dict[str, int] = field(default_factory=dict)
    removed: int = 0
    critical: int = 0

    @property
    def total(self) -> int:
        return sum(self.per_category.values())


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_repo(repo_id: str, raw: dict, category: str) -> HacsRepo | None:
    if not all(k in raw for k in REQUIRED):
        return None
    try:
        rid = int(repo_id)
    except (TypeError, ValueError):
        return None

    manifest = raw.get("manifest") or {}
    country = manifest.get("country")
    if isinstance(country, list):
        country = ",".join(country) if country else None
    elif not isinstance(country, str):
        country = None

    return HacsRepo(
        id=rid,
        category=category,
        full_name=raw["full_name"],
        description=raw.get("description"),
        manifest_name=raw.get("manifest_name") or manifest.get("name"),
        domain=raw.get("domain"),
        topics=[t for t in (raw.get("topics") or []) if t not in TOPIC_FILTER],
        country=country,
        stars=raw.get("stargazers_count"),
        downloads=raw.get("downloads"),
        open_issues=raw.get("open_issues"),
        last_updated=_parse_dt(raw.get("last_updated")),
        last_version=raw.get("last_version"),
        last_commit=raw.get("last_commit"),
    )


def fetch_categories(
    fetcher: Fetcher, etags: dict[str, str] | None = None
) -> tuple[list[HacsRepo], HacsFetchReport, dict[str, str]]:
    """Read all categories. Returns the repositories, a report and the new ETags."""
    etags = etags or {}
    new_etags: dict[str, str] = {}
    repos: list[HacsRepo] = []
    report = HacsFetchReport()

    for category in CATEGORIES:
        key = f"hacs:{category}"
        url = f"{HACS_DATA_BASE}/{category}/data.json"
        result = fetcher.get_json(url, fixture_name=f"{category}.json", etag=etags.get(key))

        if result.not_modified:
            report.not_modified.append(category)
            log.info("%s unchanged (304)", category)
            continue
        if result.etag:
            new_etags[key] = result.etag

        payload = result.data
        if not isinstance(payload, dict):
            raise SourceError(
                f"{url}: expected an object keyed by repository ID, "
                f"got: {type(payload).__name__}. The format has probably changed."
            )

        invalid = 0
        for repo_id, raw in payload.items():
            if not isinstance(raw, dict):
                invalid += 1
                continue
            parsed = _parse_repo(repo_id, raw, category)
            if parsed is None:
                invalid += 1
                continue
            repos.append(parsed)

        count = len(payload) - invalid
        report.per_category[category] = count
        if invalid:
            report.skipped_invalid[category] = invalid

        # A schema break shows up here: when a category with a schema is suddenly
        # mostly unreadable, the format is no longer what it was.
        if category in SCHEMA_CATEGORIES and payload and invalid > len(payload) * 0.1:
            raise SourceError(
                f"{url}: {invalid} of {len(payload)} entries unreadable. "
                "The HACS data format has probably changed - sync stopped so that no "
                "half-written data ends up in the database."
            )

        log.info("%-14s %5d repos (%d unreadable)", category, count, invalid)

    return repos, report, new_etags


def fetch_removed(fetcher: Fetcher) -> list[dict]:
    """Repositories HACS removed from the store - with reason and type.
    The strongest 'stop using this' signal there is."""
    result = fetcher.get_json(
        f"{HACS_DATA_BASE}/removed/data.json", fixture_name="removed.json"
    )
    data = result.data or []
    if not isinstance(data, list):
        raise SourceError("removed/data.json: expected a list")
    return [r for r in data if isinstance(r, dict) and r.get("repository")]


def fetch_critical(fetcher: Fetcher) -> list[dict]:
    """Repositories with critical security problems."""
    result = fetcher.get_json(
        f"{HACS_DATA_BASE}/critical/data.json", fixture_name="critical.json"
    )
    data = result.data or []
    if not isinstance(data, list):
        raise SourceError("critical/data.json: expected a list")
    return [r for r in data if isinstance(r, dict) and r.get("repository")]


def fetch_default_lists(fetcher: Fetcher) -> dict[str, list[str]]:
    """The official category lists from hacs/default.

    Used only for the cross-check: anything listed here without a dataset entry is a
    gap in the HACS data pipeline. Without this check, an outage of the data generation
    would look like real repositories disappearing.
    """
    out: dict[str, list[str]] = {}
    for category in CATEGORIES:
        result = fetcher.get_json(
            f"{HACS_DEFAULT_BASE}/{category}",
            fixture_name=f"default_{category}.json",
        )
        if isinstance(result.data, list):
            out[category] = [x for x in result.data if isinstance(x, str)]
    return out
