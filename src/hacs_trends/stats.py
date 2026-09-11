"""Database statistics - for checking the result after a sync."""

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
        print(f"Repositories total: {total}")

        print("\nPer category:")
        for cat, n in s.execute(
            select(Repo.category, func.count()).group_by(Repo.category).order_by(func.count().desc())
        ):
            print(f"  {cat:<16}{n:>6}")

        removed = s.scalar(select(func.count()).select_from(Repo).where(Repo.is_removed))
        critical = s.scalar(select(func.count()).select_from(Repo).where(Repo.is_critical))
        with_domain = s.scalar(
            select(func.count()).select_from(Repo).where(Repo.domain.is_not(None))
        )
        print(f"\nmarked removed: {removed}")
        print(f"marked critical: {critical}")
        print(f"with an integration domain: {with_domain}")

        days = s.execute(
            select(Snapshot.day, func.count()).group_by(Snapshot.day).order_by(Snapshot.day.desc())
        ).all()
        print(f"\nSnapshot days: {len(days)}")
        for day, n in days[:7]:
            print(f"  {day}  {n:>6} Repos")
        if len(days) < 8:
            print("  -> the delta columns need 7 and 30 days of history.")

        # Make data gaps visible: NULL is not 0.
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
            print(f"\nData gaps on {latest} (of {n_snap}):")
            print(f"  no star count:       {no_stars:>6}  ({no_stars / n_snap * 100:.1f}%)")
            print(f"  no download counter: {no_dl:>6}  ({no_dl / n_snap * 100:.1f}%)")

            inst = s.scalar(
                select(func.count()).select_from(InstallSnapshot).where(InstallSnapshot.day == latest)
            )
            print(f"  domains with installation figures: {inst}")

        print("\nLatest runs:")
        for run in s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(5)):
            dur = f"{run.duration_s:.1f}s" if run.duration_s else "-"
            print(f"  #{run.id} {run.source:<18} {run.status:<12} {dur:>8}  {run.notes or ''}")
        last = s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(1)).first()
        if last and last.counts:
            print("\nCounters of the latest run:")
            print(json.dumps(json.loads(last.counts), indent=2, ensure_ascii=False))
