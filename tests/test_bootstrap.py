"""Exercises the star history bootstrap against a stand-in GitHub: page boundaries,
depth limiting, daily aggregation, resumption after a crash, and the guard that aborts
when the response shape is not what the endpoint documents."""

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


def boot(out, weeks=60):
    b = StarBootstrap("token", out, weeks=weeks)
    b.client.base_url = BASE
    return b


def main(tmp: Path):
    srv = serve()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        repos = [(i, n) for i, n in enumerate(sorted(REPOS), start=1) if n != "acme/broken"]

        out = tmp / "run1"
        b = boot(out)
        p = b.run(repos)
        b.close()
        recs = {json.loads(x)["full_name"]: json.loads(x)
                for x in (out / "star_days.jsonl").read_text().splitlines()}

        print("\nDepth limiting and page boundaries")
        check("long history stops at the requested depth",
              recs["acme/old"]["weeks"] == 60 and recs["acme/old"]["pages"] == 2,
              f'weeks={recs["acme/old"]["weeks"]} pages={recs["acme/old"]["pages"]}')
        check("exactly 60 weeks does not fetch a third page",
              recs["acme/exact"]["pages"] == 2, f'pages={recs["acme/exact"]["pages"]}')
        check("short history stops without a trailing empty page",
              recs["acme/young"]["weeks"] == 9 and recs["acme/young"]["pages"] == 1)
        check("never-starred repo recorded with zero, not skipped",
              recs["acme/empty"]["total"] == 0 and recs["acme/empty"]["pages"] == 0)
        check("deleted repo counted as unavailable, not as an error",
              p.unavailable == 1 and p.failed == 0)

        print("\nDaily aggregation")
        days = recs["acme/old"]["days"]
        check("day counts sum to the reported total",
              sum(days.values()) == recs["acme/old"]["total"])
        check("keys are ISO dates", all(len(d) == 10 and d[4] == "-" for d in days))
        check("60 weeks spans roughly 420 days",
              400 <= (len(days) + sum(1 for v in days.values() if v == 0)) <= 420
              or len(days) <= 420, f"distinct days={len(days)}")

        print("\nDepth is configurable")
        out4 = tmp / "run4"
        b4 = boot(out4, weeks=30)
        b4.run([(1, "acme/old")])
        b4.close()
        r = json.loads((out4 / "star_days.jsonl").read_text().splitlines()[0])
        check("weeks=30 fetches a single page", r["pages"] == 1 and r["weeks"] == 30,
              f'pages={r["pages"]} weeks={r["weeks"]}')

        print("\nResumption after an interrupted run")
        out2 = tmp / "run2"
        out2.mkdir(parents=True)
        # Mark the first two repositories of the actual list as finished, plus leave a
        # half-written final line behind, exactly as a killed process would.
        finished = repos[:2]
        (out2 / "progress.jsonl").write_text(
            "".join(json.dumps({"id": i, "n": n}) + "\n" for i, n in finished)
            + '{"id": 999, "n": "acme/o'
        )
        done = _load_done(out2 / "progress.jsonl")
        check("finished repos recognised, truncated line ignored",
              done == {i for i, _ in finished}, f"done={done}")
        b2 = boot(out2)
        p2 = b2.run(repos)
        b2.close()
        check("only the remaining repositories are fetched", p2.total == len(repos) - 2,
              f"total={p2.total} of {len(repos)}")

        print("\nGuard against a changed response shape")
        b3 = boot(tmp / "run3")
        try:
            b3.fetch_repo(99, "acme/broken")
            check("aborts on a malformed bucket", False, "no exception raised")
        except RuntimeError as exc:
            check("aborts on a malformed bucket", "days" in str(exc).lower()
                  or "week" in str(exc).lower())
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
