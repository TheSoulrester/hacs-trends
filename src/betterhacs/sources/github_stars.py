"""One-time bootstrap of the full star history.

The GitHub REST stargazer endpoint returns the moment each star was given when asked
with ``Accept: application/vnd.github.v3.star+json``. Paging through it for every HACS
repository yields the complete star curve — which is what makes the 7-day, 30-day,
quarter, year and all-time windows exact from day one, instead of only after a year of
collecting snapshots.

Measured cost: all 4,193 repositories hold 354,357 stars in total, so this is roughly
7,300 requests — about half an hour at one request per 250 ms, comfortably inside the
5,000/hour limit of an authenticated token if it pauses when the budget runs low.

Written to disk as JSON Lines rather than into the database, deliberately:

* appending a line is atomic enough to survive a crash or a closed laptop lid, so a
  run that dies at minute 80 of 90 loses one repository, not everything;
* resuming needs no state beyond the file itself — whatever is already in there is done;
* it works on filesystems where SQLite does not (network shares, FUSE mounts);
* and it is the artefact we want to commit anyway.

Star *timestamps* are aggregated to daily counts on the fly. Keeping 354,357 individual
timestamps would buy nothing: no window in the interface is finer than a day.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import GITHUB_API_BASE, USER_AGENT

log = logging.getLogger(__name__)

PER_PAGE = 100
STAR_ACCEPT = "application/vnd.github.v3.star+json"
# Stop and wait rather than burning the last requests and getting a hard block.
RATE_FLOOR = 60
_LAST_PAGE = re.compile(r'[?&]page=(\d+)>; rel="last"')


@dataclass
class BootstrapProgress:
    done: int = 0
    total: int = 0
    requests: int = 0
    stars: int = 0
    failed: int = 0
    unavailable: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def eta_seconds(self) -> float | None:
        if self.done < 5:
            return None
        return self.elapsed / self.done * (self.total - self.done)


def _load_done(progress_path: Path) -> set[int]:
    """Which repositories are already finished. The file is the only state there is."""
    if not progress_path.is_file():
        return set()
    done: set[int] = set()
    with progress_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(int(json.loads(line)["id"]))
            except (ValueError, KeyError, TypeError):
                # A half-written last line from an interrupted run. That repository
                # simply gets fetched again.
                continue
    return done


class StarBootstrap:
    def __init__(self, token: str, out_dir: Path, *, delay: float = 0.0):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.progress_path = out_dir / "progress.jsonl"
        self.events_path = out_dir / "star_days.jsonl"
        self.delay = delay
        self.client = httpx.Client(
            base_url=GITHUB_API_BASE,
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": STAR_ACCEPT,
                "User-Agent": USER_AGENT,
            },
            follow_redirects=True,
        )
        self.progress = BootstrapProgress()

    def close(self) -> None:
        self.client.close()

    # -- rate limiting ------------------------------------------------------
    def _respect_limits(self, resp: httpx.Response) -> None:
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining is None or reset is None:
            return
        try:
            remaining_i, reset_i = int(remaining), int(reset)
        except ValueError:
            return
        if remaining_i > RATE_FLOOR:
            return
        wait = max(0, reset_i - int(time.time())) + 5
        log.warning(
            "Rate limit nearly exhausted (%s left). Sleeping %d s until reset.",
            remaining_i,
            wait,
        )
        time.sleep(wait)

    def _get(self, url: str, params: dict | None = None) -> httpx.Response | None:
        """One request, with retries. Returns None when the repository is gone."""
        delay = 3.0
        for attempt in range(5):
            try:
                resp = self.client.get(url, params=params)
            except httpx.HTTPError as exc:
                log.warning("%s: %s (attempt %d)", url, exc, attempt + 1)
                time.sleep(delay)
                delay *= 2
                continue

            self.progress.requests += 1

            if resp.status_code == 200:
                self._respect_limits(resp)
                return resp
            if resp.status_code in (404, 451):
                # Deleted, made private, or blocked for legal reasons. A fact, not an error.
                return None
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                self._respect_limits(resp)
                continue
            if resp.status_code in (403, 429):
                # Secondary rate limit: GitHub asks for a pause and means it.
                wait = float(resp.headers.get("retry-after", delay))
                log.warning("HTTP %s, pausing %.0f s", resp.status_code, wait)
                time.sleep(wait)
                delay *= 2
                continue
            if resp.status_code >= 500:
                time.sleep(delay)
                delay *= 2
                continue
            log.error("%s -> HTTP %s: %s", url, resp.status_code, resp.text[:160])
            return None
        return None

    # -- one repository -----------------------------------------------------
    def fetch_repo(self, repo_id: int, full_name: str) -> dict:
        path = f"/repos/{full_name}/stargazers"
        counts: Counter[str] = Counter()

        first = self._get(path, {"per_page": PER_PAGE, "page": 1})
        if first is None:
            return {"id": repo_id, "full_name": full_name, "unavailable": True}

        last_page = 1
        link = first.headers.get("link", "")
        m = _LAST_PAGE.search(link)
        if m:
            last_page = int(m.group(1))

        def absorb(resp: httpx.Response) -> None:
            for entry in resp.json():
                # With the star media type each entry is {starred_at, user}. Without it
                # GitHub returns bare user objects — which means the Accept header did
                # not survive, and the whole run would be silently useless.
                if not isinstance(entry, dict) or "starred_at" not in entry:
                    raise RuntimeError(
                        "Stargazer response has no starred_at. The Accept header "
                        f"({STAR_ACCEPT}) is not reaching GitHub — aborting rather than "
                        "collecting unusable data."
                    )
                counts[entry["starred_at"][:10]] += 1

        absorb(first)
        for page in range(2, last_page + 1):
            if self.delay:
                time.sleep(self.delay)
            resp = self._get(path, {"per_page": PER_PAGE, "page": page})
            if resp is None:
                break
            absorb(resp)

        total = sum(counts.values())
        self.progress.stars += total
        return {
            "id": repo_id,
            "full_name": full_name,
            "total": total,
            "pages": last_page,
            "days": dict(sorted(counts.items())),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # -- the run ------------------------------------------------------------
    def run(self, repos: list[tuple[int, str]], *, on_progress=None) -> BootstrapProgress:
        done = _load_done(self.progress_path)
        todo = [(rid, name) for rid, name in repos if rid not in done]
        self.progress.total = len(todo)
        self.progress.done = 0

        if done:
            log.info("Resuming: %d repositories already collected, %d to go.", len(done), len(todo))

        with self.events_path.open("a") as events, self.progress_path.open("a") as prog:
            for rid, name in todo:
                try:
                    record = self.fetch_repo(rid, name)
                except RuntimeError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.error("%s failed: %s", name, exc)
                    record = {"id": rid, "full_name": name, "error": str(exc)[:200]}
                    self.progress.failed += 1

                if record.get("unavailable"):
                    self.progress.unavailable += 1
                elif "error" not in record:
                    events.write(json.dumps(record, separators=(",", ":")) + "\n")
                    events.flush()

                prog.write(
                    json.dumps(
                        {
                            "id": rid,
                            "n": name,
                            "t": record.get("total"),
                            "u": record.get("unavailable"),
                            "e": record.get("error"),
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                prog.flush()

                self.progress.done += 1
                if on_progress and self.progress.done % 25 == 0:
                    on_progress(self.progress)

        return self.progress
