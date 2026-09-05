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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="betterhacs")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="HACS-Datensatz und HA-Analytik einlesen")
    p_sync.add_argument("--fixtures", help="Verzeichnis mit heruntergeladenen JSON-Fixtures")

    p_en = sub.add_parser("enrich", help="GitHub-Felder nachladen (pushed_at, archiviert, Release)")
    p_en.add_argument("--limit", type=int, help="nur die ersten N Repos (zum Testen)")
    p_en.add_argument("--batch-size", type=int, default=100)

    p_hw = sub.add_parser("history-write", help="Tagesscheibe der Historie schreiben")
    p_hw.add_argument("--dir", default="data/snapshots")

    p_hl = sub.add_parser("history-load", help="Historie aus den Tagesscheiben aufbauen")
    p_hl.add_argument("--dir", default="data/snapshots")

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
