"""Exercises the star bootstrap against a fake GitHub: pagination boundaries,
daily aggregation, resumption after a crash, and the guard that aborts when the
star media type is not honoured."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from betterhacs.sources.github_stars import StarBootstrap, _load_done  # noqa: E402
from fake_github import REPOS, serve  # noqa: E402

BASE = "http://127.0.0.1:8731"
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAILS.append(name)


def main(tmp: Path):
    srv = serve()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        repos = [(i, n) for i, n in enumerate(sorted(REPOS), start=1)]

        # --- full run -----------------------------------------------------
        out = tmp / "run1"
        b = StarBootstrap("token", out)
        b.client.base_url = BASE
        p = b.run(repos)
        b.close()

        records = [json.loads(x) for x in (out / "star_days.jsonl").read_text().splitlines()]
        by_name = {r["full_name"]: r for r in records}

        print("\nPagination and aggregation")
        check("250 stars -> 3 pages, all counted",
              by_name["acme/big"]["total"] == 250 and by_name["acme/big"]["pages"] == 3,
              f'total={by_name["acme/big"]["total"]} pages={by_name["acme/big"]["pages"]}')
        check("exactly 200 stars -> 2 pages, no phantom third",
              by_name["acme/exact"]["total"] == 200 and by_name["acme/exact"]["pages"] == 2,
              f'total={by_name["acme/exact"]["total"]} pages={by_name["acme/exact"]["pages"]}')
        check("single page without Link header",
              by_name["acme/small"]["total"] == 7 and by_name["acme/small"]["pages"] == 1)
        check("repo with zero stars is recorded, not skipped",
              by_name["acme/empty"]["total"] == 0)
        check("deleted repo counted as unavailable, not as an error",
              p.unavailable == 1 and p.failed == 0)
        check("day counts sum to the total",
              sum(by_name["acme/big"]["days"].values()) == 250)
        check("days are ISO dates only",
              all(len(d) == 10 for d in by_name["acme/big"]["days"]))

        # --- resumption ---------------------------------------------------
        print("\nResumption after an interrupted run")
        out2 = tmp / "run2"
        out2.mkdir(parents=True)
        # Simulate a run that died after two repositories.
        (out2 / "progress.jsonl").write_text(
            json.dumps({"id": 1, "n": "acme/big"}) + "\n"
            + json.dumps({"id": 2, "n": "acme/empty"}) + "\n"
            + '{"id": 3, "n": "acme/ex'  # half-written final line
        )
        done = _load_done(out2 / "progress.jsonl")
        check("finished repos recognised, truncated line ignored", done == {1, 2}, f"done={done}")

        b2 = StarBootstrap("token", out2)
        b2.client.base_url = BASE
        p2 = b2.run(repos)
        b2.close()
        check("only the remaining repositories are fetched", p2.total == 3, f"total={p2.total}")

        # --- the guard ------------------------------------------------------
        print("\nGuard against a missing star media type")
        out3 = tmp / "run3"
        b3 = StarBootstrap("token", out3)
        b3.client.base_url = BASE
        b3.client.headers["Accept"] = "application/vnd.github+json"  # wrong on purpose
        try:
            b3.fetch_repo(1, "acme/big")
            check("aborts instead of storing timestamp-less data", False, "no exception raised")
        except RuntimeError as exc:
            check("aborts instead of storing timestamp-less data", "starred_at" in str(exc))
        b3.close()
    finally:
        srv.shutdown()

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        sys.exit(main(Path(td)))
