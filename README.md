# betterHACs

Trend- und Wartungs-Dashboard für [HACS](https://hacs.xyz)-Repositories.

Zeigt für alle rund 4.200 HACS-Repositories, welche gerade an Sternen und Verbreitung
zulegen — und welche seit langem nicht mehr gepflegt werden.

> Kein offizielles HACS-Projekt. Nutzt öffentlich verfügbare Daten von HACS,
> der Home-Assistant-Analytik und GitHub.

## Datenquellen

| Quelle | Was | Token |
|---|---|---|
| `data-v2.hacs.xyz/<kategorie>/data.json` | Repo-Stammdaten, Sterne, Downloads, Version | nein |
| `analytics.home-assistant.io/custom_integrations.json` | laufende Installationen je Integration | nein |
| GitHub GraphQL | `pushed_at`, Release-Datum, `isArchived`, Lizenz | ja |
| GitHub REST Stargazers | einmaliger Bootstrap exakter Stern-Zeitstempel | ja |

Die ersten beiden decken den kompletten Bestand mit acht HTTP-Requests ab.

## Loslegen

```bash
uv sync
cp .env.example .env        # GITHUB_TOKEN eintragen (nur für Anreicherung nötig)
uv run betterhacs sync
uv run betterhacs stats
```

Ohne Netzzugang zu den Quellen lässt sich gegen heruntergeladene Fixtures arbeiten:

```bash
uv run betterhacs sync --fixtures data/fixtures
```

## Aufbau

Der Collector schreibt in eine SQLite-Datenbank; daraus wird eine statische JSON
exportiert, die eine einzelne HTML-Seite auf GitHub Pages lädt. Kein Server, kein Hosting.

Siehe [PLAN.md](PLAN.md) für den vollständigen Entwurf inklusive der Messwerte,
auf denen die Schwellwerte beruhen.
