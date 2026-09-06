#!/usr/bin/env bash
# Ein Befehl, der ueberall laeuft: ./run.sh
#
# Sucht sich selbst einen brauchbaren Python, legt eine virtuelle Umgebung an,
# installiert die Abhaengigkeiten, holt die Daten und startet die Seite.
# Braucht kein uv, kein Homebrew, keine Adminrechte.

set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY=""

find_python() {
  # uv bringt seinen eigenen Python mit und ist der bequemste Weg, wenn vorhanden.
  if command -v uv >/dev/null 2>&1; then echo "uv"; return; fi
  # Sonst der neueste passende System-Python. SQLAlchemy braucht mindestens 3.10.
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
Kein Python 3.10 oder neuer gefunden.

Der einfachste Weg, das zu aendern, ohne Adminrechte und ohne das System
anzufassen — uv installiert sich in dein Benutzerverzeichnis und bringt
seinen eigenen Python mit:

    curl -LsSf https://astral.sh/uv/install.sh | sh

Danach ein neues Terminal oeffnen und hier nochmal ./run.sh aufrufen.
Alternativ ein aktuelles Python von python.org installieren.
MSG
  exit 1
fi

echo "==> Python: $PY"

if [ "$PY" = "uv" ]; then
  uv sync --quiet
  RUN="uv run"
else
  if [ ! -x "$VENV/bin/python" ]; then
    echo "==> Lege virtuelle Umgebung an ($VENV)"
    "$PY" -m venv "$VENV"
  fi
  echo "==> Installiere Abhaengigkeiten"
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
    if [ "$PY" = "uv" ]; then uv run python tests/test_bootstrap.py
    else "$VENV/bin/python" tests/test_bootstrap.py; fi
    ;;
  export) cmd export --out web/data.json ;;
  stats)  cmd stats ;;
  dates)  cmd hacs-dates ;;
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
    echo "==> Daten holen"
    cmd sync
    # Order matters: sync builds the repository list, history attaches to it.
    [ -d data/snapshots ] && cmd history-load || true
    [ -f data/stars/star_days.jsonl.gz ] && cmd load-stars || true
    echo "==> Export"
    cmd export --out web/data.json
    echo
    echo "==> Seite laeuft auf http://localhost:8000  (Abbruch mit Strg-C)"
    if [ "$PY" = "uv" ]; then uv run python -m http.server -d web 8000
    else "$VENV/bin/python" -m http.server -d web 8000; fi
    ;;
  *) echo "Usage: ./run.sh [serve|build|sync|dates|enrich|bootstrap|export|stats|test]"; exit 1 ;;
esac
