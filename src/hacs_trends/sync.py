"""One sync run: the HACS dataset and Home Assistant analytics into SQLite.

A run writes exactly one snapshot per repository and day. If the sync runs several
times a day, the last run wins - the deltas work on whole days.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import Config
from .db import (
    InstallSnapshot,
    InstallVersion,
    ListGap,
    RemovedRepo,
    Repo,
    Snapshot,
    SourceEtag,
    SyncRun,
    make_engine,
    make_session_factory,
    utcnow,
)
from .sources.analytics import fetch_analytics, map_repos_to_domains
from .sources.fetch import Fetcher
from .sources.hacs import (
    fetch_categories,
    fetch_critical,
    fetch_default_lists,
    fetch_removed,
)

log = logging.getLogger(__name__)


def _load_etags(session) -> dict[str, str]:
    return {row.key: row.etag for row in session.scalars(select(SourceEtag))}


def _save_etags(session, etags: dict[str, str]) -> None:
    now = utcnow()
    for key, etag in etags.items():
        session.execute(
            sqlite_insert(SourceEtag)
            .values(key=key, etag=etag, fetched_at=now)
            .on_conflict_do_update(
                index_elements=[SourceEtag.key], set_={"etag": etag, "fetched_at": now}
            )
        )


def _chunked(rows, size=500):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def run_sync(config: Config, *, today: date | None = None) -> dict:
    started = time.monotonic()
    engine = make_engine(config.db_path)
    Session = make_session_factory(engine)
    day = today or datetime.now(timezone.utc).date()
    counts: dict = {"day": day.isoformat()}

    with Session() as session:
        run = SyncRun(source="hacs+analytics", started_at=utcnow(), status="running")
        session.add(run)
        session.commit()

        try:
            with Fetcher(fixtures=config.fixtures) as fetcher:
                etags = _load_etags(session)
                repos, report, new_etags = fetch_categories(fetcher, etags)

                if not repos and report.not_modified:
                    log.info("All categories unchanged - nothing to do.")
                    counts["not_modified"] = report.not_modified
                    run.status = "not_modified"
                    run.finished_at = utcnow()
                    run.counts = json.dumps(counts)
                    run.duration_s = time.monotonic() - started
                    session.commit()
                    return counts

                removed = fetch_removed(fetcher)
                critical = fetch_critical(fetcher)
                analytics = fetch_analytics(fetcher)
                default_lists = fetch_default_lists(fetcher)

            # --- IDs that appear in more than one category ------------------------
            seen: dict[int, str] = {}
            duplicates = []
            unique_repos = []
            for repo in repos:
                if repo.id in seen:
                    duplicates.append((repo.full_name, seen[repo.id], repo.category))
                    continue
                seen[repo.id] = repo.category
                unique_repos.append(repo)
            if duplicates:
                log.warning("%d repos in several categories: %s", len(duplicates), duplicates[:5])
            counts["duplicate_ids"] = len(duplicates)

            removed_by_name = {r["repository"]: r for r in removed}
            critical_names = {r["repository"] for r in critical}

            # --- repos upsert ------------------------------------------------------
            repo_rows = []
            for r in unique_repos:
                rm = removed_by_name.get(r.full_name)
                repo_rows.append(
                    {
                        "id": r.id,
                        "category": r.category,
                        "full_name": r.full_name,
                        "description": r.description,
                        "manifest_name": r.manifest_name,
                        "domain": r.domain,
                        "topics": json.dumps(r.topics),
                        "country": r.country,
                        "first_seen": day,
                        "last_seen": day,
                        "is_removed": rm is not None,
                        "removal_type": rm.get("removal_type") if rm else None,
                        "removal_reason": rm.get("reason") if rm else None,
                        "removal_link": rm.get("link") if rm else None,
                        "is_critical": r.full_name in critical_names,
                    }
                )

            for chunk in _chunked(repo_rows):
                stmt = sqlite_insert(Repo).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[Repo.id],
                        set_={
                            # first_seen is left alone: it is the day this project first
                            # saw the repository, the fallback for "New in HACS" when the
                            # acceptance date from hacs/default is missing.
                            "category": stmt.excluded.category,
                            "full_name": stmt.excluded.full_name,
                            "description": stmt.excluded.description,
                            "manifest_name": stmt.excluded.manifest_name,
                            "domain": stmt.excluded.domain,
                            "topics": stmt.excluded.topics,
                            "country": stmt.excluded.country,
                            "last_seen": stmt.excluded.last_seen,
                            "is_removed": stmt.excluded.is_removed,
                            "removal_type": stmt.excluded.removal_type,
                            "removal_reason": stmt.excluded.removal_reason,
                            "removal_link": stmt.excluded.removal_link,
                            "is_critical": stmt.excluded.is_critical,
                        },
                    )
                )
            session.commit()

            # --- snapshots ---------------------------------------------------------
            now = utcnow()
            snap_rows = [
                {
                    "repo_id": r.id,
                    "day": day,
                    "taken_at": now,
                    "stars": r.stars,
                    "downloads": r.downloads,
                    "open_issues": r.open_issues,
                    "last_updated": r.last_updated,
                    "last_version": r.last_version,
                    "last_commit": r.last_commit,
                }
                for r in unique_repos
            ]
            for chunk in _chunked(snap_rows):
                stmt = sqlite_insert(Snapshot).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[Snapshot.repo_id, Snapshot.day],
                        set_={
                            "taken_at": stmt.excluded.taken_at,
                            "stars": stmt.excluded.stars,
                            "downloads": stmt.excluded.downloads,
                            "open_issues": stmt.excluded.open_issues,
                            "last_updated": stmt.excluded.last_updated,
                            "last_version": stmt.excluded.last_version,
                            "last_commit": stmt.excluded.last_commit,
                        },
                    )
                )
            session.commit()

            # --- analytics ---------------------------------------------------------
            mapping, ana_report = map_repos_to_domains(unique_repos, analytics)
            mapped_domains = {d for d, _ in mapping.values()}

            inst_rows = [
                {"domain": d, "day": day, "total": analytics[d].total} for d in mapped_domains
            ]
            for chunk in _chunked(inst_rows):
                stmt = sqlite_insert(InstallSnapshot).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[InstallSnapshot.domain, InstallSnapshot.day],
                        set_={"total": stmt.excluded.total},
                    )
                )

            # Version data only for matched domains - otherwise the table grows by rows
            # nobody ever queries.
            ver_rows = [
                {"domain": d, "day": day, "version": v, "count": c}
                for d in mapped_domains
                for v, c in analytics[d].versions.items()
            ]
            for chunk in _chunked(ver_rows, 1000):
                stmt = sqlite_insert(InstallVersion).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[
                            InstallVersion.domain,
                            InstallVersion.day,
                            InstallVersion.version,
                        ],
                        set_={"count": stmt.excluded.count},
                    )
                )

            # --- Removal list as a lookup -----------------------------------------
            # Removed repositories are no longer in the dataset, so a flag on existing
            # repositories would be useless. The list is kept on its own.
            if removed:
                rm_rows = [
                    {
                        "repository": r["repository"],
                        "removal_type": r.get("removal_type"),
                        "reason": r.get("reason"),
                        "link": r.get("link"),
                        "first_seen": day,
                    }
                    for r in removed
                ]
                for chunk in _chunked(rm_rows):
                    stmt = sqlite_insert(RemovedRepo).values(chunk)
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[RemovedRepo.repository],
                            set_={
                                "removal_type": stmt.excluded.removal_type,
                                "reason": stmt.excluded.reason,
                                "link": stmt.excluded.link,
                            },
                        )
                    )

            # --- Category lists against the dataset ------------------------------
            have = {r.full_name.lower() for r in unique_repos}
            gap_rows = []
            for category, names in default_lists.items():
                for name in names:
                    if name.lower() not in have:
                        gap_rows.append(
                            {
                                "full_name": name,
                                "category": category,
                                "first_seen": day,
                                "last_seen": day,
                            }
                        )
            for chunk in _chunked(gap_rows):
                stmt = sqlite_insert(ListGap).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[ListGap.full_name],
                        set_={
                            "category": stmt.excluded.category,
                            "last_seen": stmt.excluded.last_seen,
                        },
                    )
                )
            counts["list_gaps"] = len(gap_rows)
            counts["list_total"] = sum(len(v) for v in default_lists.values())

            # --- Vanished repositories -------------------------------------------
            # Repositories seen before that are missing today. If they are on the
            # removal list, the reason is known.
            vanished = session.execute(
                select(Repo.full_name, RemovedRepo.removal_type)
                .outerjoin(RemovedRepo, RemovedRepo.repository == Repo.full_name)
                .where(Repo.last_seen < day)
            ).all()
            counts["vanished_total"] = len(vanished)
            counts["vanished_with_reason"] = sum(1 for _, t in vanished if t)
            if vanished:
                log.warning(
                    "%d previously known repos missing today (%d of them with a reason on the removal list)",
                    len(vanished),
                    counts["vanished_with_reason"],
                )

            _save_etags(session, new_etags)
            session.commit()

            counts.update(
                {
                    "repos_total": len(unique_repos),
                    "per_category": report.per_category,
                    "not_modified": report.not_modified,
                    "skipped_invalid": report.skipped_invalid,
                    "removed_entries": len(removed),
                    "critical_entries": len(critical),
                    "analytics": {
                        "domains_in_source": ana_report.domains_in_source,
                        "repos_with_domain": ana_report.repos_with_domain,
                        "matched": ana_report.matched,
                        "match_rate": round(ana_report.match_rate, 4),
                        "ambiguous_domains": ana_report.ambiguous_domains,
                        "ambiguous_repos": ana_report.ambiguous_repos,
                        "unmatched_repos": ana_report.unmatched_repos,
                    },
                    "install_rows": len(inst_rows),
                    "install_version_rows": len(ver_rows),
                }
            )

            run.status = "ok"
        except Exception as exc:
            run.status = "failed"
            run.notes = f"{type(exc).__name__}: {exc}"
            run.finished_at = utcnow()
            run.duration_s = time.monotonic() - started
            run.counts = json.dumps(counts)
            session.commit()
            raise
        else:
            run.finished_at = utcnow()
            run.duration_s = time.monotonic() - started
            run.counts = json.dumps(counts, default=str)
            session.commit()

    counts["duration_s"] = round(time.monotonic() - started, 2)
    return counts
