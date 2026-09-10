"""Exercises the daily star-history top-up end to end: watermark comparison, moved-vs-
unmoved selection, the actual DB writes, the daily slice file, and re-loading everything
from scratch the way sync.yml does on every CI run (fresh DB, replay bootstrap + all
daily slices)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hacs_trends.config import Config  # noqa: E402
from hacs_trends.db import Repo, RepoGithub, StarDaily, make_engine, make_session_factory  # noqa: E402
from hacs_trends.star_history import (  # noqa: E402
    load_bootstrap,
    load_daily_slices,
    read_watermark,
    run_daily_refresh,
    write_watermark,
)
from fake_github import REPOS, serve  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAILS.append(name)


def _seed_repos(session, names, first_seen=date(2020, 1, 1)):
    for i, n in enumerate(sorted(names), start=1):
        session.add(Repo(
            id=i, category="integration", full_name=n, topics="[]",
            first_seen=first_seen, last_seen=first_seen,
        ))
    session.commit()
    return {n: i for i, n in enumerate(sorted(names), start=1)}


def _set_stars_live(session, ids_by_name, values: dict[str, int | None]):
    from datetime import datetime, timezone

    for name, v in values.items():
        rid = ids_by_name[name]
        row = session.get(RepoGithub, rid)
        if row is None:
            session.add(RepoGithub(repo_id=rid, stars_live=v, fetched_at=datetime.now(timezone.utc)))
        else:
            row.stars_live = v
    session.commit()


def main(tmp: Path):
    srv = serve()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    names = [n for n in REPOS if n != "acme/broken"]  # acme/gone, acme/old, acme/exact, acme/young, acme/empty
    config = Config(db_path=tmp / "unused.db", fixtures=None, github_token="token")

    def new_db(name):
        engine = make_engine(tmp / f"{name}.db")
        Session = make_session_factory(engine)
        return Session

    try:
        # --- 1. No watermark yet: every repo with a stars_live value counts as moved ---
        Session = new_db("db1")
        root = tmp / "stars1"
        root.mkdir()
        with Session() as session:
            ids = _seed_repos(session, names)
            # acme/gone has no stars_live (still being enriched) - must be skipped, not crash
            _set_stars_live(session, ids, {n: 10 for n in names if n != "acme/gone"})

            # run_daily_refresh does `from .sources.github_stars import StarBootstrap`
            # fresh inside the function body, so patching the module attribute (not the
            # star_history module) is what actually takes effect - point it at the fake
            # server instead of api.github.com.
            import hacs_trends.sources.github_stars as ghs

            class PatchedBootstrap(ghs.StarBootstrap):
                def __init__(self, *a, **kw):
                    super().__init__(*a, **kw)
                    self.client.base_url = "http://127.0.0.1:8731"

            ghs.StarBootstrap = PatchedBootstrap
            stats = run_daily_refresh(config, session, root, weeks=60, per_page=30, today=date(2026, 9, 10))

        check("first run treats every stars_live-bearing repo as moved",
              stats["moved"] == len(names) - 1, f"moved={stats['moved']} expected={len(names) - 1}")
        check("the repo with no stars_live yet is not counted at all",
              stats["checked"] == len(names) - 1, f"checked={stats['checked']}")

        wm = read_watermark(root)
        check("watermark now holds every successfully-fetched repo",
              set(wm) == {ids[n] for n in names if n not in ("acme/gone",)},
              f"watermark ids={sorted(wm)}")
        check("deleted upstream repo (acme/gone, 404) does not get a watermark",
              ids["acme/gone"] not in wm)

        slice_path = root / "daily" / "2026-09-10.jsonl.gz"
        check("a daily slice file was written for today", slice_path.is_file())

        with Session() as session:
            total_rows = session.query(StarDaily).count()
        check("star_daily rows were written", total_rows > 0, f"rows={total_rows}")

        # --- 2. Second run, nothing changed: watermark matches stars_live -> no moves ---
        with Session() as session:
            stats2 = run_daily_refresh(config, session, root, weeks=60, per_page=30, today=date(2026, 9, 11))
        check("unchanged stars_live -> nothing counted as moved", stats2["moved"] == 0,
              f"moved={stats2['moved']}")
        check("no requests made when nothing moved", stats2["requests"] == 0)
        check("no new slice file for a day with zero moves",
              not (root / "daily" / "2026-09-11.jsonl.gz").is_file())

        # --- 3. Only the repos whose stars_live changed are re-fetched ---
        with Session() as session:
            _set_stars_live(session, ids, {"acme/exact": 11, "acme/young": 12})
            stats3 = run_daily_refresh(config, session, root, weeks=60, per_page=30, today=date(2026, 9, 12))
        check("only the two changed repos counted as moved", stats3["moved"] == 2,
              f"moved={stats3['moved']}")
        wm3 = read_watermark(root)
        check("watermark advanced only for the moved repos",
              wm3[ids["acme/exact"]] == 11 and wm3[ids["acme/young"]] == 12)
        check("watermark for untouched repos is unchanged",
              wm3[ids["acme/old"]] == 10 and wm3[ids["acme/empty"]] == 10)

        # --- 4. A transient per-repo failure keeps its OLD watermark (retried tomorrow),
        # without aborting the rest of the batch. fetch_repo only raises a plain (non-
        # RuntimeError) exception for something like a JSON decode failure - simulate
        # that for one repo while a second, healthy repo moves in the same run, and
        # confirm the healthy one still gets processed and the failing one does not
        # poison its watermark.
        import hacs_trends.sources.github_stars as ghs
        real_fetch_repo = ghs.StarBootstrap.fetch_repo

        def flaky_fetch_repo(self, repo_id, full_name):
            if full_name == "acme/old":
                raise ValueError("simulated: response body was not valid JSON")
            return real_fetch_repo(self, repo_id, full_name)

        with Session() as session:
            r = session.get(Repo, ids["acme/old"])
            check("fixture sanity: acme/old still has its real name", r.full_name == "acme/old")
            _set_stars_live(session, ids, {"acme/old": 999, "acme/empty": 42})
            wm_before = read_watermark(root)[ids["acme/old"]]
            ghs.StarBootstrap.fetch_repo = flaky_fetch_repo
            try:
                stats4 = run_daily_refresh(config, session, root, weeks=60, per_page=30, today=date(2026, 9, 13))
            finally:
                ghs.StarBootstrap.fetch_repo = real_fetch_repo
        wm4 = read_watermark(root)
        check("the run does not abort just because one repo failed",
              stats4["moved"] == 2, f"moved={stats4['moved']}")
        check("the failing repo is counted as failed, not silently dropped",
              stats4["failed"] == 1, f"failed={stats4['failed']}")
        check("its watermark stays at the OLD value so it is retried tomorrow",
              wm4[ids["acme/old"]] == wm_before, f"before={wm_before} after={wm4[ids['acme/old']]}")
        check("the OTHER repo in the same run still advanced normally",
              wm4[ids["acme/empty"]] == 42, f"watermark={wm4.get(ids['acme/empty'])}")

        # --- 4b. A repo with no watermark yet but EXISTING star_daily rows (i.e. the
        # weekly full bootstrap already has its history) gets seeded silently - no
        # fetch - instead of being treated as "moved". This is what keeps the very
        # first run after a fresh deploy (or after losing the watermark file) from
        # re-fetching all ~4,200 repositories for data that already exists. Isolated
        # in its own DB/dir so it is not tangled up with the stale watermark left
        # behind by the failure scenario above.
        from hacs_trends.db import StarDaily as _SD

        Session4b = new_db("db4b")
        root4b = tmp / "stars4b"
        root4b.mkdir()
        with Session4b() as session:
            ids4b = _seed_repos(session, names)
            _set_stars_live(session, ids4b, {n: 5 for n in names if n != "acme/gone"})
            # acme/exact already has star_daily rows, as if the weekly bootstrap had
            # already run for it - acme/young has none, as if it were genuinely new.
            session.add(_SD(repo_id=ids4b["acme/exact"], day=date(2020, 1, 1), added=3))
            session.commit()
            stats4b = run_daily_refresh(config, session, root4b, weeks=60, per_page=30, today=date(2026, 9, 14))
        wm4b = read_watermark(root4b)
        check("a repo with existing history is seeded, not treated as moved",
              stats4b.get("seeded") == 1, f"seeded={stats4b.get('seeded')} moved={stats4b['moved']}")
        # acme/old has 420 weeks of history, so at per_page=30 it alone costs 2 pages -
        # the point isn't "one request per moved repo", it's that the seeded repo
        # (acme/exact) contributed zero requests despite also lacking a watermark.
        check("fewer requests than repositories - the seeded one cost nothing",
              stats4b["requests"] < len(names), f"requests={stats4b['requests']} of {len(names)} repos")
        check("the seeded repo's watermark is set directly to its current stars_live",
              wm4b[ids4b["acme/exact"]] == 5, f"watermark={wm4b.get(ids4b['acme/exact'])}")

        # --- 5. Rebuild from scratch: bootstrap file + replaying every daily slice ---
        # This is exactly what sync.yml does on every run (SQLite is a disposable cache).
        boot_path = root / "star_days.jsonl"
        boot_path.write_text(
            "\n".join(
                json.dumps({"id": ids[n], "full_name": n, "days": {"2020-01-01": 5}})
                for n in names
            )
            + "\n"
        )
        Session2 = new_db("db2")
        with Session2() as session:
            _seed_repos(session, names)
            load_bootstrap(session, boot_path)
            daily_stats = load_daily_slices(session, root)
            rows_after = session.query(StarDaily).count()
        check("rebuild replays every daily slice found on disk",
              daily_stats["slices"] >= 2, f"slices={daily_stats['slices']}")
        check("rebuilt DB has both the bootstrap day and the daily-slice days",
              rows_after > len(names), f"rows={rows_after}")

        # --- 6. write_watermark / read_watermark round-trip through gzip ---
        write_watermark(root, {1: 5, 2: 9})
        check("watermark round-trips through gzip", read_watermark(root) == {1: 5, 2: 9})
        check("missing watermark file reads back as empty dict",
              read_watermark(tmp / "does-not-exist") == {})

    finally:
        srv.shutdown()

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        sys.exit(main(Path(td)))
