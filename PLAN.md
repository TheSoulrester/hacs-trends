# betterHACs — Design and Data Plan (v2)

Revised 2026-09-05. Supersedes v1 (kept as `docs-de-PLAN-v1.md` for the record).

**Goal.** A public page where the Home Assistant community can find out which HACS
repositories are gaining traction — and which ones look abandoned. Free to run, hosted
on GitHub Pages, no server required.

**Project language is English** from this revision on: code comments, docs, commit
messages and the default UI. HACS is an international community; German comments would
be a real barrier to anyone contributing. The UI ships German as a second language and
accepts further language packs by pull request (§7).

---

## 1. What changed since v1

Three things, all of them the result of measuring rather than assuming.

**The complete star history of all of HACS is retrievable in about 1.5 hours.** v1
budgeted ~2 hours just for the last 30 days and treated deeper history as out of reach.
That was wrong. All 4,193 repositories hold **354,357 stars in total**; the bootstrap
cost is dominated by the one mandatory request per repository, not by page depth:

| Bootstrap depth | Requests | Wall clock |
|---|---|---|
| 30 days | ~3,800 | ~0.8 h |
| Quarter | ~3,900 | ~0.8 h |
| 1 year | ~4,400 | ~0.9 h |
| **Every star ever given** | ~7,300 | ~1.5 h |

Thirty minutes separates "last month" from "everything". So there is no reason to
limit the depth. **Stars support 7d / 30d / quarter / year / all-time exactly from day
one**, plus a growth curve per repository going back years.

GitHub caps stargazer pagination at 400 pages (40,000 stars). The largest HACS
repository has 22,066 — no repository is affected.

**`last_updated` was already the real commit date.** v1 assumed it was GitHub's
`updated_at` and built the case for GraphQL enrichment on that. A 45-repository sample
disproved it: HACS ships `pushed_at`, to the second. Verified on
`rospogrigio/localtuya` — HACS and `pushed_at` both `2026-01-29T11:04:59Z`, while
`updated_at` reads `2026-09-04`. Enrichment stays, but for `isArchived` and release
dates, which genuinely do not exist anywhere else.

**Neither installations nor downloads can be backfilled.** Home Assistant analytics
publishes only the current state, and so does GitHub's asset counter. Their history has
to accumulate forward. One possible exception is the Internet Archive, which has
captured the analytics file (a snapshot from 2026-08-20 is confirmed to exist) — how
densely and how far back is an open investigation (§10).

---

## 2. Data availability — the constraint everything else follows from

| | now | 7d | 30d | quarter | year | all-time |
|---|---|---|---|---|---|---|
| **Stars** | yes | yes | yes | yes | yes | yes |
| **Installations** | yes | +7d | +30d | +90d | +365d | yes |
| **Downloads** | yes* | +7d | +30d | +90d | +365d | yes* |

\* 33% coverage only — see §3.

This asymmetry is not a temporary annoyance to be hidden. It is the single most
important thing the interface has to communicate honestly, because a user who sorts by
a column that is silently empty draws a false conclusion.

**Rule throughout: an unavailable value renders as an em dash with the date it becomes
available, never as zero.** Rows without a value sort to the bottom regardless of sort
direction, so an ascending sort never fills the top with gaps.

---

## 3. Metric catalogue

Everything that can serve as a popularity or health signal, with what it actually costs
and what it actually means.

### Available now

| Metric | Source | Coverage | What it really measures |
|---|---|---|---|
| **Stars** | HACS data | 3,734 / 4,193 (89%) | Visibility and approval. Not use — plenty of people star things they never install. |
| **Installations** | HA analytics, joined on `domain` | 2,101 integrations (64.7% of those with a domain); **0% of plugins, themes, templates** | Actual running installations. The only true usage signal available. Opt-in sample (~677k reporting installs), so good for ranking, never for absolute claims. |
| **Version adoption** | HA analytics per-version | same as installations | Share of installs running the newest release. Nobody else publishes this. Both a popularity and a maintenance signal. |
| **Downloads** | HACS data (GitHub release assets) | 1,373 / 4,193 (**33%**) | Cumulative asset downloads. Absent entirely for repos that ship from source, and HACS has open bugs about its accuracy. Secondary at best. |
| **Open issues** | HACS data | high | Ambiguous on its own — many issues means popular *or* broken. Useful as a ratio. |
| **Last commit** | HACS `last_updated` (verified = `pushed_at`) | 100% | Real activity. Median across HACS: 55 days; P90: 689 days. |

### From GraphQL enrichment

| Metric | Why it earns its place |
|---|---|
| **`isArchived`** | The only hard abandonment signal. Missing from HACS data entirely. |
| **`latestRelease.publishedAt`** | Separates "commits but hasn't shipped in two years" from "dead". |
| **`createdAt`** | Enables age normalisation (below). One extra field, no extra request. |
| **Forks, watchers** | Developer interest, independent of stars. |
| **Release count / cadence** | How regularly the project actually ships. |
| **License, language, availability** | Context; and whether GitHub still knows the repo at all. |

### Derived — the interesting ones

