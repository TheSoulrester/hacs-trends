> **Archiv.** Dieser Entwurf stammt aus der Zeit, als das Projekt betterHACs hiess,
> und ist durch PLAN.md ersetzt. Er bleibt erhalten, weil er festhaelt, welche
> Annahmen spaeter durch Messungen widerlegt wurden.

# betterHACs — Trend- und Wartungs-Dashboard für HACS

Entwurf, Stand 2026-09-05. Noch keine Zeile Code geschrieben.

**Ziel:** Eine öffentlich erreichbare Webseite, auf der die Home-Assistant-Community
HACS-Repositories nach kurzfristigen Trends (Sterne, Verbreitung, Downloads) sortieren
und filtern kann — und auf der sichtbar wird, welche Projekte offenbar nicht mehr
gepflegt werden.

---

## 1. Was sich gegenüber der ursprünglichen Vorgabe geändert hat

Die ursprüngliche Skizze (von Gemini) ging von falschen Voraussetzungen aus.
Geprüft am 2026-09-05:

| Annahme in der Vorgabe | Realität |
|---|---|
| `hacs/default/master/repositories.json` als Repo-Liste | **404.** Die Liste liegt als eine Datei je Kategorie vor, jeweils ein JSON-Array aus `"owner/repo"`. |
| Alle Metriken müssen einzeln über die GitHub-API geholt werden | **Nein.** HACS veröffentlicht seinen kompletten aufbereiteten Datensatz. 7 Requests statt ~5.000. |
| GitHub-Token zwingend nötig | Für die Basisdaten **nicht**. Nur für die optionale Anreicherung und den einmaligen Bootstrap. |
| Rate-Limit ist das zentrale Problem | Ist es nicht mehr. Das zentrale Problem ist, dass es **keine historischen Daten gibt** — die müssen wir selbst aufbauen. |

### Umfang (gezählt am 2026-09-05)

| Kategorie | Repos |
|---|---|
| integration | 3.262 |
| plugin | 772 |
| theme | 107 |
| appdaemon | 56 |
| template | 11 |
| python_script | 9 |
| netdaemon | 4 |
| **aktiv gesamt** | **4.221** |
| removed (Blacklist) | 447 |
| critical | 1 |

---

## 2. Datenquellen

### 2.1 HACS-Datensatz — Hauptquelle, kein Token

`https://data-v2.hacs.xyz/<kategorie>/data.json`

Ein Request je Kategorie, Schlüssel ist die **GitHub-Repo-ID** (stabil auch bei Umbenennung).
Beispiel-Eintrag verbatim:

```json
"231829137": {
  "manifest": { "name": "Noctis" },
  "description": "🐵 Dark Blue Theme for Home Assistant",
  "full_name": "aFFekopp/noctis",
  "stargazers_count": 307,
  "downloads": 101,
  "open_issues": 1,
  "last_updated": "2026-05-08T19:21:18Z",
  "last_commit": "5515804",
  "last_version": "3.3.5",
  "topics": ["dark-theme", "home-assistant-theme"],
  "etag_repository": "W/\"9814be…\"",
  "etag_releases": "W/\"96e07f…\"",
  "last_fetched": 1786896468.753937
}
```

Integrationen haben zusätzlich `domain` und `manifest_name` — das ist der Schlüssel zur
Analytics-Quelle unten.

Weitere nützliche Endpunkte derselben Basis:
- `/<kategorie>/repositories.json` — reine Namensliste
- `/removed/data.json` — mit `removal_type` und `reason` (u.a. `archived`, `deprecated`, `replaced`)
- `/critical/data.json` — Repos mit kritischen Problemen

Kategorien mit Datensatz: `integration`, `plugin`, `theme`, `template`, `python_script`,
`appdaemon`. **`netdaemon` hat kein Schema** in HACS — die 4 Repos vermutlich abgekündigt,
beim ersten Sync verifizieren.

Der Endpunkt unterstützt `If-None-Match`/ETag (HACS nutzt das selbst). Wir tun das auch:
unveränderte Kategorien kosten dann nichts.

### 2.2 Home-Assistant-Analytik — die ehrliche Verbreitungszahl

`https://analytics.home-assistant.io/custom_integrations.json` — ein Request, kein Token.

