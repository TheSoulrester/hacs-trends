"""Home-Assistant-Analytik: tatsächlich laufende Installationen je Integrations-Domain.

https://analytics.home-assistant.io/custom_integrations.json

Das ist die ehrlichste Verbreitungszahl, die öffentlich verfügbar ist — deutlich
aussagekräftiger als der Download-Zähler der Release-Assets. Drei Einschränkungen,
die überall mitgeführt und im UI benannt werden müssen:

1. Opt-in-Stichprobe. Gut für Rangfolgen, keine Absolutwahrheit.
2. Nur Integrationen. Plugins, Themes, Templates tauchen nicht auf.
3. Der Schlüssel ist die Integrations-Domain, nicht das Repository. Mehrere HACS-Repos
   können dieselbe Domain beanspruchen (Forks, Nachfolgeprojekte) — dann ist die Zahl
   nicht eindeutig zuordenbar und wird als mehrdeutig markiert statt geraten.
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
        raise SourceError("custom_integrations.json: erwartet wurde ein Objekt")

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
    log.info("Analytics: %d Domains", len(out))
    return out


def map_repos_to_domains(repos, analytics: dict[str, AnalyticsEntry]):
    """Ordnet Repos ihren Analytics-Daten zu.

    Gibt zurück: {repo_id: (domain, ambiguous)} und einen Bericht.
    'ambiguous' heißt: mehrere HACS-Repos beanspruchen dieselbe Domain. Die Zahl wird
    dann zwar angezeigt, aber als nicht eindeutig gekennzeichnet — sie stillschweigend
    einem der Repos zuzuschlagen wäre eine Falschaussage.
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
        "Analytics-Zuordnung: %d/%d Repos getroffen (%.1f%%), %d mehrdeutige Domains",
        report.matched,
        report.repos_with_domain,
        report.match_rate * 100,
        report.ambiguous_domains,
    )
    return mapping, report
