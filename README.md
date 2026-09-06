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
./run.sh sync       # HACS data and Home Assistant analytics
./run.sh export     # build web/data.json
./run.sh stats      # what is in the database
./run.sh test       # the collector's test suite
```

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
