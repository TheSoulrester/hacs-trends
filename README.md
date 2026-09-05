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
| GitHub GraphQL | `isArchived`, Release-Datum, Lizenz, Fork-Zahl | ja |
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

## Veröffentlichen auf GitHub Pages

Der Workflow in `.github/workflows/sync.yml` erledigt alles selbst — er braucht kein
eigenes Token, das automatische `GITHUB_TOKEN` von Actions genügt.

1. Repository auf GitHub anlegen und pushen.
2. Unter *Settings → Pages* als Quelle **GitHub Actions** wählen.
3. Unter *Settings → Actions → General* bei *Workflow permissions* **Read and write**
   setzen, damit der Lauf die Tagesscheibe committen darf.
4. Einmal *Actions → Daten holen und veröffentlichen → Run workflow* auslösen.

Danach läuft der Sync zweimal täglich von allein. Die Seite liegt unter
`https://<account>.github.io/<repo>/`.

### Eigene Subdomain

Eine Datei `web/CNAME` mit dem gewünschten Namen anlegen, zum Beispiel:

```
hacs.beispiel.de
```

Dazu beim DNS-Anbieter einen CNAME-Eintrag von `hacs.beispiel.de` auf
`<account>.github.io` setzen. GitHub stellt das Zertifikat automatisch aus.
Eigenes Hosting ist dafür nicht nötig.

### Wo die Historie lebt

Nicht in der Datenbank — die ist nur ein Cache und wird bei jedem Lauf neu aufgebaut.
Die Wahrheit sind die Tagesscheiben unter `data/snapshots/`, je Tag eine komprimierte
JSON von rund 50 KB. Das sind etwa 18 MB im Jahr, dafür ist die komplette Historie
versioniert, nachvollziehbar und von jedem nachnutzbar.