| Metric | Definition | Why it is worth showing |
|---|---|---|
| **Installs per star** | installs ÷ stars | Separates quiet workhorses from hype. A device integration with 15,000 installs and 200 stars is used but never celebrated; the inverse is admired but rarely run. Integrations only. |
| **Stars per month since creation** | stars ÷ age in months | Removes the age advantage. Absolute rankings are permanently owned by projects that have simply existed longer; this surfaces young projects growing fast. |
| **Relative growth** | Δ ÷ base, in percent | Requires a minimum base — the star median across HACS is **13**, so without a floor the percentage ranking is nothing but repos that went from 2 stars to 4. Floor is 25. |
| **Issues per 100 stars** | | Normalised engagement/friction. |
| **Momentum percentile** | see §5 | |

### Deliberately not included

A single blended popularity score. Stars, installations and downloads measure different
things, at different coverage, with different reliability. Adding them up produces a
number that looks objective and is not. §5 describes the transparent alternative.

---

## 4. Time windows

One global selector — **7 days / 30 days / quarter / year / all time** — applying to the
whole table, rather than per-metric controls. One rule, no special cases, and the user
learns it once.

Reference days are chosen globally, not per repository: a sync writes every repository
together, so the same reference date is correct for all of them and vastly faster than a
per-row search. Tolerance is ±2 days for the 7-day window, ±4 for 30, ±7 for the quarter,
±14 for the year — a missed run should not blank the column, but a reference point weeks
off should not silently distort it either.

Where a window is not yet available for a metric, the header carries the date it becomes
available, and every cell in it renders as a dash.

---

## 5. Views — questions, not dimensions

The v1 interface offered four tabs named after data dimensions and left the user to
work out which one to press. That is the main usability failure to fix. Each view is
now a **question a user actually arrives with**, and its explanation is permanently
visible rather than hidden in a tooltip.

| Question | View | Ranked by | Notes shown |
|---|---|---|---|
| *What is gaining attention right now?* | **Trending** (default) | star growth in the selected window, absolute and relative side by side | which reference date is in use |
| *What do people actually run?* | **Most installed** | installations | integrations only, and why; sample caveat |
| *What is rising fast for its size?* | **Breakout** | relative growth with the minimum base, plus stars per month since creation | why small repos are excluded |
| *What has real momentum?* | **Momentum** | percentile rank of star velocity **and** installation velocity, **with both component ranks shown in their own columns** | integrations only; the two ranks are visible so the placement is never a black box |
| *What might no longer be maintained?* | **Maintenance** | age of last commit; archived and HACS-removed pinned to the top | explicitly a prompt to look, not a verdict |
| *What is new in HACS?* | **Recently added** | first appearance in our own history | needs ≥2 days of history to mean anything |

Search, category filter and time window stay available in every view — they are
qualifiers, not modes.

---

## 6. Interface

### Layout, top to bottom

1. **Header** — name, one line saying what the page is for, data timestamp, language
   switcher.
2. **Question cards** — one card per view from §5. The card carries the question as its
   label and a single explanatory sentence underneath. This is what replaces the opaque
   tabs; a first-time visitor should be able to pick correctly without reading docs.
3. **Time window** — segmented control, with unavailable windows visibly marked rather
   than hidden.
4. **Search and filters** — placeholder text that names what can be typed
   (name, author, domain, topic); category chips with counts; maintenance-state chips.
5. **Table** — sticky header, windowed rendering, one row per repository.
6. **Footer** — coverage figures, sources, and the statement that this is not an
   official HACS project.

### Table row

Repository name and title, description, category, the metric columns for the active
view, and maintenance state. Numeric columns are tabular-figure aligned.

**Visual encoding** — the answer to "reads like a database dump":

- A **sparkline of the star curve** per row. We will have the full history after the
  bootstrap, so this is real data, not decoration, and it makes patterns visible at a
  glance that a number cannot convey: steady growth, a spike, a plateau.
- **Proportional bars** behind the installation figures, so relative size is readable
  without comparing digits.
- **Colour on the trend columns only** — positive, negative, neutral. Everything else
  stays quiet, so the colour means something.
- **Maintenance state as a dot plus a word**, never colour alone (colour-blind users,
  and it has to survive a screenshot).

If the row becomes crowded, the sparkline is the first thing to cut — it is the most
expensive element in both payload and attention.

### Sparkline data budget

Weekly points over 24 months would be 104 values per repository. Across 4,193
repositories that is far too much for a page payload. The export therefore carries
**26 fortnightly points covering the last year**, stored as deltas — roughly 109,000
small integers, an estimated 250–350 KB gzipped on top of the current ~300 KB. To be
measured before committing to it; if it lands materially higher, sparklines move to a
lazily fetched per-repository detail request instead.

---

## 7. Internationalisation

English is the default and the fallback. German ships alongside. Further languages are
contributed by pull request.

```
web/i18n/en.json        # source of truth, English
web/i18n/de.json        # German
web/i18n/<code>.json    # contributed
```

Flat key/value files with `{placeholder}` interpolation, because several strings carry
numbers and dates:

```json
{
  "view.trending.title": "What's gaining attention",
  "view.trending.help":  "Ranked by new stars in the selected period.",
  "window.unavailable":  "Available from {date}",
  "coverage.stars":      "Star counts for {n} of {total} repositories ({pct}%)"
}
```

