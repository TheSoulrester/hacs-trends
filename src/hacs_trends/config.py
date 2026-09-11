"""Zentrale Konfiguration. Alles über Umgebungsvariablen, nichts hartkodiert."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]

# HACS-Kategorien mit veröffentlichtem Datensatz.
# netdaemon hat in der HACS-Codebasis kein Validierungsschema, liefert aber Daten (4 Repos)
# — deshalb hier bewusst enthalten, aber gesondert behandelt.
CATEGORIES = (
    "integration",
    "plugin",
    "theme",
    "template",
    "python_script",
    "appdaemon",
    "netdaemon",
)

# Kategorien, für die HACS ein Schema pflegt. Alles andere wird toleranter validiert.
SCHEMA_CATEGORIES = frozenset(
    {"integration", "plugin", "theme", "template", "python_script", "appdaemon"}
)

HACS_DATA_BASE = "https://data-v2.hacs.xyz"
# Die kuratierten Kategorielisten — nur fuer den Abgleich, siehe fetch_default_lists.
HACS_DEFAULT_BASE = "https://raw.githubusercontent.com/hacs/default/master"
HA_ANALYTICS_URL = "https://analytics.home-assistant.io/custom_integrations.json"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_API_BASE = "https://api.github.com"

# A rank arrow (up/down against yesterday) is drawn only when a repository moved at
# least this many places. Deep in a list a single star jumps a whole block of tied
# repositories; below 3 the arrows mostly report that. Measured on 21 days of real star
# history, 30-day window: 1-2 arrows a day among the top 25 at 3, practically none at 5.
# Overridable without a commit through the repository variable of the same name
# (Settings -> Secrets and variables -> Actions -> Variables), see sync.yml.
RANK_ARROW_MIN_DEFAULT = 3

USER_AGENT = "betterHACs/0.1 (+https://github.com/hacs-trends; HACS trend dashboard)"


@dataclass(frozen=True)
class Config:
    db_path: Path
    fixtures: Path | None
    github_token: str | None
    rank_arrow_min: int = RANK_ARROW_MIN_DEFAULT

    @property
    def has_token(self) -> bool:
        return bool(self.github_token)


def _rank_arrow_min() -> int:
    """HACS_TRENDS_RANK_ARROW_MIN, or the default when unset, empty or not a whole number
    of at least 1. An unset repository variable arrives in the workflow as an empty
    string, which is the normal case and not worth a warning."""
    raw = (os.getenv("HACS_TRENDS_RANK_ARROW_MIN") or "").strip()
    if not raw:
        return RANK_ARROW_MIN_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        logging.getLogger(__name__).warning(
            "HACS_TRENDS_RANK_ARROW_MIN=%r is not a whole number >= 1 - using %d.",
            raw, RANK_ARROW_MIN_DEFAULT,
        )
        return RANK_ARROW_MIN_DEFAULT
    return value


def load_config() -> Config:
    db = os.getenv("HACS_TRENDS_DB", "data/hacs_trends.db")
    fixtures = os.getenv("HACS_TRENDS_FIXTURES") or None
    return Config(
        db_path=(ROOT / db) if not Path(db).is_absolute() else Path(db),
        fixtures=(ROOT / fixtures) if fixtures else None,
        github_token=os.getenv("GITHUB_TOKEN") or None,
        rank_arrow_min=_rank_arrow_min(),
    )