```json
"hacs":   { "total": 383740, "versions": { "1.32.1": 1515, "2.0.5": 364702 } },
"dahua":  { "total": 4537,   "versions": { "0.5.0": 77, "0.9.86": 788 } }
```

Das sind **tatsächlich laufende Installationen**, verknüpfbar über `domain`.
Zusätzlich die Versionsverteilung — daraus lässt sich ablesen, wie schnell eine neue
Version bei den Nutzern ankommt.

Einschränkungen, die ins UI gehören:
- Opt-in-Stichprobe (~677.000 meldende Installationen gesamt), keine Absolutwahrheit. Für
  **Rangfolgen** sehr gut, für Aussagen wie „X hat genau N Nutzer" nicht.
- Gibt es **nur für Integrationen**. Plugins, Themes, Templates tauchen nicht auf.
- Offene empirische Frage: wie viele der 3.262 Integrationen finden überhaupt einen
  Analytics-Treffer? Muss beim ersten Sync gemessen und im UI ausgewiesen werden.

### 2.3 GitHub GraphQL — Anreicherung (entschieden: ja)

~45 Abfragen für alle 4.221 Repos (100 aliasierte `repository`-Felder je Query), unter
einer Minute, im GitHub-Actions-Kontext mit dem automatisch bereitgestellten Token.

Liefert die Felder, die HACS **nicht** hat und die für die Wartungs-Ampel entscheidend sind:

| Feld | Warum |
|---|---|
| `isArchived` | Stärkstes Verwaisungs-Signal überhaupt, fehlt in den HACS-Daten komplett. **Nach dem Wegfall von `pushedAt` der eigentliche Grund für diesen Schritt.** |
| ~~`pushedAt`~~ | **Nicht nötig — Annahme widerlegt.** Der Entwurf ging davon aus, `last_updated` sei GitHubs `updated_at` und damit als Aktivitätsmaß untauglich. Eine Stichprobe von 45 Repos gegen die GitHub-API zeigt: HACS liefert dort bereits exakt `pushed_at`, sekundengenau (geprüft u.a. an `rospogrigio/localtuya`: HACS `2026-01-29T11:04:59Z`, GitHub `pushed_at` identisch, `updated_at` dagegen `2026-09-04`). Die Ampel steht also von Anfang an auf echten Commit-Daten. |
| `latestRelease.publishedAt` | HACS liefert die Versionsnummer, aber kein Release-Datum. Erst damit lässt sich Release-Alter von Commit-Alter trennen — ein Repo, das committet aber seit zwei Jahren nichts veröffentlicht, ist ein eigener Fall. |
| `latestRelease { publishedAt, tagName }` | Release-Alter getrennt von Commit-Alter. |
| `licenseInfo`, `forkCount`, `primaryLanguage` | Kontext, günstig mitzunehmen. |
| `isFork`, `nameWithOwner` | Umbenennungen und Forks erkennen. |

### 2.4 GitHub Stargazers — einmaliger Bootstrap (entschieden: ja)

REST, `Accept: application/vnd.github.v3.star+json`, Stargazer-Liste **von hinten**
paginiert bis `starred_at` älter als 35 Tage. Damit sind die Stern-Deltas ab Tag 1 exakt,
statt erst nach 30 Tagen Laufzeit.

- Kosten: ~5.000–6.000 Requests, also ~1,5–2 h unter dem 5.000/h-Limit. **Läuft genau einmal.**
- Muss resumierbar sein: Fortschritt je Repo in der DB, `X-RateLimit-Remaining` auswerten,
  bei Erschöpfung bis `X-RateLimit-Reset` schlafen, sekundäre Rate-Limits abfangen.
- Wichtige Einschränkung: das misst „aktuell gehaltene Sterne, die in den letzten 7/30 Tagen
  vergeben wurden". Entfernte Sterne sind darin unsichtbar. Die späteren Snapshot-Deltas
  messen dagegen die **Netto**-Änderung. Die zwei Zahlen sind minimal verschieden — der
  Übergang von Bootstrap- auf Snapshot-Werte muss in der DB markiert und im UI kenntlich sein.
- Gilt **nur für Sterne.** Download- und Installations-Trends lassen sich nicht bootstrappen,
  die wachsen zwingend über die Laufzeit.

