"""Historie als Tagesscheiben im Git-Repo.

Warum nicht die SQLite committen: eine Binärdatei, die sich täglich ändert, bläht die
Git-Historie mit jedem Lauf um ihre volle Größe auf. Eine Tagesscheibe als komprimiertes
JSON ist dagegen 35 KB — rund 13 MB im Jahr, nachgemessen.

Die Scheiben sind damit die eigentliche Quelle der Wahrheit, die Datenbank nur ein
abgeleiteter Cache, der bei jedem Lauf neu aufgebaut werden kann. Das hat einen
angenehmen Nebeneffekt: ``first_seen`` muss nirgends gespeichert werden, es ergibt sich
aus der ersten Scheibe, in der ein Repo auftaucht. Nichts kann auseinanderlaufen.
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
    """Schreibt die veränderlichen Werte eines Tages. Stammdaten kommen bei jedem
    Lauf frisch aus der HACS-Quelle und gehören deshalb nicht hier hinein."""
    day = day or session.scalar(select(func.max(Snapshot.day)))
    if day is None:
        raise RuntimeError("Keine Snapshots vorhanden.")
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
    # mtime fest, damit identischer Inhalt auch identische Bytes ergibt und Git
    # nicht bei jedem Lauf eine Änderung sieht, wo keine ist.
    with gzip.GzipFile(filename="", mode="wb", fileobj=path.open("wb"), mtime=0) as fh:
        fh.write(json.dumps(payload, separators=(",", ":")).encode())
    log.info("Tagesscheibe %s: %d Repos, %d Domains, %.0f KB", day, len(repos), len(installs),
             path.stat().st_size / 1024)
    return path


def load_slices(session, root: Path) -> dict:
    """Baut die Snapshot-Historie aus allen Tagesscheiben wieder auf.

    Wird zu Beginn jedes Action-Laufs aufgerufen, weil dort eine leere Datenbank steht.
    Bestehende Zeilen werden überschrieben, der Aufruf ist also gefahrlos wiederholbar.
    """
    if not root.is_dir():
        return {"slices": 0, "rows": 0}

    files = sorted(root.glob("*.json.gz"))
    rows = 0
    first_seen: dict[int, date] = {}

    for path in files:
        with gzip.open(path, "rb") as fh:
            payload = json.loads(fh.read())
        if payload.get("v") != SLICE_VERSION:
            log.warning("%s hat Version %s, wird übersprungen", path.name, payload.get("v"))
            continue
        day = date.fromisoformat(payload["day"])
        taken = datetime.fromisoformat(payload.get("written_at") or f"{payload['day']}T12:00:00+00:00")

        batch = []
        for rid, stars, downloads, issues in payload["repos"]:
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

    # first_seen aus der Zugehoerigkeit ableiten, nicht speichern.
    known = {rid for (rid,) in session.execute(select(Repo.id))}
    for rid, day in first_seen.items():
        if rid in known:
            session.execute(
                Repo.__table__.update().where(Repo.id == rid).values(first_seen=day)
            )
    session.commit()

    log.info("Historie geladen: %d Tagesscheiben, %d Snapshot-Zeilen", len(files), rows)
    return {"slices": len(files), "rows": rows}


def snapshots_referenced(root: Path) -> list[date]:
    return sorted(date.fromisoformat(p.name[:10]) for p in root.glob("*.json.gz"))
