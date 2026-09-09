# HACS Trends

### → **[thesoulrester.github.io/hacs-trends](https://thesoulrester.github.io/hacs-trends/)**

[![Collect and publish](https://github.com/TheSoulrester/hacs-trends/actions/workflows/sync.yml/badge.svg)](https://github.com/TheSoulrester/hacs-trends/actions/workflows/sync.yml)
[![Refresh star history](https://github.com/TheSoulrester/hacs-trends/actions/workflows/refresh-stars.yml/badge.svg)](https://github.com/TheSoulrester/hacs-trends/actions/workflows/refresh-stars.yml)

**Which Home Assistant custom integrations are alive — and which have quietly been
abandoned.**

## What this is

[HACS](https://hacs.xyz) is where Home Assistant users find the community-made
extras: integrations for devices Home Assistant does not support out of the box,
dashboard cards, themes. There are over four thousand of them, nearly all written by
volunteers in their spare time.

The store gives you a list and a search box. What it cannot tell you is which of those
projects still has somebody looking after it. Some are polished and updated weekly.
Some have not been touched since 2021 and will break the next time Home Assistant
changes something. From the store page, both look the same.

This page watches all 4,193 of them and asks the same few questions twice a day: is
anyone starring it, is anyone actually running it, has the code been touched lately,
do releases still come out. Then it ranks them by the answers.

It is an ordinary web page. Nothing to install, no account, no cookies, no tracking.
Open the link.

> Not an official HACS project. It only uses information that HACS, Home Assistant and
> GitHub already publish openly.

## How to use it

**Pick a question on the left.** There are seven, and each is a different way of being
interesting. There is deliberately no single "best" score that mixes them together —
that would hide the reason a project is near the top.

| Question | What it ranks by |
|---|---|
| **Gaining attention** | Most new stars in the chosen period. People noticing it. |
| **Actually being used** | Installations that really run, from Home Assistant's own statistics. |
| **Rising for their size** | Growth in percent, so a small project going from 40 to 90 is not buried under a big one that added the same number. |
| **Gaining and in use** | Climbing in stars *and* installations at the same time. The hardest list to get onto. |
| **Ships reliably** | How many releases came out in the last year. |
| **Possibly unmaintained** | How long since anyone touched the code. |
| **New in HACS** | Recently accepted into the store. |

**Choose a period at the top** — 7 days, 30 days, a quarter or a year. It changes what
"new stars" and "growth" mean. A quiet project can look impressive over seven days and
unremarkable over a year, which is worth knowing before you install it.

**Search for anything.** Type a device, a brand, a manufacturer — `skoda`, `heat pump`,
`solar`. It looks through repository names, the author, the description and the GitHub
topics, so it finds projects that never mention your word in their title. Several words
all have to match, but they can sit anywhere: `skoda connect` finds a project called
MySkoda. If one of your words matches nothing at all it is dropped rather than emptying
the whole list, and the bar at the bottom tells you which word it ignored.

The suggestions that drop down while you type are narrower on purpose — names and
addresses only. That list is for when you already know which project you want.

**Narrow it down** with the chips on the left: by type (integration, dashboard card,
theme…) and by how regularly the project publishes releases.

**Every row** shows the project's name and author, what it does, its newest version,
and the figures for the question you picked. The number on the far left is its place in
the full ranking — and it stays put when you search, so finding something at 412 tells
you something that finding it at 1 would not.

## Reading the numbers honestly

This is the part that matters most, so it is on the page itself as well as here.

- **Stars are not users.** A star is a bookmark. It means someone found the project
  interesting enough to remember, not that they run it. Stars are also only ever added
  in these figures — GitHub does not report when somebody removes one.
- **Installation counts come from a voluntary sample.** Home Assistant asks users
  whether they want to send anonymous statistics, and many say no. The numbers are large
  enough to rank by and useless for claiming how many people use something. They also
  exist for **integrations only** — dashboard cards, themes and templates are simply not
  counted anywhere.
- **"Possibly unmaintained" is a hint, not an accusation.** A small integration for a
  device with a stable interface can be finished. It can sit there for three years
  without a commit and still work perfectly. The list is a prompt to go and look, not a
  verdict.
- **A dash is not a zero.** Where a figure genuinely is not known, the page shows `–`
  and says why when you hover over it. Those rows sink to the bottom whichever way you
  sort, so an ascending sort does not fill the screen with gaps.
- **Some columns need time.** Star history could be fetched from GitHub going back
  years. Installation figures could not — Home Assistant publishes today's number and no
  archive — so those trends fill in as this project keeps collecting, and the page says
  so rather than showing a misleading zero.
- **The top left says how fresh it is** — "last run 3 hours ago", measured against your
  own clock. If the data behind it turns out to be older than the run, a second line
  says which day it is really from.

## Try it on your own machine

**Just to look at it**, you need nothing but a browser, `git`, and any Python:

```bash
git clone https://github.com/thesoulrester/hacs-trends.git
cd hacs-trends
python3 -m http.server -d web 8000
```

Then open <http://localhost:8000>. That is the complete page with the real, current
data — the numbers are committed to the repository, so there is nothing to fetch, no
account, no key, no waiting. Stop it with Ctrl-C.

**To collect the data yourself** you need Python 3.10 or newer, and then:

```bash
./run.sh
```

The script sorts itself out: it finds a suitable Python, sets up its own isolated
environment, installs what it needs, fetches the HACS store and the Home Assistant
statistics, and serves the result on <http://localhost:8000>. No admin rights, and
nothing is installed system-wide.

One thing to know before you run it: this collects the parts that need no permission
from GitHub, which leaves the release and commit columns empty — and it overwrites the
data file that came with the repository. If you just wanted to see the page, the plain
web server above is the better command. To collect *everything*, see the developer
section below.

<details>
<summary><b>Collecting everything, and the other commands</b></summary>

The GitHub parts — releases, commit counts, archived state, star history — need a
personal access token. Not because any of it is private, but because GitHub allows
anonymous callers 60 requests an hour and token holders 5,000. A **classic token with
no scopes ticked at all** is enough. Put it in a file called `.env`:

```
GITHUB_TOKEN=ghp_...
```

Then:

```bash
./run.sh build      # everything the scheduled run does, about 12 minutes
```

The individual steps, if you want them one at a time:

```bash
./run.sh check      # syntax, translations, workflows, tests — seconds, no token
./run.sh sync       # HACS store and Home Assistant statistics
./run.sh dates      # the day each repository was accepted into HACS
./run.sh enrich     # releases, commits, archived state (needs a token)
./run.sh export     # rebuild web/data.json
./run.sh stats      # what is currently in the local database
./run.sh test       # the collector's test suite
```

`check` is worth running before every push. It catches what typing breaks — invalid
JavaScript, a translation key in one file and not the other, a workflow that is no
longer valid YAML — in a few seconds, with no token and no network. What it cannot
check is whether the page still *looks* right: serve `web/` and look at it.

The full star history is a separate, one-time job of about 8,400 requests:

```bash
./run.sh bootstrap  # roughly 30–90 minutes, and resumable if it stops
```

</details>

## Where the numbers come from

Nothing here is estimated, modelled or smoothed. Every figure comes from one of four
public sources, and you can check any of them yourself.

| Source | What it gives |
|---|---|
| **The HACS store** (`data-v2.hacs.xyz`) | Which repositories exist, what kind each is, star counts, descriptions, the newest release version, last update |
| **Home Assistant statistics** (`analytics.home-assistant.io`) | How many installations of each integration are running, and which version they are on |
| **GitHub** | Releases, commit counts, whether a repository was archived, and the day-by-day star history |
| **The [`hacs/default`](https://github.com/hacs/default) list** | The day each repository was accepted into HACS, read from that list's own history |

Two things are worth spelling out, because they are the ones most easily got wrong.

**Growth in percent is measured against the start of the period, not the end.** A
project that doubled reports 100 %, not 50 %. Below 25 stars at the start no percentage
is shown at all — with a typical repository sitting at 13 stars, a percentage ranking
would otherwise just be a list of projects that went from 2 stars to 4.

**Installations are matched to a repository by the integration's internal name.** Where
two repositories claim the same one, the figure is flagged as ambiguous instead of being
given to either. That happens for 43 of them.

<details>
<summary><b>Column by column — where every single figure comes from</b></summary>

| Column | Where it comes from |
|---|---|
| **Kind** | The category file the repository is listed in at `data-v2.hacs.xyz` — `integration`, `plugin` (dashboard card), `theme`, `template`, `python_script`, `appdaemon`, `netdaemon`. Nothing is inferred from the code. |
| **Stars** | The HACS dataset's own count, taken at collection time. |
| **Stars gained (7 d / 30 d / quarter / year)** | Summed from GitHub's star history endpoint, which returns weekly buckets each holding a seven-element array of daily counts, back to the repository's creation. The sum over the window is therefore exact, not interpolated. GitHub reports stars *given*, never stars removed, so this is a gross figure. |
| **Growth %** | Stars gained divided by the count at the **start** of the window, not the current one. Below 25 stars at the start no percentage is shown at all; with a corpus median of 13 stars, a percentage ranking would otherwise be a list of repositories that went from 2 stars to 4. The cut-off travels in the data file, so the page always states the value the figures were actually computed with. |
| **Installations** | Home Assistant's opt-in analytics, matched to a repository by the integration domain in its `manifest.json`. Where two repositories claim the same domain the number is flagged as ambiguous rather than attributed to one of them (43 domains, currently). Integrations only — 2,101 of the 3,248 integrations that declare a domain are matched. |
| **Installation growth** | Differenced from this project's own daily slices — analytics publishes today's figure, never a history, so this column can only fill in over time and says so on the page. |
| **Version adoption** | The share of reported installations running the release tag HACS names as newest. If that exact tag does not appear in the analytics data the column shows a dash, not a zero — an early version of this got 0.0 % for everything by picking the highest-looking key instead, which selected nightly builds with one install. |
| **Last commit** | The HACS dataset's `last_updated`. A 45-repository sample against the GitHub API showed this is exactly GitHub's `pushed_at`, not `updated_at` — the wording on the page follows that measurement. Shown as the distance from your own clock, so it stays right between collection runs. |
| **Status** (active / quiet / stale / dormant) | Days since that commit: under 90 active, under 365 quiet, under 730 stale, beyond that dormant. Archived repositories and ones GitHub no longer serves get their own state. The thresholds come from the measured distribution across all 4,193 repositories — median 55 days, P75 208, P90 689. |
| **Last release** | The newest release from GitHub GraphQL, ordered explicitly by creation date. Without that explicit ordering GitHub returns the *oldest* releases for a `last: N` query, which produced a plausible and entirely wrong table until it was checked. |
| **Releases / year** | Releases published in the last 365 days. The first pass fetches 30 releases per repository and a second pass re-queries the ones that hit that ceiling with 100, so the number is exact for all but the 52 repositories still at 100 — those are shown as `100+` rather than as a figure the data cannot support. |
| **Release rhythm** | Buckets on that same count: 12 or more continuous, 4 or more regular, 1 or more occasional, none in the year dormant, and never published a release at all shows as never. The thresholds are the corpus quartiles (median 4 a year, P75 13, P90 27), not round numbers. |
| **Commits / year and quarter** | GitHub GraphQL, counted on the default branch since a timestamp — not a rate, an actual count. |
| **Gaining and in use** | The percentile rank of star growth and of installation growth, ranked on the **lower** of the two, so a repository has to be strong in both. Both component ranks get their own column: a placement is never a black box. |
| **In HACS since** | The first commit that added the repository to the lists in `hacs/default` — exact back to 20 October 2019 and matching 4,171 of 4,193 repositories. The 22 without a date are HACS itself, which is not in its own list, and repositories renamed on GitHub since. Everything stamped with 20 October 2019 is shown as "since the start" rather than dated: that is the day the list was written from an older location, so those were already in HACS and the real date is gone. |
| **New in HACS** | Ranked by that acceptance date. The first daily slice a repository appears in is kept as a fallback for anything the list has not caught up with. |
| **Downloads** | The release asset counter from the HACS dataset. Only 33 % of repositories have one, because HACS installs from source when a release carries no assets. Shown, never ranked on. |
| **Rank number** | The position in the current view's full ranking, assigned before your search and filters are applied — so a search result also tells you where it stands. |

**What is deliberately not measured**

Watchers (median 1, P90 8 across the corpus — too sparse to rank on), issue close rates
as a quality signal, anything from a repository's code or README, and anything about the
people behind a repository. There is no scoring formula that blends several figures into
one number: every ranking is one figure you can name, with the others shown next to it.

**Check it yourself**

Every daily slice is committed as text under `data/snapshots/`, and the star history as
`data/stars/star_days.jsonl.gz`. The exported file the page reads is `web/data.json`.
[PLAN.md](PLAN.md) documents each measurement in full, including the assumptions that
turned out to be wrong.

</details>

## How it stays up to date

Two scheduled jobs run on GitHub's own machines. Nothing runs on a server anybody has to
pay for or look after.

- **Twice a day** — fetch the HACS store and the Home Assistant statistics, ask GitHub
  about releases and commits, write the day's figures, rebuild the page and publish it.
- **Once a week** — re-read the full star history for every repository. This is the slow
  one: about 8,400 requests and up to two hours.

Because the star history is only refreshed weekly, a repository starred yesterday may be
up to seven days behind in the star columns, while everything else is at most twelve
hours old.

### Where the history lives

Not in a database — that is only a cache, rebuilt on every run. The record is committed
as plain text:

- `data/snapshots/YYYY-MM-DD.json.gz` — one slice a day, about 50 KB, roughly 18 MB a
  year. Readable, diffable, and usable by anyone who wants the raw series.
- `data/stars/star_days.jsonl.gz` — the star history, refreshed weekly.

A committed database file would have added its full size to the repository's history on
every single run.

## Publish your own copy

1. Push to a repository of your own.
2. *Settings → Pages* → source **GitHub Actions**.
3. *Settings → Actions → General → Workflow permissions* → **Read and write**, so the
   run can commit each day's figures.
4. *Settings → Secrets → Actions* → add `STAR_HISTORY_TOKEN` (only needed for the weekly
   star refresh).
5. *Actions → Collect and publish → Run workflow* once to get it started.

The site appears at `https://<account>.github.io/<repo>/` after the first successful
run. Before that the address returns 404, because the site does not exist yet.

For your own domain, put the hostname in `web/CNAME` and point a DNS `CNAME` record at
`<account>.github.io`. GitHub issues the certificate. No hosting needed.

## Translating

English is the source, and it also fills any gap, so a half-finished translation is
useful immediately and never leaves someone staring at a blank interface.

1. Copy `web/i18n/en.json` to `web/i18n/<code>.json`.
2. Translate the values. Leave the keys and the `{placeholders}` alone.
3. Add the language to `LANGS` at the top of `web/app.js`.
4. Open a pull request.

`python tools/check_i18n.py` reports how complete each file is and fails on keys that
exist nowhere else or placeholders that no longer match.

## Sources

- HACS dataset: `https://data-v2.hacs.xyz/<category>/data.json`
- Home Assistant analytics: `https://analytics.home-assistant.io/custom_integrations.json`
- GitHub GraphQL and the star history endpoint
- The git history of [`hacs/default`](https://github.com/hacs/default)

[PLAN.md](PLAN.md) records the design decisions and, more usefully, the measurements
that overturned several of them.
