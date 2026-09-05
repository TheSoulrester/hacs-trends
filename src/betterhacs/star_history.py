"""Turn the bootstrap output into queryable daily star counts, and compute windows.

The bootstrap writes one JSON line per repository with a date -> stars-added map. This
module loads that into ``star_daily`` and answers "how many stars in the last N days"
as a plain sum over rows.

That is a real simplification over the snapshot-difference approach used for the other
metrics: no reference day has to be chosen, no tolerance has to be applied, and a
missing sync run cannot distort the result. The trade-off is stated in the StarDaily
docstring — this counts stars given, not net change.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import Repo, StarDaily

log = logging.getLogger(__name__)

# The windows the interface offers. "all" is the current total and needs no history.
WINDOWS = (7, 30, 90, 365)


def _open_any(path: Path):
    """Open a .jsonl or the gzipped .jsonl.gz beside it.

    The bootstrap is committed compressed - 1.7 MB of JSON Lines becomes 281 KB, and it
    is written once and read on every run.
    """
    import gzip

    if path.is_file():
        return path.open()
    gz = path.with_suffix(path.suffix + ".gz")
    if gz.is_file():
        return gzip.open(gz, "rt")
    raise FileNotFoundError(
        f"Neither {path} nor {gz} found — run 'betterhacs bootstrap-stars' first."
    )


def load_bootstrap(session, path: Path) -> dict:
    """Load the star history into star_daily. Safe to re-run.

    Reads every record; where a repository appears more than once - the one-time
    bootstrap plus a later partial refresh - the later record wins, because the daily
    refresh carries fresher counts for the days it covers.
    """

    known = {rid for (rid,) in session.execute(select(Repo.id))}
    if not known:
        raise SystemExit(
            "The repository list is empty. Run 'betterhacs sync' first — star history "
            "attaches to repositories, so the list has to exist before it can be loaded."
        )
    rows: list[dict] = []
    repos = 0
    skipped_unknown = 0
    total_stars = 0

    with _open_any(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            rid = rec.get("id")
            if rid not in known:
                # A repository that left HACS between bootstrap and now.
                skipped_unknown += 1
                continue
            repos += 1
            for day_str, added in (rec.get("days") or {}).items():
                if not added:
                    continue
                rows.append({"repo_id": rid, "day": date.fromisoformat(day_str), "added": int(added)})
                total_stars += int(added)

            if len(rows) >= 5000:
                _flush(session, rows)
                rows = []
    _flush(session, rows)
    session.commit()

    stats = {
        "repos": repos,
        "day_rows": session.scalar(select(func.count()).select_from(StarDaily)),
        "stars": total_stars,
        "skipped_unknown_repo": skipped_unknown,
    }
    log.info(
        "Star history loaded: %d repos, %d daily rows, %d stars",
        stats["repos"], stats["day_rows"], stats["stars"],
    )
    return stats


def _flush(session, rows: list[dict]) -> None:
    for i in range(0, len(rows), 1000):
        chunk = rows[i : i + 1000]
        stmt = sqlite_insert(StarDaily).values(chunk)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[StarDaily.repo_id, StarDaily.day],
                set_={"added": stmt.excluded.added},
            )
        )


def window_sums(session, today: date, windows=WINDOWS) -> dict[int, dict[int, int]]:
    """{window_days: {repo_id: stars gained}}.

    The most recent day is excluded on purpose: GitHub's current-day bucket is still
    filling, so including it would make every window look slightly low in the morning
    and jump around during the day.
    """
    end = today - timedelta(days=1)
    out: dict[int, dict[int, int]] = {}
    for n in windows:
        start = end - timedelta(days=n - 1)
        out[n] = {
            rid: total
            for rid, total in session.execute(
                select(StarDaily.repo_id, func.sum(StarDaily.added))
                .where(StarDaily.day >= start, StarDaily.day <= end)
                .group_by(StarDaily.repo_id)
            )
        }
    return out


def coverage(session) -> dict:
    """How much of the corpus the bootstrap actually covers — belongs in the export
    so the interface can say what the windows rest on."""
    repos_with_history = session.scalar(
        select(func.count(func.distinct(StarDaily.repo_id)))
    )
    span = session.execute(select(func.min(StarDaily.day), func.max(StarDaily.day))).first()
    return {
        "repos_with_history": repos_with_history or 0,
        "earliest_day": span[0].isoformat() if span and span[0] else None,
        "latest_day": span[1].isoformat() if span and span[1] else None,
    }