---

## 3. Datenmodell (SQLite)

Schlüssel ist überall die GitHub-Repo-ID, nie `full_name` (Umbenennungen).

```
repos            id, category, full_name, description, manifest_name, domain,
                 topics_json, first_seen, last_seen, is_removed, removal_type,
                 removal_reason, is_critical

repo_github      repo_id, pushed_at, released_at, latest_tag, is_archived, is_fork,
                 license, fork_count, primary_language, fetched_at

snapshots        repo_id, taken_at (Tagesgranularität), stars, downloads,
                 open_issues, last_updated, last_version
                 PK (repo_id, taken_at)

installs         domain, taken_at, total
installs_version domain, taken_at, version, count      -- optional, für Adoptionskurven

star_events      repo_id, starred_at                   -- nur aus dem Bootstrap, ~35 Tage

sync_runs        id, started_at, finished_at, source, status, counts_json, notes
```

**Delta-Berechnung:** `wert_jetzt − wert(nächstgelegener Snapshot ≤ jetzt−7d, Toleranz ±1 Tag)`.
Fehlt ein ausreichend alter Snapshot, ist das Ergebnis `NULL` — und die UI zeigt „—" statt
einer 0. Eine 0 wäre eine Lüge.

**Größe:** 4.221 Repos × 365 Tage ≈ 1,5 Mio. Zeilen/Jahr, wenige zehn MB. Unkritisch.

---

## 4. Auswertung: getrennte Ranglisten, kein kombinierter Score

Entschieden: **kein zusammengerechneter Trend-Score.** Ein einzelner Wert aus Sternen,
Downloads und Installationen suggeriert eine Objektivität, die er nicht hat — die drei
Größen messen verschiedene Dinge und haben verschiedene Datenqualität. Stattdessen klar
benannte, getrennte Sichten auf denselben Datenbestand:

| Sicht | Sortierung | Deckung |
|---|---|---|
| **Sterne-Trend** | Δ Sterne 7 d / 30 d, absolut und in % | alle 4.221 |
| **Verbreitung** | Installationen laut HA-Analytik, Bestand und Δ 7 d / 30 d | nur Integrationen |
| **Downloads** | Δ Release-Downloads 7 d / 30 d | nur Repos mit Release-Assets |
| **Neu in HACS** | `first_seen` innerhalb der letzten N Tage | alle |
| **Wartungszustand** | Alter des letzten Pushes / Releases | alle |

Kategorie-Filter und Freitextsuche sind in jeder Sicht verfügbar, nicht nur in einer.

Zwei Darstellungsregeln, die über die Seriosität der Seite entscheiden:
- **Prozentuales Wachstum gleichberechtigt neben absolutem.** Nach absoluten Zuwächsen
  sortiert stehen dauerhaft dieselben Großprojekte oben; das ist kein Trend, das ist Größe.
- **„Kein Zähler" ≠ „0".** Repos ohne Release-Assets haben keinen Download-Wert. Sie als
  0 anzuzeigen wäre falsch und würde sie in jeder Sortierung nach unten drücken.

---

## 5. Wartungs-Ampel

Der Schwellwert wird **datengetrieben** festgelegt, nicht geraten: erster Schritt nach dem
ersten vollständigen Sync ist die Verteilung von `pushed_at` über alle 4.221 Repos
(Median, Quartile, Dezile). Die Grenzen richten sich dann an Perzentilen aus.

Startvorschlag zur Diskussion nach der Messung:

| Stufe | Kriterium |
|---|---|
| 🟢 aktiv | letzter Push < 90 Tage |
| 🟡 ruhig | 90–365 Tage |
| 🟠 lange still | > 365 Tage |
| 🔴 aufgegeben | `isArchived`, oder in HACS `removed`/`critical`, oder > 730 Tage |

**Die wichtigste Einschränkung, und sie gehört sichtbar ins UI:** „lange kein Commit" heißt
nicht „kaputt". Eine kleine, fertige Integration für ein Gerät mit stabiler API kann
jahrelang unverändert korrekt laufen. Eine Ampel, die solche Projekte als schlecht markiert,
schadet ihnen — Leute installieren sie dann nicht mehr, obwohl sie funktionieren. Die Ampel
ist ein **Hinweis zum Nachschauen**, kein Qualitätsurteil, und muss auch so beschriftet sein.

