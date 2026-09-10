"""Turn the bootstrap output into queryable daily star counts, and compute windows.

The bootstrap writes one JSON line per repository with a date -> stars-added map. This
module loads that into ``star_daily`` and answers "how many stars in the last N days"
as a plain sum over rows.

That is a real simplification over the snapshot-difference approach used for the other
metrics: no reference day has to be chosen, no tolerance has to be applied, and a
missing sync run cannot distort the result. The trade-off is stated in the StarDaily
docstring — this counts stars given, not net change.

**The daily refresh, at the bottom of this file.** The bootstrap above is complete but
weekly: reading 60 weeks for 4,193 repositories is ~7,200 requests, fine once a week,
far too slow and far too wasteful to sit in front of every daily run. Measured against
the committed history: only 180-300 repositories gain a star on a given day, so asking
the other 4,000 "did anything change?" every day is the wrong question.

GitHub already answers it for free. The daily ``enrich`` step (github_graphql.py)
queries every repository anyway for release and commit data; adding ``stargazerCount``
to that same query cost nothing extra (measured: cost=1 per batch with or without the
field). Compared against a small committed watermark file, it says exactly which
repositories moved since yesterday - and only those get a real history request, one
page at ``per_page=2`` each (verified byte-identical to the first two buckets of a
``per_page=30`` answer), through the automatic Actions token rather than the weekly
job's personal one. ~200 requests a day instead of ~7,200 a week, and the star windows
are then at most a day old instead of up to a week.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import Repo, RepoGithub, StarDaily

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
        f"Neither {path} nor {gz} found — run 'hacs-trends bootstrap-stars' first."
    )


def _records(fh):
    """One dict per non-empty, well-formed line. Shared by the bootstrap loader and
    the daily-slice loader below - one parser for the {id, days} record shape,
    regardless of which file it came from."""
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def _rows_from_records(records, known: set[int]):
    """{id, days} records -> star_daily rows, skipping repositories no longer known
    and days with nothing added. Returns (rows, repos_seen, skipped_unknown, stars)."""
    rows: list[dict] = []
    repos = 0
    skipped_unknown = 0
    total_stars = 0
    for rec in records:
        rid = rec.get("id")
        if rid not in known:
            # A repository that left HACS between when this record was written and now.
            skipped_unknown += 1
            continue
        repos += 1
        for day_str, added in (rec.get("days") or {}).items():
            if not added:
                continue
            rows.append({"repo_id": rid, "day": date.fromisoformat(day_str), "added": int(added)})
            total_stars += int(added)
    return rows, repos, skipped_unknown, total_stars


def load_bootstrap(session, path: Path) -> dict:
    """Load the star history into star_daily. Safe to re-run.

    Reads every record; where a repository appears more than once - the one-time
    bootstrap plus a later partial refresh - the later record wins, because the daily
    refresh carries fresher counts for the days it covers.
    """

    known = {rid for (rid,) in session.execute(select(Repo.id))}
    if not known:
        raise SystemExit(
            "The repository list is empty. Run 'hacs-trends sync' first — star history "
            "attaches to repositories, so the list has to exist before it can be loaded."
        )

    with _open_any(path) as fh:
        rows, repos, skipped_unknown, total_stars = _rows_from_records(_records(fh), known)
    for i in range(0, len(rows), 5000):
        _flush(session, rows[i : i + 5000])
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


# ---------------------------------------------------------------- daily refresh ---
def _watermark_path(root: Path) -> Path:
    return root / "gh_watermark.json.gz"


def read_watermark(root: Path) -> dict[int, int]:
    """repo_id -> the GitHub stargazerCount it had the last time the daily refresh
    looked at it. Missing entirely before the first run; missing entries after that
    just mean "never checked yet", treated the same as "moved"."""
    path = _watermark_path(root)
    if not path.is_file():
        return {}
    with gzip.open(path, "rt") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}


def write_watermark(root: Path, values: dict[int, int]) -> Path:
    path = _watermark_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({str(k): v for k, v in sorted(values.items())}, separators=(",", ":")).encode()
    with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as fh:
        fh.write(body)
    return path


def _daily_dir(root: Path) -> Path:
    return root / "daily"


def daily_slice_path(root: Path, day: date) -> Path:
    return _daily_dir(root) / f"{day.isoformat()}.jsonl.gz"


def write_daily_slice(root: Path, day: date, records: list[dict]) -> Path | None:
    """One small gzip file per day, holding only the repositories that moved - the
    same {id, full_name, days} shape the bootstrap writes, just far fewer lines and
    far fewer days per line (measured: 180 repos / 14 days = 2.3 KB gzipped). Mirrors
    data/snapshots/: many small dated files, never one file rewritten whole every day -
    that would mean re-committing the same ~280 KB blob daily for a handful of new
    lines, instead of a few KB."""
    if not records:
        return None
    path = daily_slice_path(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, separators=(",", ":")) for r in records).encode()
    with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as fh:
        fh.write(body)
    return path


def load_daily_slices(session, root: Path) -> dict:
    """Load every committed daily slice into star_daily - the incremental counterpart
    to load_bootstrap, and safe to re-run for the same reason: the upsert is keyed on
    (repo_id, day), so a day a slice carries simply overwrites that one row. A slice
    only ever carries the handful of days it actually refreshed, so it can never erase
    a day the original bootstrap already had."""
    daily_dir = _daily_dir(root)
    if not daily_dir.is_dir():
        return {"slices": 0, "repos": 0, "day_rows": 0}

    known = {rid for (rid,) in session.execute(select(Repo.id))}
    files = sorted(daily_dir.glob("*.jsonl.gz"))
    total_rows = total_repos = 0
    for path in files:
        with gzip.open(path, "rt") as fh:
            rows, repos, _skipped, _stars = _rows_from_records(_records(fh), known)
        for i in range(0, len(rows), 5000):
            _flush(session, rows[i : i + 5000])
        total_rows += len(rows)
        total_repos += repos
    session.commit()
    return {"slices": len(files), "repos": total_repos, "day_rows": total_rows}


def run_daily_refresh(config, session, root: Path, *, weeks: int = 2, per_page: int = 2,
                       today: date | None = None) -> dict:
    """The daily top-up: find who moved since yesterday, ask only for them.

    "Moved" is decided by GitHub's own stargazerCount, fetched moments ago by the
    enrich step for every repository anyway (see github_graphql.py's stars_live) - not
    by HACS' own star figure, which was measured to sit still for a day or two and
    then jump for hundreds of repositories at once (2026-09-08 to 2026-09-09: 471
    repositories moved in one HACS update that should have been spread over three
    days). GitHub's own count does not carry that lag.

    A repository with no watermark yet - new to HACS, or seen for the first time since
    this shipped - counts as moved too, so its baseline gets captured now instead of
    staying silently absent from every window forever.
    """
    if not config.has_token:
        raise SystemExit("No GITHUB_TOKEN set — the daily star refresh needs it, same as enrich.")
    today = today or date.today()

    watermark = read_watermark(root)
    rows = session.execute(
        select(Repo.id, Repo.full_name, RepoGithub.stars_live)
        .join(RepoGithub, RepoGithub.repo_id == Repo.id)
        .where(RepoGithub.stars_live.is_not(None))
    ).all()

    # A repository with no watermark yet splits into two very different cases. One
    # already has real star_daily rows - the weekly full bootstrap already fetched its
    # entire history, this daily job has just never checked in on it before - and for
    # that one a fetch here would be pure waste: the data already exists, only the
    # watermark needs to catch up so future days can tell whether it moved. The other
    # has no rows at all - never captured by anything yet - and does need a real fetch
    # to get a baseline. Without this split, the very first run after this shipped (or
    # after any gap where the watermark file was lost) would re-fetch all ~4,200
    # repositories in one go instead of the ~200-300 that actually changed, exactly
    # the kind of one-time waste this feature exists to avoid.
    has_history = {rid for (rid,) in session.execute(select(StarDaily.repo_id).distinct())}

    moved: list[tuple[int, str]] = []
    seed_only: dict[int, int] = {}
    for r in rows:
        if watermark.get(r.id) == r.stars_live:
            continue
        if r.id not in watermark and r.id in has_history:
            seed_only[r.id] = r.stars_live
        else:
            moved.append((r.id, r.full_name))
    log.info(
        "Star refresh: %d of %d repositories moved since the last watermark "
        "(%d more seeded from existing history, no fetch needed)",
        len(moved), len(rows), len(seed_only),
    )

    stars_live_by_id = {r.id: r.stars_live for r in rows}
    # Everyone NOT in "moved" already matches the watermark - nothing to change for
    # them. Only "moved" repositories that are actually fetched successfully below
    # advance their watermark; one that fails stays at its old value on purpose, so
    # it is treated as still-moved and retried tomorrow rather than silently dropped.
    new_watermark = dict(watermark)
    new_watermark.update(seed_only)

    if not moved:
        write_watermark(root, new_watermark)
        return {"checked": len(rows), "moved": 0, "seeded": len(seed_only),
                "requests": 0, "day_rows": 0}

    from .sources.github_stars import StarBootstrap

    boot = StarBootstrap(config.github_token, root, delay=0.0, weeks=weeks, per_page=per_page)
    records = []
    unavailable = failed = 0
    try:
        for rid, full_name in moved:
            try:
                rec = boot.fetch_repo(rid, full_name)
            except RuntimeError:
                raise  # token revoked - stop rather than write a half-done watermark
            except Exception as exc:  # noqa: BLE001
                log.warning("%s: star refresh failed (%s), retried tomorrow", full_name, exc)
                failed += 1
                continue
            if rec.get("unavailable") or "error" in rec:
                unavailable += 1 if rec.get("unavailable") else 0
                failed += 1 if "error" in rec else 0
                continue
            records.append({"id": rid, "full_name": full_name, "days": rec.get("days") or {}})
            new_watermark[rid] = stars_live_by_id[rid]
    finally:
        boot.close()

    known = {rid for (rid,) in session.execute(select(Repo.id))}
    star_rows, _repos, _skipped, total_stars = _rows_from_records(records, known)
    for i in range(0, len(star_rows), 5000):
        _flush(session, star_rows[i : i + 5000])
    session.commit()

    write_daily_slice(root, today, records)
    write_watermark(root, new_watermark)

    return {
        "checked": len(rows), "moved": len(moved), "seeded": len(seed_only),
        "requests": boot.progress.requests,
        "unavailable": unavailable, "failed": failed,
        "day_rows": len(star_rows), "stars": total_stars,
    }
