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
