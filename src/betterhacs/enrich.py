"""Anreicherungslauf: GitHub-Felder nachladen und in repo_github ablegen."""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import Config
from .db import Repo, RepoGithub, SyncRun, make_engine, make_session_factory, utcnow
from .sources.github_graphql import enrich as gql_enrich

log = logging.getLogger(__name__)


def run_enrich(config: Config, *, limit: int | None = None, batch_size: int = 100) -> dict:
    if not config.has_token:
        raise SystemExit(
            "Kein GITHUB_TOKEN gesetzt.\n"
            "Lokal: .env anlegen (siehe .env.example), ein Token ganz ohne Scopes reicht.\n"
            "In GitHub Actions steht das Token automatisch zur Verfügung."
        )

    started = time.monotonic()
    engine = make_engine(config.db_path)
    Session = make_session_factory(engine)

    with Session() as session:
        run = SyncRun(source="github-graphql", started_at=utcnow(), status="running")
        session.add(run)
        session.commit()

        rows = session.execute(select(Repo.id, Repo.full_name).order_by(Repo.id)).all()
        if limit:
            rows = rows[:limit]
        targets = [(r.id, r.full_name) for r in rows]

        def progress(done, total):
            log.info("  %d/%d", done, total)

        try:
            results, report = gql_enrich(
                targets, config.github_token, batch_size=batch_size, progress=progress
            )
            now = utcnow()
            payload = [
                {
                    "repo_id": g.repo_id,
                    "name_with_owner": g.name_with_owner,
                    "pushed_at": g.pushed_at,
                    "released_at": g.released_at,
                    "latest_tag": g.latest_tag,
                    "is_archived": g.is_archived,
                    "is_fork": g.is_fork,
                    "is_disabled": g.is_disabled,
                    "license_key": g.license_key,
                    "fork_count": g.fork_count,
                    "primary_language": g.primary_language,
                    "homepage": g.homepage,
                    "unavailable": g.unavailable,
                    "fetched_at": now,
                }
                for g in results
            ]
            for i in range(0, len(payload), 500):
                chunk = payload[i : i + 500]
                stmt = sqlite_insert(RepoGithub).values(chunk)
                session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[RepoGithub.repo_id],
                        set_={
                            c: getattr(stmt.excluded, c)
                            for c in (
                                "name_with_owner",
                                "pushed_at",
                                "released_at",
                                "latest_tag",
                                "is_archived",
                                "is_fork",
                                "is_disabled",
                                "license_key",
                                "fork_count",
                                "primary_language",
                                "homepage",
                                "unavailable",
                                "fetched_at",
                            )
                        },
                    )
                )
            counts = {
                "requested": report.requested,
                "resolved": report.resolved,
                "unavailable": report.unavailable,
                "renamed": report.renamed,
                "queries": report.queries,
                "rate_limit_remaining": report.rate_limit_remaining,
                "errors": report.errors[:5],
            }
            run.status = "ok"
        except Exception as exc:
            run.status = "failed"
            run.notes = f"{type(exc).__name__}: {exc}"
            run.finished_at = utcnow()
            session.commit()
            raise
        run.finished_at = utcnow()
        run.duration_s = time.monotonic() - started
        run.counts = json.dumps(counts, default=str)
        session.commit()

    counts["duration_s"] = round(time.monotonic() - started, 1)
    return counts