Belastbarere Signale als das reine Commit-Alter, die wir haben:
- `isArchived` — eindeutig
- HACS `removed` mit `removal_type` — die Betreiber haben aktiv entschieden
- offene Issues im Verhältnis zur Sternzahl — viele Issues bei stillem Repo ist aussagekräftig
- kein Release, nur Commits — HACS-Installation ist dann fragiler

---

## 6. Bauform: A gegen B

### Variante A — statisch: GitHub Action + GitHub Pages

Der Collector läuft als geplante GitHub Action (2×/Tag), schreibt den Tages-Snapshot als
komprimiertes JSONL ins Repo und exportiert eine fertig aggregierte `docs/data.json`.
Das Frontend ist eine einzelne HTML-Datei auf GitHub Pages, die diese JSON lädt und
clientseitig sortiert, filtert und sucht.

| | |
|---|---|
| Betriebskosten | 0 € |
| Betriebsaufwand | keiner, keine Server, keine Datenbank im Betrieb, kein Backup |
| Öffentlich erreichbar | sofort, über `<user>.github.io/betterHACs` |
| Payload | ~4.200 Zeilen, geschätzt 1,5–2 MB roh, ~400 KB gzip — für Tabulator mit Virtualisierung unproblematisch |
| Historie | im Git versioniert und für jeden nachvollziehbar |
| Community-tauglich | maximal: forkbar, PRs möglich, keine Zugangsdaten nötig |
| Grenzen | keine serverseitigen Abfragen; beliebige Zeitfenster und lange Verlaufskurven gehen nicht ohne wachsende Payload; Watchlist nur per localStorage |

Zur Historie im Repo: **JSONL pro Tag, nicht eine committete SQLite-Datei.** Textzeilen
diffen und komprimieren in Git gut, eine binäre DB bläht die History bei jedem Lauf auf.
Die SQLite wird beim Lauf aus den JSONL aufgebaut bzw. aus dem Actions-Cache geholt.

### Variante B — FastAPI + SQLite

Derselbe Collector, aber daneben ein Server mit REST-API: `/api/repos` mit serverseitigem
Filtern, Sortieren und Paginieren, `/api/repos/{id}/history` für Verlaufskurven, `/api/stats`.

| | |
|---|---|
| Betriebskosten | Hosting nötig (Fly.io, Railway, eigener Server, NAS) |
| Betriebsaufwand | Prozess, Updates, DB-Backup, Monitoring |
| Stärke | beliebige Zeitfenster, Verlaufsdiagramme über Monate ohne Payload-Problem, später Nutzerkonten und Watchlists |
| Grenze | für den heutigen Funktionsumfang schlicht nicht nötig |

### Empfehlung

**A jetzt bauen, B als offene Option — mit gemeinsamem Kern.** `sources/`, `db.py` und
`metrics.py` sind in beiden Varianten identisch. A ergänzt `export.py`, B ergänzt `api.py`.
Ein späterer Wechsel heißt: FastAPI vor dieselbe SQLite setzen. Kein Rewrite, kein
Datenverlust.

Für das erklärte Ziel „öffentlich für die HA-Community" spricht A zusätzlich stark: keine
Zugangsdaten, kein Ausfallrisiko, keine laufenden Kosten, und die Seite überlebt es, wenn
das Interesse nachlässt.

---

## 7. Projektstruktur

```
betterHACs/
├── pyproject.toml              # uv-verwaltet
├── .python-version
├── .env.example                # GITHUB_TOKEN (nur Anreicherung + Bootstrap)
├── README.md
├── src/hacs_trends/
│   ├── config.py
│   ├── db.py                   # SQLAlchemy-Modelle, Schema-Migration
│   ├── sources/
│   │   ├── hacs.py             # data-v2.hacs.xyz, ETag-Handling, Schema-Validierung
│   │   ├── analytics.py        # custom_integrations.json
│   │   ├── github_graphql.py   # Anreicherung
│   │   └── github_stars.py     # einmaliger Bootstrap, resumierbar
│   ├── metrics.py              # Deltas, Perzentile, Ampel-Einstufung
│   ├── sync.py                 # Orchestrierung + CLI
│   ├── export.py               # docs/data.json (Variante A)
│   └── api.py                  # FastAPI (Variante B, später)
├── web/
│   ├── index.html              # Tailwind CDN + Tabulator
│   └── app.js
├── data/snapshots/YYYY-MM-DD.jsonl.gz
├── .github/workflows/sync.yml
└── tests/
```

