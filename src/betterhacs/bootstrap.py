"""Driver for the one-time star history bootstrap."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import select

from .config import Config
from .db import Repo, make_engine, make_session_factory
from .sources.github_stars import StarBootstrap

log = logging.getLogger(__name__)


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def run_bootstrap(
    config: Config,
    out_dir: Path,
    *,
    limit: int | None = None,
    delay: float = 0.0,
    weeks: int | None = None,
    changed_only: bool = False,
    api_base: str | None = None,
) -> dict:
    if not config.has_token:
        raise SystemExit(
            "No GITHUB_TOKEN set.\n"
            "Create a classic personal access token with NO scopes ticked — everything\n"
            "this reads is public; the token only lifts the rate limit from 60 to 5,000\n"
            "requests per hour. Then put it in .env as GITHUB_TOKEN=..."
        )

    engine = make_engine(config.db_path)
    Session = make_session_factory(engine)
    with Session() as session:
        rows = session.execute(select(Repo.id, Repo.full_name).order_by(Repo.id)).all()
    repos = [(r.id, r.full_name) for r in rows]

    if changed_only:
        # The daily run does not need to re-read 4,193 histories. HACS gives us each
        # repository's current star count, so only those whose count moved since the
        # last snapshot can have new days to fetch - roughly 400-700 a day against
        # 4,193, which is the difference between a 35-minute job and a 5-minute one.
        from sqlalchemy import func

        from .db import Snapshot

        days = sorted(session.scalars(select(Snapshot.day).distinct()))
        if len(days) >= 2:
            today, prev = days[-1], days[-2]
            now_stars = dict(
                session.execute(
                    select(Snapshot.repo_id, Snapshot.stars).where(Snapshot.day == today)
                )
            )
            then_stars = dict(
                session.execute(
                    select(Snapshot.repo_id, Snapshot.stars).where(Snapshot.day == prev)
                )
            )
            moved = {
                rid
                for rid, val in now_stars.items()
                if val is not None and then_stars.get(rid) != val
            }
            before = len(repos)
            repos = [r for r in repos if r[0] in moved]
            log.info(
                "Only repositories whose star count moved since %s: %d of %d",
                prev, len(repos), before,
            )
        else:
            log.info("Not enough history to tell what moved - fetching everything")

    if limit:
        repos = repos[:limit]
    if not repos:
        raise SystemExit("No repositories in the database — run 'betterhacs sync' first.")

    from .sources.github_stars import DEFAULT_WEEKS

    boot = StarBootstrap(
        config.github_token, out_dir, delay=delay,
        weeks=DEFAULT_WEEKS if weeks is None else weeks,
    )
    if api_base:
        boot.client.base_url = api_base

    def report(p):
        eta = p.eta_seconds()
        log.info(
            "%d/%d repos · %d requests · %s stars · elapsed %s%s",
            p.done, p.total, p.requests, f"{p.stars:,}".replace(",", " "),
            _fmt(p.elapsed),
            f" · ~{_fmt(eta)} left" if eta else "",
        )

    started = time.monotonic()
    try:
        progress = boot.run(repos, on_progress=report)
    finally:
        boot.close()

    return {
        "repos_processed": progress.done,
        "requests": progress.requests,
        "stars_collected": progress.stars,
        "unavailable": progress.unavailable,
        "failed": progress.failed,
        "duration": _fmt(time.monotonic() - started),
        "output": str(out_dir),
    }