**Language selection:** `?lang=` in the URL, then the stored choice, then
`navigator.language`, then English. The chosen language is remembered per browser.

**Fallback is per key, not per file.** English is always loaded; a translation file
overrides the keys it defines. A partial translation is therefore useful immediately
and never produces a blank interface — which matters, because that is what makes a
first contribution feel worth making.

**Numbers and dates** go through `Intl.NumberFormat` and `Intl.DateTimeFormat` with the
active locale, not hand-formatted.

**CI guards the contribution loop.** A check compares every language file against
`en.json` and fails on unknown keys, reporting missing ones as a warning with a count.
Without this, translations drift silently as the interface grows and contributors have
no way to know what needs updating. `CONTRIBUTING-TRANSLATIONS.md` documents the whole
process: copy `en.json`, translate the values, leave the keys and placeholders alone,
open a pull request.

---

## 8. Data model changes

```
star_events        repo_id, starred_at              -- full bootstrap, ~354k rows
star_daily         repo_id, day, cumulative_stars   -- derived; any window, and sparklines
repo_github        + created_at, watchers, releases_count
```

`star_daily` is derived from `star_events` and is what the window arithmetic and the
sparklines actually read; `star_events` is kept so the derivation can be redone if the
aggregation changes.

**Where the bootstrap result lives.** It is a one-time artefact of ~354k rows,
regenerating it costs 1.5 hours, and it must survive a fresh clone. It is therefore
committed as `data/star_history.json.gz` (per repository: a start date and a run-length
encoded daily series), not left in the disposable database. Estimated 2–4 MB, committed
once and appended to rarely.

Daily slices under `data/snapshots/` remain the source of truth for everything else,
unchanged.

---

## 9. Implementation order

1. **i18n scaffolding** — extract every string, English source file, German pack, key
   parity check in CI. Doing this first avoids extracting strings twice.
2. **Star bootstrap** — resumable, rate-limit aware, progress persisted per repository.
   The single biggest unlock in this revision.
3. **`star_daily` and window arithmetic** for all five windows.
4. **Extend GraphQL** with `createdAt`, watchers, release count.
5. **Derived metrics** — installs per star, stars per month, version adoption,
   issues per 100 stars.
6. **Interface rebuild** — question cards, permanent explanations, window selector,
   visual encoding.
7. **Momentum view** with visible component ranks.
8. **Investigate the Internet Archive** for installation history (§10).
9. **Verification** — spot-check bootstrap totals against GitHub's own star counts,
   confirm window arithmetic against known repositories, measure the real payload size.

---

## 10. Open questions and risks

- **Internet Archive density for installation history.** Confirmed that captures of
  `custom_integrations.json` exist. Unknown: how far back, how regularly, and whether
  the captures are complete rather than truncated. Worth one investigation step; if
  captures turn out to be monthly or better over a year, installation trends become
  available immediately instead of in 2027. Not to be scraped aggressively.
- **Sparkline payload.** Estimated, not measured. §6 states the fallback.
- **43 shared domains.** Multiple HACS repositories claim the same integration domain,
  so their installation figures are not attributable. Already flagged in the interface;
  the momentum view must exclude them from ranking rather than rank them on an
  ambiguous number.
- **`data-v2.hacs.xyz` is HACS-internal.** No stability guarantee; v1 → v2 already
  happened. Schema validation aborts the sync loudly rather than writing partial data.
- **Fair use.** ETags on every request, honest user agent, at most 2–4 runs a day. The
  bootstrap runs once and is spread under the rate limit.
- **The maintenance view can do harm.** A small, finished integration for a device with
  a stable API can be correct for years without a commit. Labelling it as a problem
  drives users away from working software. The wording is a prompt to look, never a
  verdict, and `isArchived` and HACS removal are the only statements presented as facts.

---

## 11. Decisions taken, and what the enrichment measured

### Settled

- **Interface direction C** — dark, left rail with icons, a four-figure summary strip
  above the table. Chosen from three drafts.
- **A seventh view, "Ships reliably"**, ranked on releases in the last year, plus a
  release-rhythm column in every view. Verified to be worth having: of the top 30 by
  30-day star growth and the top 30 by release activity, **only 5 repositories appear
  in both**. A view sorted on raw commit freshness would have been a near-duplicate of
  Trending — young growing projects commit daily — which is why it is release rhythm
  and not commit count.
- **Collect everything**: release rhythm, commit activity, version adoption, issue
  balance, forks, licence, age. The full enrichment costs **84 rate-limit points of
  5,000 per hour** — measured, one point per 50-repository query.

### What the corpus actually looks like (4,193 repositories, enriched)

| Release rhythm | | |
|---|---|---|
| continuous, 12+ releases a year | 1,147 | 27.4% |
| regular, 4–11 a year | 1,162 | 27.7% |
| occasional, 1–3 a year | 978 | 23.3% |
| nothing for over a year | 775 | 18.5% |
| no release at all | 131 | 3.1% |

