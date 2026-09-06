"""When a repository was accepted into HACS.

HACS keeps its store as plain lists in github.com/hacs/default: one file per category,
each a JSON array of "owner/name". A repository's acceptance date is therefore the first
commit that added its line - exact, back to 2019, with no API and no token.

Measured on the real repository: the clone is 5.7 MB and takes four seconds, walking the
history over 4,903 commits takes 1.3 seconds, and 4,171 of our 4,193 repositories get a
date out of it. The 22 without one are HACS itself, which is not in its own list, and
repositories renamed on GitHub since they were accepted.

206 entries carry 2019-10-20, the day the list was created from an older location
("Add repositories from the old location"). Those were in HACS before that and the real
date is gone, so they are marked rather than dated - showing 2019-10-20 would be a
figure the data cannot support.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

REMOTE = "https://github.com/hacs/default.git"
CATEGORY_FILES = (
    "integration", "plugin", "theme", "template",
    "python_script", "appdaemon", "netdaemon",
)
# The day the list itself was created; everything stamped with it predates the record.
FOUNDING_DAY = date(2019, 10, 20)

_ENTRY = re.compile(r'^\+\s*"([^"]+)"')


@dataclass
class AddedReport:
    entries: int = 0
    founding: int = 0
    commits: int = 0
    errors: list[str] = field(default_factory=list)


def _run(args: list[str], cwd: Path | None = None, timeout: int = 300) -> str:
    result = subprocess.run(
        args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def sync_clone(cache_dir: Path) -> Path:
    """Clone hacs/default, or update the copy that is already there."""
    repo = cache_dir / "hacs-default"
    if (repo / ".git").is_dir():
        try:
            _run(["git", "fetch", "--quiet", "origin"], cwd=repo)
            _run(["git", "reset", "--quiet", "--hard", "origin/HEAD"], cwd=repo)
            return repo
        except RuntimeError as exc:
            log.warning("Update of the HACS list failed (%s), cloning fresh", exc)
            subprocess.run(["rm", "-rf", str(repo)], check=False)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--quiet", REMOTE, str(repo)], timeout=600)
    return repo


def added_dates(repo: Path) -> tuple[dict[str, date], AddedReport]:
    """First commit that added each entry, per lowercased "owner/name"."""
    report = AddedReport()
    out = _run(
        ["git", "log", "--reverse", "--format=COMMIT %ct", "--unified=0", "-p", "--"]
        + list(CATEGORY_FILES),
        cwd=repo,
        timeout=600,
    )
    first: dict[str, int] = {}
    stamp = None
    for line in out.splitlines():
        if line.startswith("COMMIT "):
            stamp = int(line.split()[1])
            report.commits += 1
            continue
        if stamp is None or not line.startswith("+") or line.startswith("+++"):
            continue
        match = _ENTRY.match(line)
        if match:
            key = match.group(1).lower()
            if key not in first or stamp < first[key]:
                first[key] = stamp

    dates = {
        key: datetime.fromtimestamp(stamp, tz=timezone.utc).date()
        for key, stamp in first.items()
    }
    report.entries = len(dates)
    report.founding = sum(1 for d in dates.values() if d <= FOUNDING_DAY)
    log.info(
        "HACS list: %d entries with an acceptance date over %d commits, %d of them from "
        "the day the list was created",
        report.entries,
        report.commits,
        report.founding,
    )
    return dates, report


def collect(cache_dir: Path) -> tuple[dict[str, date], AddedReport]:
    return added_dates(sync_clone(cache_dir))
