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
  if [ "$PY" = "uv" ]; then uv run betterhacs "$@"; else "$VENV/bin/python" -m betterhacs.cli "$@"; fi
}

case "${1:-serve}" in
  sync)   cmd sync ;;
  export) cmd export --out web/data.json ;;
  stats)  cmd stats ;;
  serve)
    echo "==> Daten holen"
    cmd sync
    echo "==> Export"
    cmd export --out web/data.json
    echo
    echo "==> Seite laeuft auf http://localhost:8000  (Abbruch mit Strg-C)"
    if [ "$PY" = "uv" ]; then uv run python -m http.server -d web 8000
    else "$VENV/bin/python" -m http.server -d web 8000; fi
    ;;
  *) echo "Aufruf: ./run.sh [serve|sync|export|stats]"; exit 1 ;;
esac
