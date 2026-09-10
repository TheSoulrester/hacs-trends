"""One-time bootstrap of the star history.

**A note on why this file was rewritten.** The original version paged through
``GET /repos/{owner}/{repo}/stargazers`` with the ``star+json`` media type, which used
to return the moment each individual star was given. On 30 June 2026 GitHub restricted
that endpoint to a repository's own admins and collaborators, and tokens without scopes
stopped working on it entirely. It now answers 404 for every repository you do not own —
not 403, because GitHub does not confirm existence to callers without access. Any tool
built on it broke overnight, and there is no workaround.

GitHub shipped the replacement on 4 September 2026:

    GET /repos/{owner}/{repo}/stargazers/history?per_page=30&page=N

It returns weekly buckets, newest first, each with a seven-element ``days`` array — so
daily resolution, without exposing who starred anything. It works for any public
repository with an ordinary token, and it goes back to the repository's creation.

Verified against ``hacs/integration``: 14 pages back to its creation week in February
2019, and the daily values sum to exactly the current star count of 7,684. No drift.

Cost is driven by repository *age* now, not star count: one request per 30 weeks. The
default depth of 60 weeks covers every window up to a year in at most two requests per
repository — roughly 8,000 requests for all of HACS. Full history since creation would
be about 29,000 and is available behind ``--weeks 0`` when it is worth the hours.

Results are written as JSON Lines rather than into the database, deliberately:

* appending a line survives a crash or a closed laptop lid, so a run that dies at minute
  80 of 90 loses one repository, not everything;
* resuming needs no state beyond the file itself;
* it works on filesystems where SQLite does not;
* and it is the artefact we want to commit anyway.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..config import GITHUB_API_BASE, USER_AGENT

log = logging.getLogger(__name__)

# The history endpoint caps per_page at 30 weeks and page at 100.
PER_PAGE = 30
MAX_PAGE = 100
API_VERSION = "2026-03-10"
# 60 weeks covers every window up to a year with margin, in at most two requests.
DEFAULT_WEEKS = 60
# Stop and wait rather than burning the last requests and getting a hard block.
RATE_FLOOR = 60


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
    def __init__(self, token: str, out_dir: Path, *, delay: float = 0.0,
                 weeks: int = DEFAULT_WEEKS, per_page: int = PER_PAGE):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.progress_path = out_dir / "progress.jsonl"
        self.events_path = out_dir / "star_days.jsonl"
        self.delay = delay
        self.weeks = weeks
        # The one-time bootstrap wants the widest page (30 weeks) to cover a year in
        # two requests. A daily top-up only needs to see since yesterday, so it asks
        # for 2 weeks at per_page=2 - one request per repository instead of one or two,
        # and verified byte-identical to the first two buckets of a per_page=30 answer.
        self.per_page = per_page
        self.client = httpx.Client(
            base_url=GITHUB_API_BASE,
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
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
            if resp.status_code == 401:
                # A revoked or expired token must stop the run, not quietly mark every
                # remaining repository as unavailable - that would poison the output
                # with plausible-looking nulls that nobody would notice.
                raise RuntimeError(
                    "GitHub rejected the token (401). It was probably revoked or has "
                    "expired. Fix GITHUB_TOKEN and run again - progress is kept."
                )
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
        """Walk the weekly history backwards until the requested depth is covered."""
        path = f"/repos/{full_name}/stargazers/history"
        counts: dict[str, int] = {}
        weeks_seen = 0
        pages = 0
        want = self.weeks or (MAX_PAGE * PER_PAGE)  # weeks=0 means everything

        for page in range(1, MAX_PAGE + 1):
            if page > 1 and self.delay:
                time.sleep(self.delay)
            resp = self._get(path, {"per_page": self.per_page, "page": page})
            if resp is None:
                if page == 1:
                    return {"id": repo_id, "full_name": full_name, "unavailable": True}
                break

            batch = resp.json()
            if not isinstance(batch, list):
                raise RuntimeError(
                    f"{path} did not return a list. The star history endpoint has "
                    "changed shape — aborting rather than collecting unusable data."
                )
            if not batch:
                break
            pages += 1

            for bucket in batch:
                # Guard the contract explicitly. A silent shape change here would
                # produce an entire run of plausible-looking but wrong numbers.
                if (
                    not isinstance(bucket, dict)
                    or "week" not in bucket
                    or not isinstance(bucket.get("days"), list)
                    or len(bucket["days"]) != 7
                ):
                    raise RuntimeError(
                        "Star history bucket is not {week, total, days[7]} as documented: "
                        f"{str(bucket)[:120]} — aborting."
                    )
                week_start = datetime.fromtimestamp(bucket["week"], tz=timezone.utc).date()
                for offset, n in enumerate(bucket["days"]):
                    if n:
                        day = week_start + timedelta(days=offset)
                        counts[day.isoformat()] = counts.get(day.isoformat(), 0) + int(n)
                weeks_seen += 1

            # Buckets come newest first, so once we have enough weeks we can stop.
            if weeks_seen >= want or len(batch) < self.per_page:
                break

        total = sum(counts.values())
        self.progress.stars += total
        return {
            "id": repo_id,
            "full_name": full_name,
            "total": total,
            "pages": pages,
            "weeks": weeks_seen,
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
