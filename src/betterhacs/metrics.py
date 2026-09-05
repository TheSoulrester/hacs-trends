"""Kennzahlen aus den Snapshots: Delta-Werte und Wartungszustand.

Zwei Regeln, die den Rest der Datei erklären:

1. Ein fehlender Wert ist NULL, nie 0. Gibt es keinen ausreichend alten Snapshot,
   ist das Delta unbekannt — und "unbekannt" als "keine Veränderung" darzustellen
   würde jede Sortierung verfälschen.
2. Referenztage werden global gewählt, nicht je Repo. Ein Sync schreibt immer alle
   Repos gemeinsam, also ist derselbe Stichtag für alle korrekt und um Größenordnungen
   schneller als eine Suche je Repo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from .db import InstallSnapshot, RepoGithub, Snapshot

log = logging.getLogger(__name__)

# Wie weit der tatsächliche Stichtag vom gewünschten abweichen darf.
# Ein ausgefallener Lauf soll die Spalte nicht leeren, ein zwei Wochen alter
# Ersatzwert sie aber auch nicht verfälschen.
TOLERANCE = {7: 2, 30: 4}

# Ab wie vielen Sternen ein prozentualer Zuwachs überhaupt aussagekräftig ist.
# Bei einem Median von 13 Sternen würde eine Sortierung nach Prozent sonst
# ausschließlich Repos zeigen, die von 2 auf 4 Sterne gestiegen sind.
MIN_BASE_FOR_PERCENT = 25


@dataclass
class HealthThresholds:
    """Grenzen für die Wartungsampel, in Tagen seit dem letzten Commit.

    Die Voreinstellung stammt aus der gemessenen Verteilung über alle 4.193 Repos
    (Median 55 Tage, P75 208, P90 689) und nicht aus dem Bauchgefühl.
    """

    active: int = 90
    quiet: int = 365
    stale: int = 730


@dataclass
class Deltas:
    d7: int | None = None
    d30: int | None = None
    p7: float | None = None
    p30: float | None = None


def _pick_reference_day(available: list[date], today: date, days: int) -> date | None:
    """Der verfügbare Snapshot-Tag, der dem Wunschstichtag am nächsten liegt."""
    target = today - timedelta(days=days)
    tol = TOLERANCE.get(days, 3)
    candidates = [d for d in available if abs((d - target).days) <= tol]
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - target).days))


def snapshot_days(session) -> list[date]:
    return list(session.scalars(select(Snapshot.day).distinct().order_by(Snapshot.day)))


def compute_star_deltas(session, today: date) -> tuple[dict[int, Deltas], dict[int, date | None]]:
    """Stern-Deltas für alle Repos, gegen die global gewählten Referenztage."""
    days = snapshot_days(session)
    refs = {n: _pick_reference_day(days, today, n) for n in (7, 30)}
    log.info("Referenztage für Stern-Deltas: %s", {k: str(v) for k, v in refs.items()})

    current = {
        rid: stars
        for rid, stars in session.execute(
            select(Snapshot.repo_id, Snapshot.stars).where(Snapshot.day == today)
        )
    }

    out: dict[int, Deltas] = {rid: Deltas() for rid in current}
    for n, ref_day in refs.items():
        if ref_day is None or ref_day == today:
            continue
        past = {
            rid: stars
            for rid, stars in session.execute(
                select(Snapshot.repo_id, Snapshot.stars).where(Snapshot.day == ref_day)
            )
        }
        for rid, now_val in current.items():
            then = past.get(rid)
            if now_val is None or then is None:
                continue
            diff = now_val - then
            pct = (diff / then * 100) if then >= MIN_BASE_FOR_PERCENT and then > 0 else None
            if n == 7:
                out[rid].d7, out[rid].p7 = diff, pct
            else:
                out[rid].d30, out[rid].p30 = diff, pct
    return out, refs


def compute_install_deltas(session, today: date) -> dict[str, Deltas]:
    """Dasselbe für die Installationszahlen, aber je Domain statt je Repo."""
    days = list(session.scalars(select(InstallSnapshot.day).distinct().order_by(InstallSnapshot.day)))
    refs = {n: _pick_reference_day(days, today, n) for n in (7, 30)}

    current = {
        d: t
        for d, t in session.execute(
            select(InstallSnapshot.domain, InstallSnapshot.total).where(InstallSnapshot.day == today)
        )
    }
    out: dict[str, Deltas] = {d: Deltas() for d in current}
    for n, ref_day in refs.items():
        if ref_day is None or ref_day == today:
            continue
        past = {
            d: t
            for d, t in session.execute(
                select(InstallSnapshot.domain, InstallSnapshot.total).where(
                    InstallSnapshot.day == ref_day
                )
            )
        }
        for d, now_val in current.items():
            then = past.get(d)
            if then is None or then <= 0:
                continue
            diff = now_val - then
            pct = diff / then * 100 if then >= MIN_BASE_FOR_PERCENT else None
            if n == 7:
                out[d].d7, out[d].p7 = diff, pct
            else:
                out[d].d30, out[d].p30 = diff, pct
    return out


def load_github_activity(session) -> dict[int, dict]:
    """Angereicherte GitHub-Daten, sofern der Anreicherungslauf schon gelaufen ist."""
    rows = session.execute(
        select(
            RepoGithub.repo_id,
            RepoGithub.pushed_at,
            RepoGithub.released_at,
            RepoGithub.is_archived,
            RepoGithub.unavailable,
            RepoGithub.license_key,
            RepoGithub.fork_count,
            RepoGithub.releases_year,
            RepoGithub.releases_year_capped,
            RepoGithub.releases_total,
            RepoGithub.commits_year,
            RepoGithub.commits_quarter,
            RepoGithub.open_issues_gh,
            RepoGithub.closed_issues,
            RepoGithub.created_at,
            RepoGithub.watchers,
        )
    ).all()
    return {
        r.repo_id: {
            "pushed_at": r.pushed_at,
            "released_at": r.released_at,
            "is_archived": r.is_archived,
            "unavailable": r.unavailable,
            "license": r.license_key,
            "forks": r.fork_count,
            "releases_year": r.releases_year,
            "releases_capped": r.releases_year_capped,
            "releases_total": r.releases_total,
            "commits_year": r.commits_year,
            "commits_quarter": r.commits_quarter,
            "open_issues": r.open_issues_gh,
            "closed_issues": r.closed_issues,
            "created_at": r.created_at,
        }
        for r in rows
    }


def classify_health(
    *,
    last_activity: datetime | None,
    is_archived: bool | None,
    is_unavailable: bool,
    now: datetime | None = None,
    thresholds: HealthThresholds | None = None,
) -> tuple[str, int | None]:
    """Wartungszustand als Ampel plus Alter in Tagen.

    Bewusst ein Hinweis, kein Urteil: eine kleine, fertige Integration für ein Gerät
    mit stabiler API kann jahrelang ohne Commit korrekt laufen. Nur 'archived' und
    'unavailable' sind harte Aussagen — alles andere ist Alter, sonst nichts.
    """
    thresholds = thresholds or HealthThresholds()
    now = now or datetime.now(timezone.utc)

    if is_unavailable:
        return "gone", None
    if is_archived:
        return "archived", None
    if last_activity is None:
        return "unknown", None

    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)
    age = (now - last_activity).days

    if age <= thresholds.active:
        return "active", age
    if age <= thresholds.quiet:
        return "quiet", age
    if age <= thresholds.stale:
        return "stale", age
    return "dormant", age


def activity_percentiles(session, today: date) -> dict[str, int]:
    """Verteilung des Aktivitätsalters — Grundlage für datengetriebene Schwellen."""
    rows = [
        r[0]
        for r in session.execute(
            select(Snapshot.last_updated).where(
                Snapshot.day == today, Snapshot.last_updated.is_not(None)
            )
        )
    ]
    if not rows:
        return {}
    now = datetime.now(timezone.utc)
    ages = sorted(
        (now - (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d)).days for d in rows
    )
    return {f"p{p}": ages[int(len(ages) * p / 100)] for p in (10, 25, 50, 75, 90, 95)}


def coverage(session, today: date) -> dict[str, int]:
    """Wie viele Repos überhaupt einen Wert je Feld haben — gehört sichtbar ins UI."""
    total = session.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.day == today))
    with_stars = session.scalar(
        select(func.count())
        .select_from(Snapshot)
        .where(Snapshot.day == today, Snapshot.stars.is_not(None))
    )
    with_dl = session.scalar(
        select(func.count())
        .select_from(Snapshot)
        .where(Snapshot.day == today, Snapshot.downloads.is_not(None))
    )
    return {"total": total or 0, "with_stars": with_stars or 0, "with_downloads": with_dl or 0}


# --- release rhythm --------------------------------------------------------
# Boundaries from the measured distribution over all 4,193 repositories:
# median 4 releases a year, P75 13, P90 27; 18.5% published nothing for over a
# year and 3.1% have never released at all.
RHYTHM = (
    (12, "continuous"),
    (4, "regular"),
    (1, "occasional"),
)


def release_rhythm(releases_year, released_at, now=None) -> str:
    """How often a project ships. A description, not a verdict.

    Deliberately separate from the maintenance signal: a project can commit daily and
    never publish, or publish steadily without much churn. Both are normal.
    """
    if released_at is None:
        return "never"
    n = releases_year or 0
    for threshold, label in RHYTHM:
        if n >= threshold:
            return label
    return "dormant"


def installs_by_version(session, day):
    """Raw {domain: {version: installs}} for one day."""
    from collections import defaultdict

    from .db import InstallVersion

    per_domain = defaultdict(dict)
    for domain, version, count in session.execute(
        select(InstallVersion.domain, InstallVersion.version, InstallVersion.count).where(
            InstallVersion.day == day
        )
    ):
        per_domain[domain][version] = count
    return per_domain


def normalise_version(v):
    """Strip the decoration projects put around the same number.

    HACS repositories tag every way imaginable, and the analytics key and the release
    tag for one and the same version routinely differ by a leading v or a suffix.
    """
    if not v:
        return None
    v = str(v).strip().lstrip("vV")
    return v or None


def adoption_share(versions: dict, latest_version):
    """Share of installations running the project's newest RELEASE.

    Which version is newest is taken from the repository's own release tag, never
    inferred from the analytics keys: those include every nightly and CI build anyone
    ever reported, and picking the numerically largest key reliably selects a dev
    build with a single install - which is how this first returned 0% for everything.

    Returns None when the release tag does not appear in the analytics data at all.
    That is genuinely unknown, not zero: it usually means the two sides spell the
    version differently, and reporting it as 0% would libel a perfectly healthy project.
    """
    total = sum(versions.values())
    if total < 20:
        return None  # below this the percentage is noise
    want = normalise_version(latest_version)
    if not want:
        return None
    for key, count in versions.items():
        if normalise_version(key) == want:
            return round(count / total * 100, 1)
    return None
