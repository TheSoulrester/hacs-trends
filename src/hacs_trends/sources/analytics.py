"""Home Assistant analytics: installations actually running, per integration domain.

https://analytics.home-assistant.io/custom_integrations.json

The most honest adoption figure publicly available - far more meaningful than the
download counter of release assets. Three limits that travel with it everywhere and
have to be named in the UI:

1. An opt-in sample. Good for rankings, not an absolute truth.
2. Integrations only. Plugins, themes and templates do not appear.
3. The key is the integration domain, not the repository. Several HACS repositories
   can claim the same domain (forks, successor projects) - then the figure cannot be
   attributed and is marked ambiguous instead of guessed.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..config import HA_ANALYTICS_URL
from .fetch import Fetcher, SourceError

log = logging.getLogger(__name__)


@dataclass
class AnalyticsEntry:
    domain: str
    total: int
    versions: dict[str, int] = field(default_factory=dict)


@dataclass
class AnalyticsReport:
    domains_in_source: int = 0
    repos_with_domain: int = 0
    matched: int = 0
    ambiguous_domains: int = 0
    ambiguous_repos: int = 0
    unmatched_repos: int = 0
    source_domains_without_repo: int = 0

    @property
    def match_rate(self) -> float:
        return self.matched / self.repos_with_domain if self.repos_with_domain else 0.0


def fetch_analytics(fetcher: Fetcher) -> dict[str, AnalyticsEntry]:
    result = fetcher.get_json(HA_ANALYTICS_URL, fixture_name="ha_analytics.json")
    data = result.data
    if not isinstance(data, dict):
        raise SourceError("custom_integrations.json: expected an object")

    out: dict[str, AnalyticsEntry] = {}
    for domain, raw in data.items():
        if not isinstance(raw, dict) or "total" not in raw:
            continue
        versions = raw.get("versions")
        out[domain] = AnalyticsEntry(
            domain=domain,
            total=int(raw["total"]),
            versions={str(k): int(v) for k, v in versions.items()}
            if isinstance(versions, dict)
            else {},
        )
    log.info("Analytics: %d domains", len(out))
    return out


def map_repos_to_domains(repos, analytics: dict[str, AnalyticsEntry]):
    """Match repositories to their analytics data.

    Returns {repo_id: (domain, ambiguous)} and a report. 'ambiguous' means several HACS
    repositories claim the same domain. The figure is still shown, but marked as not
    attributable - silently giving it to one of them would be a false statement.
    """
    claims: dict[str, list[int]] = defaultdict(list)
    for repo in repos:
        if repo.domain:
            claims[repo.domain].append(repo.id)

    counts = Counter({d: len(ids) for d, ids in claims.items()})
    ambiguous = {d for d, n in counts.items() if n > 1}

    mapping: dict[int, tuple[str, bool]] = {}
    matched = 0
    for domain, repo_ids in claims.items():
        if domain not in analytics:
            continue
        matched += len(repo_ids)
        for rid in repo_ids:
            mapping[rid] = (domain, domain in ambiguous)

    report = AnalyticsReport(
        domains_in_source=len(analytics),
        repos_with_domain=sum(len(v) for v in claims.values()),
        matched=matched,
        ambiguous_domains=len(ambiguous),
        ambiguous_repos=sum(len(claims[d]) for d in ambiguous),
        unmatched_repos=sum(len(v) for d, v in claims.items() if d not in analytics),
        source_domains_without_repo=len(set(analytics) - set(claims)),
    )
    log.info(
        "Analytics matching: %d/%d repos matched (%.1f%%), %d ambiguous domains",
        report.matched,
        report.repos_with_domain,
        report.match_rate * 100,
        report.ambiguous_domains,
    )
    return mapping, report
