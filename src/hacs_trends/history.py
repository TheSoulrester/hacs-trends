"""History as daily slices in the git repository.

Why not commit the SQLite file: a binary that changes every day grows the git history
by its full size on every run. A daily slice as compressed JSON is a few dozen KB.

The slices are therefore the actual source of truth, and the database only a derived
cache that can be rebuilt on every run. A pleasant side effect: ``first_seen`` does not
have to be stored anywhere - it follows from the first slice a repository appears in.
Nothing can drift apart.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import InstallSnapshot, Repo, Snapshot

log = logging.getLogger(__name__)

SLICE_VERSION = 1


def slice_path(root: Path, day: date) -> Path:
    return root / f"{day.isoformat()}.json.gz"


def write_slice(session, root: Path, day: date | None = None) -> Path:
    """Write one day's changing values. Master data comes fresh from the HACS source
    on every run and therefore does not belong in here."""
    day = day or session.scalar(select(func.max(Snapshot.day)))
    if day is None:
        raise RuntimeError("No snapshots in the database.")
    root.mkdir(parents=True, exist_ok=True)

    repos = [
        [rid, stars, downloads, issues]
        for rid, stars, downloads, issues in session.execute(
            select(Snapshot.repo_id, Snapshot.stars, Snapshot.downloads, Snapshot.open_issues)
            .where(Snapshot.day == day)
            .order_by(Snapshot.repo_id)
        )
    ]
    installs = [
        [domain, total]
        for domain, total in session.execute(
            select(InstallSnapshot.domain, InstallSnapshot.total)
            .where(InstallSnapshot.day == day)
            .order_by(InstallSnapshot.domain)
        )
    ]
    payload = {
        "v": SLICE_VERSION,
        "day": day.isoformat(),
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": ["repo_id", "stars", "downloads", "open_issues"],
        "repos": repos,
        "installs": installs,
    }
    path = slice_path(root, day)
    # Fixed mtime, so identical content gives identical bytes and git does not see a
    # change on every run where there is none.
    with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as fh:
        fh.write(json.dumps(payload, separators=(",", ":")).encode())
    log.info("Daily slice %s: %d repos, %d domains, %.0f KB", day, len(repos), len(installs),
             path.stat().st_size / 1024)
    return path


def load_slices(session, root: Path) -> dict:
    """Rebuild the snapshot history from all daily slices.

    Called at the start of every workflow run, because the database there starts empty.
    Existing rows are overwritten, so the call is safe to repeat.
    """
    if not root.is_dir():
        return {"slices": 0, "rows": 0}

    known = {rid for (rid,) in session.execute(select(Repo.id))}
    if not known:
        raise SystemExit(
            "The repository list is empty. Run 'hacs-trends sync' first — history attaches "
            "to repositories, so the list has to exist before the slices can be loaded."
        )

    files = sorted(root.glob("*.json.gz"))
    rows = 0
    skipped = 0
    first_seen: dict[int, date] = {}

    for path in files:
        with gzip.open(path, "rb") as fh:
            payload = json.loads(fh.read())
        if payload.get("v") != SLICE_VERSION:
            log.warning("%s has version %s, skipped", path.name, payload.get("v"))
            continue
        day = date.fromisoformat(payload["day"])
        taken = datetime.fromisoformat(payload.get("written_at") or f"{payload['day']}T12:00:00+00:00")

        batch = []
        for rid, stars, downloads, issues in payload["repos"]:
            if rid not in known:
                # A repository that has since left HACS. Its history stays in the slice
                # files - that is the point of keeping them - but there is nothing to
                # attach it to today.
                skipped += 1
                continue
            first_seen.setdefault(rid, day)
            batch.append(
                {
                    "repo_id": rid,
                    "day": day,
                    "taken_at": taken,
                    "stars": stars,
                    "downloads": downloads,
                    "open_issues": issues,
                }
            )
        for i in range(0, len(batch), 1000):
            chunk = batch[i : i + 1000]
            stmt = sqlite_insert(Snapshot).values(chunk)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Snapshot.repo_id, Snapshot.day],
                    set_={
                        "stars": stmt.excluded.stars,
                        "downloads": stmt.excluded.downloads,
                        "open_issues": stmt.excluded.open_issues,
                    },
                )
            )
        rows += len(batch)

        inst = [{"domain": d, "day": day, "total": t} for d, t in payload.get("installs", [])]
        for i in range(0, len(inst), 1000):
            chunk = inst[i : i + 1000]
            stmt = sqlite_insert(InstallSnapshot).values(chunk)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[InstallSnapshot.domain, InstallSnapshot.day],
                    set_={"total": stmt.excluded.total},
                )
            )
    session.commit()

    # first_seen is derived from slice membership, never stored - so it cannot drift.
    for rid, day in first_seen.items():
        if rid in known:
            session.execute(
                Repo.__table__.update().where(Repo.id == rid).values(first_seen=day)
            )
    session.commit()

    log.info(
        "History loaded: %d slices, %d snapshot rows, %d rows for repositories no longer in HACS",
        len(files), rows, skipped,
    )
    return {"slices": len(files), "rows": rows, "skipped_gone": skipped}


def snapshots_referenced(root: Path) -> list[date]:
    return sorted(date.fromisoformat(p.name[:10]) for p in root.glob("*.json.gz"))
