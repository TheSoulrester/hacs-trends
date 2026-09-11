#!/usr/bin/env bash
# One command that runs anywhere: ./run.sh
#
# Finds a usable Python, creates a virtual environment, installs the dependencies,
# fetches the data and starts the page. Needs no uv, no Homebrew, no admin rights.

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY=""

find_python() {
  # uv brings its own Python and is the most convenient route when it is there.
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  # Otherwise the newest suitable system Python. SQLAlchemy needs at least 3.10.
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "$c"; return
      fi
    fi
  done
  echo ""
}

PY="$(find_python)"

if [ -z "$PY" ]; then
  cat <<'MSG'
No Python 3.10 or newer found.

The easiest way to change that, without admin rights and without touching the
system: uv installs itself into your home directory and brings its own Python:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Then open a new terminal and run ./run.sh here again.
Alternatively, install a current Python from python.org.
MSG
  exit 1
fi

echo "==> Python: $PY"

if [ "$PY" = "uv" ]; then
  uv sync --quiet
  RUN="uv run"
else
  # A virtual environment is a set of symlinks to one interpreter. If that interpreter
  # moves - a Python upgrade, a moved folder, a checkout used from another machine - the
  # directory is still there and every command fails with "No such file or directory",
  # which reads like a broken script rather than a stale link. So it is not enough to
  # check that the directory exists: the interpreter has to actually run.
  if [ -e "$VENV" ] && ! "$VENV/bin/python" -c "pass" 2>/dev/null; then
    echo "==> Virtual environment points nowhere, recreating it"
    rm -rf "$VENV"
  fi
  if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Creating virtual environment ($VENV)"
    "$PY" -m venv "$VENV"
  fi
  echo "==> Installing dependencies"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -e .
  RUN="$VENV/bin/python -m"
fi

cmd() {
  if [ "$PY" = "uv" ]; then uv run hacs-trends "$@"; else "$VENV/bin/python" -m hacs_trends.cli "$@"; fi
}

case "${1:-serve}" in
  sync)   cmd sync ;;
  bootstrap)
    # One-time: fetch the full star history. Takes roughly 30-90 minutes and is
    # resumable - if it stops, run it again and it picks up where it left off.
    if [ ! -f data/hacs_trends.db ]; then
      echo "==> No database yet, running sync first"
      cmd sync
    fi
    if [ ! -f .env ] || ! grep -q "^GITHUB_TOKEN=." .env 2>/dev/null; then
      echo "GITHUB_TOKEN missing in .env - see .env.example" >&2
      exit 1
    fi
    cmd bootstrap-stars
    ;;
  test)
    # Plain scripts, no test framework: each prints PASS/FAIL per check and exits non-zero
    # if any check failed. Every tests/test_*.py runs, so a new one needs no wiring here.
    fail=0
    for t in tests/test_*.py; do
      echo "==> $t"
      if [ "$PY" = "uv" ]; then uv run python "$t" || fail=1; else "$VENV/bin/python" "$t" || fail=1; fi
    done
    exit "$fail"
    ;;
  export) cmd export --out web/data.json ;;
  stats)  cmd stats ;;
  dates)  cmd hacs-dates ;;
  check)
    # Seconds, no token, no network: the mistakes one actually makes while typing.
    # It does not replace looking at the page - it catches the things that would
    # otherwise be found by a workflow run ten minutes later, or by a visitor.
    fail=0
    echo "==> JavaScript"
    if command -v node >/dev/null 2>&1; then
      node --check web/app.js || fail=1
    else
      echo "    node not found, skipped"
    fi
    echo "==> Translations"
    if [ "$PY" = "uv" ]; then uv run python tools/check_i18n.py || fail=1
    else "$VENV/bin/python" tools/check_i18n.py || fail=1; fi
    echo "==> Python"
    if [ "$PY" = "uv" ]; then uv run python -m compileall -q src tools tests >/dev/null || fail=1
    else "$VENV/bin/python" -m compileall -q src tools tests >/dev/null || fail=1; fi
    echo "==> Workflows"
    # PyYAML is not a dependency of this project and will not become one for a syntax
    # check; if it happens to be there the check runs, otherwise it says so.
    if [ "$PY" = "uv" ]; then YCHK="uv run python"; else YCHK="$VENV/bin/python"; fi
    if $YCHK -c "import yaml" 2>/dev/null; then
      $YCHK - .github/workflows/*.yml <<'PYCHECK' || fail=1
import sys, yaml
for path in sys.argv[1:]:
    try:
        yaml.safe_load(open(path))
    except Exception as exc:
        print(f"  {path}: {exc}")
        raise SystemExit(1)
PYCHECK
    else
      echo "    PyYAML not installed, skipped"
    fi
    echo "==> Tests"
    for t in tests/test_*.py; do
      if [ "$PY" = "uv" ]; then uv run python "$t" >/dev/null || { echo "    $t failed"; fail=1; }
      else "$VENV/bin/python" "$t" >/dev/null || { echo "    $t failed"; fail=1; }; fi
    done
    if [ "$fail" -eq 0 ]; then echo; echo "All good."; else echo; echo "Problems found - see above." >&2; fi
    exit "$fail"
    ;;
  enrich)
    if [ ! -f .env ] || ! grep -q "^GITHUB_TOKEN=." .env 2>/dev/null; then
      echo "GITHUB_TOKEN missing in .env - see .env.example" >&2
      exit 1
    fi
    cmd enrich
    cmd refine-releases
    ;;
  build)
    # Everything the scheduled workflow does, minus the commit and the deploy. Takes
    # about twelve minutes, nearly all of it the GitHub enrichment. Without this full
    # chain an export is WORSE than the published file rather than newer: a database
    # that has not been enriched leaves every release and commit column empty.
    if [ ! -f .env ] || ! grep -q "^GITHUB_TOKEN=." .env 2>/dev/null; then
      echo "GITHUB_TOKEN missing in .env - see .env.example" >&2
      exit 1
    fi
    cmd sync
    cmd hacs-dates
    [ -d data/snapshots ] && cmd history-load || true
    [ -f data/stars/star_days.jsonl.gz ] && cmd load-stars || true
    cmd enrich
    cmd refine-releases
    cmd export --out web/data.json
    ;;
  serve)
    echo "==> Fetching data"
    cmd sync
    # Order matters: sync builds the repository list, history attaches to it.
    [ -d data/snapshots ] && cmd history-load || true
    [ -f data/stars/star_days.jsonl.gz ] && cmd load-stars || true
    echo "==> Export"
    cmd export --out web/data.json
    echo
    echo "==> Page running at http://localhost:8000  (stop with Ctrl-C)"
    if [ "$PY" = "uv" ]; then uv run python -m http.server -d web 8000
    else "$VENV/bin/python" -m http.server -d web 8000; fi
    ;;
  *) echo "Usage: ./run.sh [serve|check|build|sync|dates|enrich|bootstrap|export|stats|test]"; exit 1 ;;
esac
