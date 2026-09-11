"""Command line. One entry point, so the GitHub Action and local use take the
same path."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import load_config


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx logs one line per request at INFO. During a bootstrap that is thousands of
    # lines that bury the progress reports and make a normal run look like a failure.
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hacs-trends")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Read the HACS dataset and Home Assistant analytics")
    p_sync.add_argument("--fixtures", help="Directory with downloaded JSON fixtures")

    p_en = sub.add_parser("enrich", help="Fetch the GitHub fields (pushed_at, archived, release)")
    p_en.add_argument("--limit", type=int, help="only the first N repositories (for testing)")
    p_en.add_argument("--batch-size", type=int, default=50)

    p_hw = sub.add_parser("history-write", help="Write today's history slice")
    p_hw.add_argument("--dir", default="data/snapshots")

    p_hl = sub.add_parser("history-load", help="Rebuild the history from the daily slices")
    p_hl.add_argument("--dir", default="data/snapshots")

    p_bs = sub.add_parser(
        "bootstrap-stars",
        help="One-time: fetch the full star history for every repository (~30-90 min)",
    )
    p_bs.add_argument("--dir", default="data/stars")
    p_bs.add_argument("--limit", type=int, help="only the first N repositories (for testing)")
    p_bs.add_argument("--delay", type=float, default=0.0, help="seconds between page requests")
    p_bs.add_argument("--weeks", type=int, help="weeks of history per repo (0 = since creation)")
    p_bs.add_argument("--changed-only", action="store_true",
                      help="only repositories whose star count moved since the last sync")
    p_bs.add_argument("--api-base", help="override the API base (used by the test suite)")

    p_sl = sub.add_parser("load-stars", help="Load the bootstrap output into star_daily")
    p_sl.add_argument("--dir", default="data/stars")

    p_rd = sub.add_parser(
        "refresh-stars-daily",
        help="Daily top-up: only repositories whose GitHub star count moved since yesterday",
    )
    p_rd.add_argument("--dir", default="data/stars")
    p_rd.add_argument("--weeks", type=int, default=2,
                      help="weeks of history to request per moved repo (default: 2, covers the 7/30-day windows)")
    p_rd.add_argument("--per-page", type=int, default=2,
                      help="weeks per API page — 2 keeps each moved repo to a single request")

    p_rr = sub.add_parser(
        "refine-releases",
        help="Second pass for repositories that hit the release fetch ceiling",
    )
    p_rr.add_argument("--batch-size", type=int, default=25)

    p_hd = sub.add_parser(
        "hacs-dates",
        help="Acceptance dates from the git history of hacs/default",
    )
    p_hd.add_argument("--cache", default="data/cache", help="Where the clone is kept")

    sub.add_parser("stats", help="Print database statistics")

    p_exp = sub.add_parser("export", help="Write web/data.json, the file the page loads")
    p_exp.add_argument("--out", help="Output path (default: web/data.json)")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    config = load_config()

    if args.command == "sync":
        from pathlib import Path

        from .sync import run_sync

        if args.fixtures:
            config = type(config)(
                db_path=config.db_path,
                fixtures=Path(args.fixtures).resolve(),
                github_token=config.github_token,
            )
        result = run_sync(config)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.command in ("history-write", "history-load"):
        from pathlib import Path

        from .db import make_engine, make_session_factory
        from .history import load_slices, write_slice

        root = Path(args.dir)
        if not root.is_absolute():
            from .config import ROOT

            root = ROOT / args.dir
        engine = make_engine(config.db_path)
        Session = make_session_factory(engine)
        with Session() as session:
            if args.command == "history-write":
                print(write_slice(session, root))
            else:
                print(json.dumps(load_slices(session, root), indent=2))
        return 0

    if args.command == "hacs-dates":
        from pathlib import Path as _P

        from .db import Repo, make_engine, make_session_factory
        from .sources.hacs_default import FOUNDING_DAY, collect

        cache = _P(args.cache)
        if not cache.is_absolute():
            from .config import ROOT

            cache = ROOT / args.cache
        dates, report = collect(cache)

        engine = make_engine(config.db_path)
        Session = make_session_factory(engine)
        with Session() as session:
            matched = changed = 0
            for repo in session.query(Repo).all():
                found = dates.get(repo.full_name.lower())
                if found is None:
                    continue
                matched += 1
                if repo.added_to_hacs != found:
                    repo.added_to_hacs = found
                    changed += 1
            total = session.query(Repo).count()
            session.commit()
        print(json.dumps({
            "list_entries": report.entries,
            "commits_walked": report.commits,
            "matched": matched,
            "of_repos": total,
            "updated": changed,
            "from_founding_day": report.founding,
            "founding_day": FOUNDING_DAY.isoformat(),
        }, indent=2))
        return 0

    if args.command == "load-stars":
        from pathlib import Path as _P

        from .db import make_engine, make_session_factory
        from .star_history import coverage, load_bootstrap, load_daily_slices

        root = _P(args.dir)
        if not root.is_absolute():
            from .config import ROOT

            root = ROOT / args.dir
        engine = make_engine(config.db_path)
        Session = make_session_factory(engine)
        with Session() as session:
            stats = load_bootstrap(session, root / "star_days.jsonl")
            # The DB is rebuilt from scratch every run (it's a cache, see sync.yml) —
            # the daily top-up slices carry fresher counts for the days they cover and
            # have to be replayed on top of the bootstrap every time, not just once.
            stats["daily"] = load_daily_slices(session, root)
            stats.update(coverage(session))
        print(json.dumps(stats, indent=2))
        return 0

    if args.command == "bootstrap-stars":
        from pathlib import Path as _P

        from .bootstrap import run_bootstrap

        root = _P(args.dir)
        if not root.is_absolute():
            from .config import ROOT

            root = ROOT / args.dir
        print(json.dumps(run_bootstrap(config, root, limit=args.limit, delay=args.delay,
                                       weeks=args.weeks, changed_only=args.changed_only,
                                       api_base=args.api_base), indent=2))
        return 0

    if args.command == "refresh-stars-daily":
        from pathlib import Path as _P

        from .db import make_engine, make_session_factory
        from .star_history import run_daily_refresh

        root = _P(args.dir)
        if not root.is_absolute():
            from .config import ROOT

            root = ROOT / args.dir
        engine = make_engine(config.db_path)
        Session = make_session_factory(engine)
        with Session() as session:
            stats = run_daily_refresh(config, session, root, weeks=args.weeks, per_page=args.per_page)
        print(json.dumps(stats, indent=2))
        return 0

    if args.command == "refine-releases":
        from .enrich import refine_releases

        print(json.dumps(refine_releases(config, batch_size=args.batch_size), indent=2))
        return 0

    if args.command == "enrich":
        from .enrich import run_enrich

        print(json.dumps(run_enrich(config, limit=args.limit, batch_size=args.batch_size), indent=2))
        return 0

    if args.command == "export":
        from pathlib import Path

        from .export import export

        path = export(config, Path(args.out).resolve() if args.out else None)
        print(path)
        return 0

    if args.command == "stats":
        from .stats import print_stats

        print_stats(config)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
