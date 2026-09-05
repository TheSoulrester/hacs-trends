"""Kommandozeile. Ein Einstiegspunkt, damit GitHub Action und lokale Nutzung
denselben Weg gehen."""

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
    parser = argparse.ArgumentParser(prog="betterhacs")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="HACS-Datensatz und HA-Analytik einlesen")
    p_sync.add_argument("--fixtures", help="Verzeichnis mit heruntergeladenen JSON-Fixtures")

    p_en = sub.add_parser("enrich", help="GitHub-Felder nachladen (pushed_at, archiviert, Release)")
    p_en.add_argument("--limit", type=int, help="nur die ersten N Repos (zum Testen)")
    p_en.add_argument("--batch-size", type=int, default=50)

    p_hw = sub.add_parser("history-write", help="Tagesscheibe der Historie schreiben")
    p_hw.add_argument("--dir", default="data/snapshots")

    p_hl = sub.add_parser("history-load", help="Historie aus den Tagesscheiben aufbauen")
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

    p_rr = sub.add_parser(
        "refine-releases",
        help="Second pass for repositories that hit the release fetch ceiling",
    )
    p_rr.add_argument("--batch-size", type=int, default=25)

    sub.add_parser("stats", help="Kennzahlen der Datenbank ausgeben")

    p_exp = sub.add_parser("export", help="Statische docs/data.json erzeugen")
    p_exp.add_argument("--out", help="Zielpfad (Standard: docs/data.json)")

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

    if args.command == "load-stars":
        from pathlib import Path as _P

        from .db import make_engine, make_session_factory
        from .star_history import coverage, load_bootstrap

        root = _P(args.dir)
        if not root.is_absolute():
            from .config import ROOT

            root = ROOT / args.dir
        engine = make_engine(config.db_path)
        Session = make_session_factory(engine)
        with Session() as session:
            stats = load_bootstrap(session, root / "star_days.jsonl")
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