Start mit `uv`:
```
uv sync
uv run hacs-trends sync            # HACS + Analytics + GraphQL
uv run hacs-trends bootstrap-stars # einmalig, läuft ~2 h
uv run hacs-trends export
```

---

## 8. Umsetzungsreihenfolge

1. Gerüst, `uv`, DB-Schema
2. HACS-Quelle: 6 Kategorien + `removed` + `critical` einlesen, erster Snapshot.
   **Verifikation:** Anzahl gegen die Kategorielisten prüfen (4.221 erwartet), `netdaemon` klären
3. HA-Analytik anbinden, über `domain` joinen. **Trefferquote messen und dokumentieren**
4. GraphQL-Anreicherung
5. Verteilungsanalyse `pushed_at` → Ampel-Schwellen festlegen
6. Stargazer-Bootstrap (einmalig, resumierbar)
7. Delta-Berechnung + statischer Export
8. Frontend
9. GitHub Action + Pages
10. **Verifikation:** Stichproben gegen die GitHub-Weboberfläche, Plausibilität der Deltas,
    Vollzähligkeit der Kategorien

---

## 9. Risiken und offene Punkte

- **`data-v2.hacs.xyz` ist HACS' internes Format**, keine zugesicherte öffentliche API. Der
  Wechsel v1 → v2 hat bereits stattgefunden. Absicherung: Schema-Validierung bei jedem Sync,
  und bei Abweichung **lauter Abbruch statt stiller Fehldaten**.
- **Fair use.** ETag/`If-None-Match` nutzen, aussagekräftigen User-Agent setzen, maximal
  2–4 Läufe pro Tag. Die Quelle wird von einem Community-Projekt bezahlt.
- **Analytics ist eine Stichprobe** und deckt nur Integrationen ab. Muss im UI stehen.
- **Downloads-Zähler ist unzuverlässig** (HACS hat dazu selbst offene Bugs, u.a. bei Repos
  mit mehreren Release-Assets). Als sekundäre Metrik kennzeichnen.
- **Umbenennungen und Löschungen**: GitHub-ID als Schlüssel fängt das ab; verschwundene
  Repos nicht löschen, sondern als `last_seen` markieren.
- **Abgrenzung**: Wenn die Seite öffentlich ist, muss klar draufstehen, dass sie **kein
  offizielles HACS-Projekt** ist, und die Quellen müssen genannt werden.
- **Sandbox-Hinweis für die Entwicklung:** `data-v2.hacs.xyz` und
  `analytics.home-assistant.io` sind aus der Cowork-Umgebung heraus nicht erreichbar
  (Egress-Sperre); erreichbar sind nur `raw.githubusercontent.com` und `api.github.com`.
  Live-Tests laufen also auf dem Mac direkt oder in der GitHub Action.

---

## 10. Perspektive „in HACS integrieren"

Realistisch, aber nicht als Fork von HACS. Das Datenproblem ist nicht, dass HACS keine
Trendanzeige hat — es ist, dass **niemand die Historie veröffentlicht**. HACS publiziert nur
den jeweils aktuellen Stand.

Genau diese Lücke füllt dieses Projekt: eine öffentliche, versionierte Snapshot-Historie des
HACS-Bestandes. Wenn die über Monate stabil läuft, ist der plausible Weg nach vorn:

1. Seite öffentlich betreiben und in der HA-Community bekannt machen
2. Die Snapshot-Historie als eigenständige, stabile Datenquelle anbieten (z. B. ebenfalls
   über GitHub Pages) — dann kann sie jeder nutzen, auch HACS selbst
3. Erst dann eine Trendspalte im HACS-Dashboard vorschlagen, mit fertigem Datenlieferanten
   im Rücken statt als reine Feature-Idee

Ein HA-Custom-Panel, das die öffentliche JSON anzeigt, wäre als Zwischenschritt jederzeit
nachrüstbar — es hängt an derselben Datei wie die Webseite.