Median releases in a year: 4. Median days since the last release: 86 (P75 245, P90 722).
Median commits in a year: 25 — and a quarter of the corpus manages four or fewer.
Archived: 1. Gone from GitHub: 16. Forks: 133. Without a licence: 548.

### Measured corrections to earlier assumptions

- **`releases(last: N)` returns the OLDEST releases.** GitHub orders the connection
  descending by creation, so `last` takes the tail. Caught on
  `robinostlund/homeassistant-volkswagencarnet`, where the "latest" three came back as
  v4.4.5–v4.4.7 from June 2020 against a real newest of v5.5.1 from August 2026. Every
  query now orders explicitly. Left unnoticed this would have produced a complete,
  plausible and entirely wrong cadence table.
- **Median gap between releases is not a usable cadence measure.** It reads 5 days
  across the corpus, which sounds like everything ships weekly. The last 15 releases of
  any project cluster tightly even when the whole block is two years old — a repository
  that released fifteen times in one month in 2023 scores a one-day cadence. Releases
  within the last year plus the age of the newest are what get stored instead.
- **Watchers are too sparse to rank on.** Median 1, P90 8. Dropped as a signal.
- **"Commits but never releases" is rare** — 7 of 611 in the sample. Worth a note on a
  repository page, worthless as a metric.
- **A 100-repository GraphQL batch times out** (502, and 504 on heavy repositories).
  Fifty works; the collector halves a failing batch and retries rather than losing it.

### Known defect, fixed since

`releases_year` **saturated at 30** because only 30 release nodes were fetched, so the
top of the "Ships reliably" ranking was one block of ties decided by the commit
tiebreaker. A second pass now re-queries the repositories that hit the ceiling with 100
nodes. 52 are still at 100 and display as "100+"; everything below that is exact.

### Still open

- Which GitHub account and repository name the project lives under.
- Whether the Internet Archive holds enough captures of the analytics file to backfill
  installation history.
- Sparkline payload size — estimated, never measured.
- 773 repositories gained no stars at all in 60 weeks. Worth surfacing as its own fact.

## 12. Round two — reported defects and what is planned for them

Everything in this section was measured on the live site
(`https://thesoulrester.github.io/hacs-trends/`) and on the 2026-09-05 export,
not estimated.

### 12.1 One missing CSS rule causes two of the reported bugs

`web/index.html` has no `[hidden]{display:none!important}` rule. The browser's own
stylesheet does carry `[hidden]{display:none}`, but author rules outrank it, and two
author rules set `display` on exactly the elements the code hides:

- `.seg{display:inline-flex}` — the time-window buttons
- `.row{display:grid}` — the pooled table rows

So `element.hidden = true` sets the attribute and changes nothing on screen.

**Effect A — window buttons look stuck.** `buildWindows()` sets `box.hidden = !v.windowed`
and returns early for non-windowed views. In `installed`, `ships`, `maintenance` and
`fresh` the buttons therefore stay visible with their old click handlers. Clicking one
changes `win`, calls `buildWindows()`, which returns before re-rendering the buttons, so
`aria-pressed` never moves. The button appears dead — and `win` has silently changed
underneath, which is why the next windowed view can open on an unexpected period.
This matches the report exactly: "not always, but often".

**Effect B — duplicate rows under search.** The renderer keeps a pool of row elements and
hides the surplus with `node.hidden = true`. The surplus stays visible, at its old
absolute position, with its old content. Filtering the list down (which is what searching
does) shrinks `need`, so leftover rows from the unfiltered list remain painted over the
result. `washdata` occurs exactly once in `data.json` — zero duplicate ids, zero duplicate
names — so the second "washdata" on screen is a ghost row, not a data defect.

**Fix.** Add `[hidden]{display:none!important}` to the stylesheet. Additionally reset the
surplus rows' `innerHTML` and drop the stale click handlers so nothing depends on a single
CSS rule, and hide the window strip by removing the buttons rather than by an attribute.

*Why it never showed in the design preview*: the artifact wrapper injects that rule.
The standalone page does not.

### 12.2 Search: 79 ms per keystroke, no index

Measured on an M-series Mac, whole corpus, one keystroke:

| step | today | with index |
|---|---|---|
| filter incl. description | 79.4 ms | 3.5 ms |
| building the index | — | 213 ms, once |

The cost is `toLowerCase()` on up to 300 characters of description for 4,193 rows on every
keystroke. Plan: build a lowercase haystack (`name + title + domain + description`) once
after first paint, in an idle callback, and search against it. Search stays over the same
four fields, so results do not change.

Autocomplete rides on the same index: a dropdown of at most eight matches on name,
display name and repository path (not description — a substring hit inside a sentence
makes a poor suggestion), ordered by stars, arrow keys and Enter. Choosing a suggestion
puts the full path into the search box, which narrows the table to that one repository.

### 12.3 "0 d" — the export throws the time of day away

`_iso_day()` truncates every timestamp to a date, so anything less than a day old reads
`0 d`. The database holds full timestamps (`2026-09-05 18:41:24`), so this is an export
change only: emit `lu` and `rd` with minute resolution (`2026-09-05T18:41Z`) and let the
page compute the distance from the current clock. Cost: about +7 characters per field per
row, roughly 29 KB uncompressed and far less after gzip. Benefit beyond the fix: the
figure stops being frozen at export time and stays right between the twice-daily runs.

