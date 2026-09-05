"""Zentrale Konfiguration. Alles über Umgebungsvariablen, nichts hartkodiert."""

from __future__ import annotations

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

USER_AGENT = "betterHACs/0.1 (+https://github.com/hacs-trends; HACS trend dashboard)"


@dataclass(frozen=True)
class Config:
    db_path: Path
    fixtures: Path | None
    github_token: str | None

    @property
    def has_token(self) -> bool:
        return bool(self.github_token)


def load_config() -> Config:
    db = os.getenv("BETTERHACS_DB", "data/betterhacs.db")
    fixtures = os.getenv("BETTERHACS_FIXTURES") or None
    return Config(
        db_path=(ROOT / db) if not Path(db).is_absolute() else Path(db),
        fixtures=(ROOT / fixtures) if fixtures else None,
        github_token=os.getenv("GITHUB_TOKEN") or None,
    )
