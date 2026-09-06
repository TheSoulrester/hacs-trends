# HACS Trends

### → **[thesoulrester.github.io/hacs-trends](https://thesoulrester.github.io/hacs-trends/)**

[![Collect and publish](https://github.com/TheSoulrester/hacs-trends/actions/workflows/sync.yml/badge.svg)](https://github.com/TheSoulrester/hacs-trends/actions/workflows/sync.yml)
[![Refresh star history](https://github.com/TheSoulrester/hacs-trends/actions/workflows/refresh-stars.yml/badge.svg)](https://github.com/TheSoulrester/hacs-trends/actions/workflows/refresh-stars.yml)

Which Home Assistant custom repositories are gaining ground — and which look abandoned.

A trend dashboard for all **4,193 repositories** in the [HACS](https://hacs.xyz) store.
Static site, collected twice a day by a GitHub Action, hosted on GitHub Pages. No server
to run, nothing to install.

> Not an official HACS project. It uses public data published by HACS, by Home
> Assistant's opt-in analytics, and by GitHub.

## What it answers

Seven questions rather than seven filters, because the interesting part is rarely one
number:

| | |
|---|---|
| **Gaining attention** | Most new stars in the period. Visibility, not use. |
| **Actually being used** | Installations that really run, from Home Assistant analytics. |
| **Rising for their size** | Percentage growth, so small projects are not buried. |
| **Real momentum** | Strong on both stars *and* installations, with both ranks shown. |
| **Ships reliably** | Releases published in the last year, next to commit counts. |
| **Possibly unmaintained** | How long since the last commit. A prompt to look, not a verdict. |
| **New in HACS** | Recently accepted into the store. |

Periods: 7 days, 30 days, quarter, year.

## What the numbers mean, and what they don't

This matters more than the feature list, so it is on the page as well as here.

- **Stars are exact for every period.** GitHub's star history endpoint gives daily
  counts back to a repository's creation, so the quarter and year windows are real, not
  estimated. What is counted is stars *given* in the period — GitHub does not report
  removed stars, so this is not a net change.
- **Installations come from opt-in analytics.** A large sample, not a headcount: good
  for ranking, useless for claiming exact user numbers. They exist for **integrations
  only** — dashboard cards, themes and templates are not reported. 2,101 of 3,248
  integrations with a domain are matched, and 43 domains are claimed by more than one
  repository, which are flagged rather than guessed.
- **The download counter is nearly useless.** Only 33% of repositories have one at all,
  because HACS installs from source when there are no release assets. It is shown as a
  secondary figure and gets no ranking of its own.
- **Installation and download trends have to accumulate.** Unlike stars they cannot be
  backfilled from anywhere, so those columns fill in over the first weeks and say so.
- **A missing value shows as a dash, never as a zero**, and those rows sort to the
  bottom whichever way you sort — an ascending sort should not fill the top with gaps.
- **"Possibly unmaintained" is a prompt, not a judgement.** A small, finished
  integration for a device with a stable API can be correct for years without a commit.

## How every figure is produced

Nothing here is estimated, modelled or smoothed. Every column comes from one of three
public sources, and this section says which one and what happens to it in between, so
you can check any number yourself.

**The three sources**

| Source | What it gives | Fetched |
|---|---|---|
| `data-v2.hacs.xyz/<category>/data.json` | The store itself: which repositories exist, in which category, their stars, description, manifest name, integration domain, last release version, open issues, last update | Twice a day, one request per category, no token |
| `analytics.home-assistant.io/custom_integrations.json` | Installation counts per integration domain, per version | Twice a day, one request, no token |
| GitHub GraphQL + the star history endpoint | Archived state, releases, commit counts, forks, licence, and the daily star series | Twice a day (~90 queries); the star history weekly (~8,400 requests) |
| The git history of [`hacs/default`](https://github.com/hacs/default) | The day each repository was accepted into HACS | Twice a day, a 5.7 MB clone, no token |

**Column by column**

| Column | Where it comes from |
|---|---|
| **Kind** | The category file the repository is listed in at `data-v2.hacs.xyz` — `integration`, `plugin` (dashboard card), `theme`, `template`, `python_script`, `appdaemon`, `netdaemon`. Nothing is inferred from the code. |
| **Stars** | The HACS dataset's own count, taken at collection time. |
| **Stars gained (7 d / 30 d / quarter / year)** | Summed from GitHub's star history endpoint, which returns weekly buckets each holding a seven-element array of daily counts, back to the repository's creation. The sum over the window is therefore exact, not interpolated. GitHub reports stars *given*, never stars removed, so this is a gross figure. |
| **Growth %** | Stars gained divided by the count at the **start** of the window, not the current one — a repository that doubled reports 100 %, not 50 %. Below 25 stars at the start no percentage is shown at all: with a corpus median of 13 stars, a percentage ranking would otherwise be a list of repositories that went from 2 stars to 4. |
| **Installations** | Home Assistant's opt-in analytics, matched to a repository by the integration domain in its `manifest.json`. Where two repositories claim the same domain the number is flagged as ambiguous rather than attributed to one of them (43 domains, currently). Integrations only. |
| **Installation growth** | Differenced from this project's own daily slices — analytics publishes today's figure, never a history, so this column can only fill in over time and says so on the page. |
| **Version adoption** | The share of reported installations running the release tag HACS names as newest. If that exact tag does not appear in the analytics data the column shows a dash, not a zero — an early version of this got 0.0 % for everything by picking the highest-looking key instead, which selected nightly builds with one install. |
| **Last commit** | The HACS dataset's `last_updated`. A 45-repository sample against the GitHub API showed this is exactly GitHub's `pushed_at`, not `updated_at` — the wording on the page follows that measurement. Shown as the distance from your own clock, so it stays right between collection runs. |
| **Status** (active / quiet / stale / dormant) | Days since that commit: under 90 active, under 365 quiet, under 730 stale, beyond that dormant. Archived repositories and ones GitHub no longer serves get their own state. The thresholds come from the measured distribution across all 4,193 repositories — median 55 days, P75 208, P90 689. |
| **Last release** | The newest release from GitHub GraphQL, ordered explicitly by creation date. Without that explicit ordering GitHub returns the *oldest* releases for a `last: N` query, which produced a plausible and entirely wrong table until it was checked. |
| **Releases / year** | Releases published in the last 365 days. The first pass fetches 30 releases per repository and a second pass re-queries the ones that hit that ceiling with 100, so the number is exact for all but the 52 repositories still at 100 — those are shown as `100+` rather than as a figure the data cannot support. |
| **Release rhythm** | Buckets on that same count: 12 or more continuous, 4 or more regular, 1 or more occasional, none in the year dormant, and never published a release at all shows as never. The thresholds are the corpus quartiles (median 4 a year, P75 13, P90 27), not round numbers. |
| **Commits / year and quarter** | GitHub GraphQL, counted on the default branch since a timestamp — not a rate, an actual count. |
| **Real momentum** | The percentile rank of star growth and of installation growth, ranked on the **lower** of the two, so a repository has to be strong in both. Both component ranks get their own column: a placement is never a black box. |
| **In HACS since** | The first commit that added the repository to the lists in `hacs/default` — exact back to 20 October 2019 and matching 4,171 of 4,193 repositories. The 22 without a date are HACS itself, which is not in its own list, and repositories renamed on GitHub since. Everything stamped with 20 October 2019 is shown as "since the start" rather than dated: that is the day the list was written from an older location, so those were already in HACS and the real date is gone. |
| **New in HACS** | Ranked by that acceptance date. The first daily slice a repository appears in is kept as a fallback for anything the list has not caught up with. |
| **Downloads** | The release asset counter from the HACS dataset. Only 33 % of repositories have one, because HACS installs from source when a release carries no assets. Shown, never ranked on. |
| **Rank number** | The position in the current view's full ranking, assigned before your search and filters are applied — so a search result also tells you where it stands. |

**When it runs, and what "today" means**

The collector runs twice a day. Star history is refreshed weekly, so a repository that
was starred yesterday may be up to seven days behind on the star columns while every
other figure is at most twelve hours old. The page footer names the day the data was
built.

**What is deliberately not measured**

Watchers (median 1, P90 8 across the corpus — too sparse to rank on), issue close rates
as a quality signal, anything from a repository's code or README, and anything about the
people behind a repository. There is no scoring formula that blends several figures into
one number: every ranking is one figure you can name, with the others shown next to it.

**Check it yourself**

Every daily slice is committed as text under `data/snapshots/`, and the star history as
`data/stars/star_days.jsonl.gz`. The exported file the page reads is `web/data.json`.
[PLAN.md](PLAN.md) documents each measurement in full, including the four assumptions
that turned out to be wrong.

## Running it yourself

```bash
git clone https://github.com/thesoulrester/hacs-trends.git
cd hacs-trends
./run.sh
```

That is the whole thing: the script finds a Python 3.10 or newer, sets up a virtual
environment, collects the data and serves the page on <http://localhost:8000>. It uses
`uv` if you have it and the system Python if you don't. No admin rights.

Individual steps, if you want them:

```bash
./run.sh check      # syntax, translations, workflows, tests - seconds, no token
./run.sh build      # everything the scheduled run does, ~12 min, needs a token
./run.sh sync       # HACS data and Home Assistant analytics
./run.sh dates      # acceptance dates from the git history of hacs/default
./run.sh enrich     # releases, commits, archived state (needs a token)
./run.sh export     # build web/data.json
./run.sh stats      # what is in the database
./run.sh test       # the collector's test suite
```

`check` is worth running before every push. It catches what typing breaks — invalid
JavaScript, a translation key that exists in one file and not the other, a placeholder
that no longer matches, a workflow that is no longer valid YAML — in a few seconds,
without a token or a network. What it cannot check is whether the page looks right: serve
`web/` and look at it.

`build` is the one to use before looking at local data. An `export` on its own writes
whatever the database currently holds, and a database that has never been enriched leaves
every release and commit column empty — the file is then *worse* than the published one,
not newer.

The enrichment and the star history need a GitHub token — a **classic personal access
token with no scopes ticked at all**. Everything read is public; the token only lifts
the rate limit from 60 requests an hour to 5,000. Put it in `.env`:

```
GITHUB_TOKEN=ghp_...
```

```bash
uv run hacs-trends enrich            # archived state, releases, commits, issues
uv run hacs-trends bootstrap-stars   # full star history, ~35 minutes, resumable
```

## How it stays up to date

Two scheduled workflows, both needing no configuration beyond the repository itself:

- **`sync.yml`**, twice a day — fetches the HACS dataset and Home Assistant analytics,
  enriches from GitHub, writes the day's slice, rebuilds the page and deploys it. Uses
  the automatic Actions token; about 90 GitHub queries.
- **`refresh-stars.yml`**, weekly — re-reads the star history for every repository
  (~8,400 requests, up to two hours). This one needs a personal access token in the
  `STAR_HISTORY_TOKEN` secret, because the automatic token is capped at 1,000 requests
  an hour.

### Where the history lives

Not in the database — that is a cache, rebuilt on every run. The truth is committed:

- `data/snapshots/YYYY-MM-DD.json.gz` — one slice a day, about 50 KB, roughly 18 MB a
  year. Text, diffable, and usable by anyone who wants the raw series.
- `data/stars/star_days.jsonl.gz` — the star history, refreshed weekly.

A committed SQLite file would have added its full size to the Git history on every
single run. A side effect of doing it this way: `first_seen` never has to be stored,
because it falls out of the first slice a repository appears in, so nothing can drift.

## Publishing your own copy

1. Push to a repository.
2. *Settings → Pages* → source **GitHub Actions**.
3. *Settings → Actions → General → Workflow permissions* → **Read and write**, so the
   run can commit the daily slice.
4. *Settings → Secrets → Actions* → add `STAR_HISTORY_TOKEN` (only needed for the weekly
   star refresh).
5. *Actions → Collect and publish → Run workflow* once to prime it.

The site appears at `https://<account>.github.io/<repo>/` after the first successful
deployment — before that the address returns 404, because the Pages site does not exist
yet. For this repository that is
<https://thesoulrester.github.io/hacs-trends/>.

For a custom domain, put the hostname in `web/CNAME` and point a DNS `CNAME` record at
`<account>.github.io`. GitHub issues the certificate. No hosting needed.

## Translating

English is the source of truth and the per-key fallback, so a half-finished translation
is useful immediately and never leaves a blank interface.

1. Copy `web/i18n/en.json` to `web/i18n/<code>.json`.
2. Translate the values. Leave the keys and the `{placeholders}` alone.
3. Add the language to `LANGS` at the top of `web/app.js`.
4. Open a pull request.

`python tools/check_i18n.py` reports how complete each file is and fails on keys that
exist nowhere else or placeholders that do not match.

## Sources

- HACS dataset: `https://data-v2.hacs.xyz/<category>/data.json`
- Home Assistant analytics: `https://analytics.home-assistant.io/custom_integrations.json`
- GitHub GraphQL and the star history endpoint

[PLAN.md](PLAN.md) records the design decisions and, more usefully, the measurements
that overturned several of them.