Display ladder: `< 60 min` → minutes, `< 24 h` → hours, `< 60 d` → days, beyond that
months. Same ladder for last commit and last release.

### 12.4 Icons

`https://brands.home-assistant.io/<domain>/icon.png` serves core and custom integrations
from one path; a domain without an icon returns 404, and the `/_/` variant returns a
placeholder image instead. Coverage against our corpus, counted from the brands repository
tree:

| | repositories |
|---|---|
| total | 4,193 |
| have a domain | 3,248 |
| have `icon.png` in brands | **2,138 (51 %)** |
| domain, but no brands entry | 1,055 |
| no domain at all (cards, themes, scripts) | 945 |

So roughly every second row can have a real icon and the rest needs a placeholder — the
category glyph on the panel colour, not the brands placeholder image, which would look
like a broken icon repeated a thousand times. Icons are cached for seven days by the
browser and served by Cloudflare, and only the ~20 rows in the viewport request one.

Since HA 2026.3 custom integrations may ship their brand icons in their own repository and
have them proxied, so real coverage may be higher than the 2,138 counted here. Not
verifiable from this network; worth re-measuring against the live CDN.

### 12.5 Performance — the desktop is fine, the phone is not

Measured on the live site:

| | |
|---|---|
| `data.json` over the wire | **513 KB** (1.85 MB uncompressed, gzip by Pages) |
| `JSON.parse` | 78 ms |
| filter for a view | 3.3 ms |
| sort | 3.2 ms |
| DOM interactive | 445 ms |

Nothing here justifies paging or lazy loading: the table already renders only the rows in
the viewport.

**But** the ≤900 px stylesheet sets `.viewport{overflow:visible;height:auto}`, which makes
`viewport.clientHeight` equal to the full content height. The renderer then decides it
needs every row and builds **all 4,193 of them: 71,405 DOM nodes**. Confirmed in the
browser. On a phone this is the whole performance problem, and it is a layout bug rather
than a data-volume problem. Fix: on the narrow layout, drive the window from the page
scroll position and `window.innerHeight` instead of the element's, keeping the same ~20
live rows everywhere.

### 12.6 Answers to two questions this round raised

**Where the "kind" badge comes from.** It is the HACS category, and it comes from which
category file the repository is listed in at `data-v2.hacs.xyz/<category>/data.json`.
Nothing is inferred. Corpus: 3,244 integrations, 765 plugins (dashboard cards), 106 themes,
54 AppDaemon apps, 11 templates, 9 python scripts, 4 NetDaemon apps.

**How release rhythm is defined.** Releases published in the last 365 days, bucketed:
≥ 12 continuous, ≥ 4 regular, ≥ 1 occasional, 0 dormant, and never for a repository that
has never published a release. The thresholds come from the measured corpus (median 4
releases a year, P75 13, P90 27; 18.5 % dormant, 3.1 % never), not from round numbers.
Caveat: the count is exact except for the 52 repositories still at the 100-release
fetch ceiling, which display as "100+" (see §11).


### 12.7 What was decided and built

Chosen: two-line rows (56 px) with icons, everything in one pass, autocomplete included.

Verified in headless Chromium against the real export, viewport 1440x900 and 390x844:

| check | result |
|---|---|
| row height / description present | 56 px, description on every row |
| search `washdata` | **1 visible row** (was 2) |
| period strip in a non-windowed view | `hidden`, `display:none`, zero buttons left |
| period buttons after switching back | 7 d selects and marks correctly |
| relative time | `21 min`, `12 h`, `3 d`, German `21 Min.` |
| rows in the DOM at 390 px | **20**, and 24 after scrolling (was 4,193) |
| page errors | none |

Icons could not be loaded in the test environment (the CDN is not reachable from there),
which exercised the fallback path instead: every row fell back to the category mark with
no error. The URL form is the one the brands repository documents.

Still open from this round: re-measuring icon coverage against the live CDN now that
integrations may ship their own brand icons.

### 12.8 The rank column keeps its place under a filter

Numbering happens before the user's filters, not after. Searching for a repository now
answers a second question along with the first: not only that it exists, but where it
stands. `washdata` comes back as **6**, not as **1**; filtering the list to themes shows
44, 67, 123 rather than 1, 2, 3.

Only the view's own eligibility rule takes part in the numbering — a row with no growth
figure has no place in a growth ranking to keep. The number follows the active sort, so
sorting by stars renumbers everything before the filter is applied. Where nothing is
filtered, the number is the position, exactly as before, and the tooltip appears only on
a number that has been kept.

Cost: sorting 4,193 rows instead of the filtered remainder — 3.2 ms, measured.

### 12.9 Version behind the path

The newest release now sits behind the repository path on the first line, separated by a
middle dot. HACS reports one for 4,075 of 4,193 repositories; the rest simply show
nothing rather than a placeholder.

The version does not shrink, the path does — a shortened path still identifies the
repository, a shortened version number does not. Below roughly five characters the path
says nothing at all, so it is dropped entirely and the full path stays on its tooltip.
Measured at 1440 px the path survives for every row; from about 1280 px down it gives way
on the longer names, and on a phone it is always gone.

