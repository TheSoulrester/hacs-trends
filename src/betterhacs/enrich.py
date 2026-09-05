"""Anreicherungslauf: GitHub-Felder nachladen und in repo_github ablegen."""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import Config
from .db import Repo, RepoGithub, SyncRun, make_engine, make_session_factory, utcnow
from .sources.github_graphql import enrich as gql_enrich

log = logging.getLogger(__name__)

# Columns written back; kept in one place so the insert and the conflict-update
# can never drift apart.
FIELDS = ('name_with_owner', 'created_at', 'pushed_at', 'released_at', 'latest_tag', 'releases_total', 'releases_year', 'releases_quarter', 'uses_prerelease', 'commits_year', 'commits_quarter', 'is_archived', 'is_fork', 'is_disabled', 'license_key', 'fork_count', 'watchers', 'open_issues_gh', 'closed_issues', 'primary_language', 'homepage', 'unavailable')


def run_enrich(config: Config, *, limit: int | None = None, batch_size: int = 50,
               resume: bool = True) -> dict:
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

        if resume:
            # Anything fetched within the last day is current enough; skipping it lets a
            # run that was cut short simply be started again.
            cutoff = utcnow() - timedelta(days=1)
            done = {
                rid
                for (rid,) in session.execute(
                    select(RepoGithub.repo_id).where(RepoGithub.fetched_at >= cutoff)
                )
            }
            if done:
                targets = [t for t in targets if t[0] not in done]
                log.info("Resuming: %d already enriched, %d to go", len(done), len(targets))
            if not targets:
                return {"requested": 0, "resolved": 0, "note": "everything already enriched"}

        def progress(done, total):
            log.info("  %d/%d", done, total)

        # Written back in slices rather than once at the end: a run that is
        # interrupted - a closed laptop, a timeout, a rate limit - then keeps
        # everything it had already fetched, and resume picks up from there.
        SLICE = 250
        counts = {
            "requested": len(targets), "resolved": 0, "unavailable": 0,
            "renamed": 0, "queries": 0, "cost_points": 0,
            "rate_limit_remaining": None, "errors": [],
        }
        try:
            for offset in range(0, len(targets), SLICE):
                part = targets[offset : offset + SLICE]
                results, report = gql_enrich(
                    part, config.github_token, batch_size=batch_size, progress=progress
                )
                now = utcnow()
                payload = [
                    {**{f: getattr(g, f) for f in FIELDS}, "repo_id": g.repo_id,
                     "fetched_at": now}
                    for g in results
                ]
                for i in range(0, len(payload), 500):
                    chunk = payload[i : i + 500]
                    stmt = sqlite_insert(RepoGithub).values(chunk)
                    session.execute(
                        stmt.on_conflict_do_update(
                            index_elements=[RepoGithub.repo_id],
                            set_={c: getattr(stmt.excluded, c) for c in FIELDS + ("fetched_at",)},
                        )
                    )
                session.commit()
                counts["resolved"] += report.resolved
                counts["unavailable"] += report.unavailable
                counts["renamed"] += report.renamed
                counts["queries"] += report.queries
                counts["cost_points"] += report.cost
                counts["errors"] = (counts["errors"] + report.errors)[:10]
                if report.rate_limit_remaining is not None:
                    counts["rate_limit_remaining"] = report.rate_limit_remaining
                log.info("committed %d/%d", min(offset + SLICE, len(targets)), len(targets))

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
