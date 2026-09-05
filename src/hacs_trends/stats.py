"""Kennzahlen der Datenbank — zur Verifikation nach jedem Sync."""

from __future__ import annotations

import json

from sqlalchemy import func, select

from .config import Config
from .db import InstallSnapshot, Repo, Snapshot, SyncRun, make_engine, make_session_factory


def print_stats(config: Config) -> None:
    engine = make_engine(config.db_path)
    Session = make_session_factory(engine)

    with Session() as s:
        total = s.scalar(select(func.count()).select_from(Repo))
        print(f"Repositories gesamt: {total}")

        print("\nJe Kategorie:")
        for cat, n in s.execute(
            select(Repo.category, func.count()).group_by(Repo.category).order_by(func.count().desc())
        ):
            print(f"  {cat:<16}{n:>6}")

        removed = s.scalar(select(func.count()).select_from(Repo).where(Repo.is_removed))
        critical = s.scalar(select(func.count()).select_from(Repo).where(Repo.is_critical))
        with_domain = s.scalar(
            select(func.count()).select_from(Repo).where(Repo.domain.is_not(None))
        )
        print(f"\nals entfernt markiert: {removed}")
        print(f"als kritisch markiert: {critical}")
        print(f"mit Integrations-Domain: {with_domain}")

        days = s.execute(
            select(Snapshot.day, func.count()).group_by(Snapshot.day).order_by(Snapshot.day.desc())
        ).all()
        print(f"\nSnapshot-Tage: {len(days)}")
        for day, n in days[:7]:
            print(f"  {day}  {n:>6} Repos")
        if len(days) < 8:
            print("  -> Delta-Spalten brauchen 7 bzw. 30 Tage Historie.")

        # Datenlücken sichtbar machen: NULL ist nicht 0.
        latest = s.scalar(select(func.max(Snapshot.day)))
        if latest:
            n_snap = s.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.day == latest))
            no_stars = s.scalar(
                select(func.count())
                .select_from(Snapshot)
                .where(Snapshot.day == latest, Snapshot.stars.is_(None))
            )
            no_dl = s.scalar(
                select(func.count())
                .select_from(Snapshot)
                .where(Snapshot.day == latest, Snapshot.downloads.is_(None))
            )
            print(f"\nDatenlücken am {latest} (von {n_snap}):")
            print(f"  ohne Sternzahl:      {no_stars:>6}  ({no_stars / n_snap * 100:.1f}%)")
            print(f"  ohne Download-Zähler:{no_dl:>6}  ({no_dl / n_snap * 100:.1f}%)")

            inst = s.scalar(
                select(func.count()).select_from(InstallSnapshot).where(InstallSnapshot.day == latest)
            )
            print(f"  Domains mit Installationsdaten: {inst}")

        print("\nLetzte Läufe:")
        for run in s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(5)):
            dur = f"{run.duration_s:.1f}s" if run.duration_s else "-"
            print(f"  #{run.id} {run.source:<18} {run.status:<12} {dur:>8}  {run.notes or ''}")
        last = s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(1)).first()
        if last and last.counts:
            print("\nZähler des letzten Laufs:")
            print(json.dumps(json.loads(last.counts), indent=2, ensure_ascii=False))