That measurement costs one layout per render, but only if it is done properly: reading a
width and hiding an element in the same loop invalidates the layout before the next read
and made the browser recompute it twenty times — **26 ms per render against 9 ms** for the
same work split into a read pass and a write pass. With the split, the probe costs
nothing measurable (8.4–9.6 ms against 8.0–9.8 ms over three runs).

### 12.10 Cache: a stale page after a deploy

GitHub Pages serves every file with `Cache-Control: max-age=600` and an ETag. Within
those ten minutes a browser reuses what it has without asking, which is why a fresh
deploy can still show the old page — and why Safari in particular keeps `app.js` across
an ordinary reload.

Ten minutes of old numbers is harmless. Ten minutes of **yesterday's `index.html` against
today's `app.js`** is not: the two are built together and can break each other. Two
changes, one for each half:

- `data.json` and the translation files are fetched with `cache: "no-cache"`, which does
  not mean "do not cache" but "revalidate first" — one conditional request, answered with
  304 and no body when nothing changed. Verified: the browser now sends `max-age=0` for
  those three and nothing for `app.js`.
- The workflow stamps the script reference in the deployed `index.html` with the first
  eight characters of the commit sha. An old HTML asks for the `app.js` it was built
  against, a new one for the new file, and neither can be answered from the cache with
  the other. The repository copy keeps the plain `./app.js`, so nothing changes locally.

### 12.11 The version stands in a column

Right-aligned within the repository cell. Placed behind the path it landed wherever the
path happened to end, and a number that moves on every row cannot be read by scanning.

That exposed a second defect: the name could not shrink, so on a long name it pushed the
version past the cell edge, where `overflow:hidden` cut it off — the one thing the whole
arrangement was supposed to prevent. The shrink order is now explicit: the path gives way
first (weighted a hundred to one), the name only after the path is gone, the version
never. Measured at 1920, 1600, 1440, 1280 and 1000 px: one right edge per width, nothing
overhanging the cell.

### 12.12 Mobile, round two

A tester's phone froze on the site the night before the narrow-layout fix shipped, on the
build that still put all 4,193 rows in the DOM. That build is gone, but the report was
worth measuring properly rather than declaring solved, so the current one was profiled in
a 390x844 context at 1x, 4x and 8x CPU throttling.

The DOM was fine — 34 rows, 850 nodes, 11 MB heap. Scrolling was not: **every scroll event
rewrote all thirty-odd rows**, because the pool assigned element *i* to row *first + i*,
so a one-row scroll changed the content of every element.

Rows now keep their element while they stay on screen: the slot is the row index modulo
the pool size, so scrolling by one row rewrites one row. A generation counter invalidates
every slot at once when the data, the columns or the pool size change.

| CPU | before | after |
|---|---|---|
| 1x | 8.7 ms | **2.4 ms** |
| 4x | 44.6 ms | **11.3 ms** |
| 8x | 103.9 ms | **29.1 ms** |

(Median over 30 scroll steps, with the scroll position committed before the event so the
figure is the real render and not a no-op. Output verified identical: 37 rows, every rank
matching its position, no duplicates.)

Three more passes over the corpus were being repeated per keystroke and are now not:

- the ranked base list is cached against view, window, sort and locale — it does not
  depend on what is typed;
- the suggestion list kept every match and sorted it, which for a two-letter query meant
  sorting thousands to show eight. It now keeps the best eight as it scans;
- the summary strip recomputed four corpus-wide counts that never change.

A keystroke on the throttled device went from 88-238 ms to 44-188 ms; the remaining cost
is the filter itself over 4,193 rows, which is the honest price of searching descriptions.

### 12.13 Considered and rejected

A per-repository permalink (`?repo=owner/name`) showing a single card — last commit,
release rhythm, installations, version spread — to serve the "should I install this one
thing" question rather than the browsing one. Raised after a tester said he never browses
HACS and only ever installs something specific. **Not for this project.** HACS Trends
answers ranking questions; the single-repository lookup is a different tool.

### 12.14 The phone gets its own layout

The table could not survive on a phone and had not been looked at since it was built. Its
columns are fixed pixels adding up to 694, so on a 390px screen the browser widened the
document to **720px** and shrank the whole page: half the columns past the right edge,
everything unreadably small, two-axis scrolling. On top of that the header — title,
four-line explanation, period strip, search, language picker, four summary tiles, column
headings — pushed the first row to **539px down an 844px screen**.

Below 900px there is now no grid at all. Each row is a card that lays itself out:

- the figure the current view ranks by, in the largest type, on the right, with its own
  label — a ranking whose reason is invisible is just a list. It follows the view: star
  growth in the trend views, installations in "Actually used", releases in "Ships
  reliably", the last commit in the maintenance view;
- name and version on the first line, two lines of description, and **two** further values
  underneath, never three: a third one wraps for exactly those repositories that have
  installation figures, and a row whose height depends on whether a number happens to
  exist looks broken. Whatever the big figure already says is left out;
- the view chooser becomes scrolling chips, the heading disappears (the active chip
  already says it), the language picker moves up beside the brand, and the explanation
  plus the four summary figures fold behind one line.

| | before | after |
|---|---|---|
| document width at 390px | 720px | **390px** |
| first row | 539px | **262px** |
| rows visible | ~2 (scaled down) | **7** |

Checked at 360, 390 and 768px, in all seven views, in German (the longer labels), scrolled
deep into the list: no card overflows its height, no horizontal scrolling anywhere, no
console errors. The desktop layout is untouched — above 900px the same renderer still
produces the table.

Deliberate loss: the column headings are gone on a phone, and with them the ability to
re-sort by tapping one. Each view has a sensible sort of its own; a sort control for
phones would be its own piece of work.

### 12.15 The interface stops explaining itself

The view descriptions had a pattern the author did not see until a reader named it: they
**justified the design** instead of saying what the list shows. "so that small projects do
not disappear", "a project has to be strong in both", "the placement is never a black
box" — answers to objections nobody had raised, in the one place on screen where space is
most expensive. 1,953 characters across seven views, now 467.

The rule they were rewritten under: the heading asks the question; the line underneath
names **what is sorted** and **what limits the list**, as fact. No "so that", no "which
means", no reassurance. Where a limit is a property of the data — 25 stars, integrations
only, the release ceiling — it stays. Everything else moved to the README section this
round added, which is linked from the rail.

Two structural corrections came with it:

- **"Installation trends begin on …" was in the header while the table sat wordlessly
  empty.** It is a state, not an explanation, and now appears in the empty table area,
  which is where the reader is looking when they wonder why nothing is there.
- **"Real momentum" was jargon.** So was "percentile rank", which the first rewrite
  introduced while removing the first offence. The view is called "Gaining and in use" and
  says "Gaining stars and installations at the same time."

One collision showed up while building. The status labels were changed to name their
threshold — "over a year", "over two years" — because "long quiet" against "very long
quiet" is not a difference anyone can read. But the cell also shows the measured distance,
so it read "over a year   14 mo": the same thing twice. The cell now shows the coloured dot
and the figure, and the word is on the tooltip for anyone who cannot read the colour. That
also makes the table match the phone layout, which already did it that way.

### 12.16 "New in HACS" had nothing to rank by

The view sorted by `first_seen`, which is derived from the daily slices — and there are
two of them. All 4,193 repositories carried 2026-09-05, the day this project started
collecting. The list was sorted by a constant and nobody could tell.

HACS keeps its store as plain lists in `github.com/hacs/default`, one file per category,
each a JSON array of "owner/name". The day a repository was accepted is therefore the
first commit that added its line. Measured before building anything:

| | |
|---|---|
| clone | 5.7 MB, 4 s |
| walking 4,903 commits | 1.3 s |
| repositories matched | **4,171 of 4,193 (99.5 %)** |
| entries stamped 2019-10-20 | 206 (122 still in the store) |
| no date at all | 22 |

No API, no token, exact back to 20 October 2019. It also answers a question the project
could not answer before: **1,680 of the current repositories were accepted in 2026 and
1,071 in 2025** — against 160 in 2024 and 168 in the whole of 2019.

Two honest limits are on the page rather than in a footnote. The 2019-10-20 entries come
from the commit that created the list out of an older location; those repositories were in
HACS before the record begins, so the column says "since the start" instead of printing a
day that is not theirs. The 22 without a date show a dash with the reason on the tooltip.

`first_seen` stays as the fallback for anything accepted after our collection begins but
not yet reflected in the list.

### 12.17 Local checking

`./run.sh check` runs in seconds without a token or a network: `node --check` on the front
end, the translation guard (unknown keys, mismatched placeholders, completeness), a
compile pass over the Python, YAML parsing of both workflows when PyYAML happens to be
installed, and the collector's test suite. It catches what typing breaks. It does not
replace opening the page.

What can and cannot be checked before a push, honestly:

- **Front end** — fully, locally, in seconds. Serve `web/` and look; the committed
  `data.json` is real data.
- **Collector and export** — with a database. The changed step alone against a copy is
  usually enough; the full chain is `./run.sh build`, about twelve minutes.
- **The workflow itself** — not at all beyond YAML syntax. Ordering, action versions and
  permissions only show up in a real run, and two of this project's failures were exactly
  that. A branch is the cheap mitigation: the workflow can be dispatched there, and it
  builds and commits its slice without touching the published page.

`run.sh` also now notices a virtual environment whose interpreter has gone. That happens
after a Python upgrade, after moving the folder, or — as it did here — when the same
checkout is used from a second machine and the symlinks end up pointing into the other
one's filesystem. The directory still exists, so the old check passed and every command
then failed with "No such file or directory", which reads like a broken script rather than
a stale link. It is now recreated instead.

## 13. Round three — the header seam, the run stamp, and what the search misses

Six reports, of which two turned out to be defects and one turned out to be a wrong
assumption worth recording.

### 13.1 Two figures suspected of being hard-coded; one was

The report was that `4,193 repositories` and the growth view's `2,101 of 3,248 matched`
looked baked in. Neither is: `counts.repos` is `len(repos)` with no filter in front of it,
`coverage.total` is the same number, and the caption is a template filled from
`meta.analytics` on each render. Every view was checked the same way.

One number was genuinely written twice. `MIN_PCT_BASE = 25` decides which repositories get
a growth percentage at all, in `export.py` — and `app.js` printed a literal `25` in the
caption that explains the cut-off. Two places, one of which would eventually have been
changed alone, and the page would then have described a rule the figures were not computed
with. It now travels in `meta.thresholds.min_pct_base`, with the literal kept only as a
fallback for payloads written before this change.

### 13.2 The header seam

The brand block and the head bar meet at one horizontal border, and it did not line up.
Measured at 1440px: 89.0px against 81.3px. Both blocks sized themselves from their
content, so the break was not a constant — it varied with the width, and with the
language, because `4.193 Repositories · 06. Sept. 2026` wraps inside a 212px rail and the
English stamp does not.

A shared `--topbar` height with the content centred in it fixes the wide case. It does not
fix everything: between 900 and roughly 1240px the head bar wraps the search box onto a
second row and grows past any fixed value. Measured across that band before the change:
-75.3, -70.5, -24.5, -5.8. CSS cannot tell one block the other's height, so the head is
measured at its natural height after clearing the property — which leaves the 92px
stylesheet floor in place — and the brand is told to match. The value written back is the
height already reached, so it settles in one pass.

Verified at 960, 1024, 1120, 1240, 1360, 1440, 1600 and 1920px, in both languages, across
all seven views, and under live resizing including a trip through the phone layout and
back: 0.0px everywhere.

### 13.3 "What this view shows · 4 figures" on the desktop

A missing base rule, not a text. `.disclose` is styled only inside the phone media query,
where it gets `display:flex!important`. Outside it the element is a plain `<button>`, and
`boot()` sets `hidden = false` unconditionally, so it rendered under the head bar on every
desktop, 23px tall. `.disclose{display:none}` in the base sheet; the phone rule carries
`!important` and still wins there.

### 13.4 A run stamp instead of a date

The stamp said `06. Sept. 2026` and left the reader to decide whether that was today. It
now reads `Letzter Lauf vor 3 Stunden`, from `generated_at` against the reader's own clock,
with the exact local time on the tooltip. The long forms come from
`Intl.RelativeTimeFormat` rather than the translation files: the table's own units are
clipped for a column ("3 T"), which reads badly as a sentence in the rail.

What happens when the collector stops was checked rather than assumed. `sync.yml` has no
`continue-on-error` on the collecting step, so a failure aborts the job and nothing is
deployed: the page keeps its last good `data.json` and the stamp ages in place, which is
the honest outcome and the one wanted.

The case the run stamp cannot cover on its own is a green run whose newest snapshot is
older than the run itself — the page is fresh, the data is not. Then, and only then, a
third line appears in the warning colour: `Daten vom 03. Sept. 2026`. It is driven by
comparing `meta.day` against the date part of `generated_at`, and it stays hidden when they
agree, which is the normal case.

### 13.5 The footer points at the repository

`Wie die Zahlen entstehen →` gave way to `GitHub →` on the project repository. The sources
line above it stays plain text: the "GitHub" in `HACS · Home Assistant analytics · GitHub`
names a data source, and hanging the project's own link on that word would send the reader
somewhere the word does not promise.

### 13.6 Search: topics in, and the multi-word case

The search already covered the description — the assumption that it did not was wrong. The
gap was GitHub topics, which sit in the payload as `tp` on 3,776 of 4,193 repositories and
were never indexed. Measured: "skoda" 1 → 2, "heatpump" 14 → 24, "solar" 99 → 137, at
+136 kB of haystack.

What they mostly buy is a spelling gap rather than hidden knowledge. The rows that "heatpump"
newly finds are `Quatt`, `Lambda Heat Pumps`, `Heat Pump Card`, `Qvantum Heat Pump` — all of
them self-evident from the name, missing only because the description writes "heat pump" with
a space and the topic does not. That measurement killed a planned feature: chips in the row
showing which topic matched. They would have explained what the row already says. The
genuine oddities that remain — `bermuda` under "energy", via `bluetooth-low-energy` — are
word ambiguity, which no amount of labelling fixes.

Multi-word queries were a single substring, so "skoda connect" only matched a repository
with that exact sequence somewhere. The query is now split on whitespace and every term has
to match the row, in any field, in any order. A term that matches nothing on its own is
dropped rather than emptying the result: "solar wechselrichter" answers with the 137 rows
for "solar" and the footer says `„wechselrichter" ignoriert — kein Treffer`. If no term
survives, none is dropped — the query is simply wrong and the empty state should say so.

The worry about filler words turned out to be misplaced, and the measurement is the reason
to stop worrying: a keystroke costs 10-25ms including the repaint, and it costs the same
for "a" with 4,192 answers as for "skoda connect" with one. It is one pass over prepared
strings; the number of hits does not enter into it, and the table recycles its rows.

The suggestion dropdown was deliberately left alone. It shows eight entries ranked by
stars, matching names, slugs and domains — "I know which repository I want". Feeding topics
into it would let "energy", with 358 topic matches, push the exact name matches out of the
eight slots. The dropdown stays precise; the table is where breadth belongs.
