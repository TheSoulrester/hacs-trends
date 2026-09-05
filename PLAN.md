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

### Known defect, not yet fixed

`releases_year` **saturates at 30** because only 30 release nodes are fetched. The top
of the "Ships reliably" ranking is therefore all ties at 30, decided by the commit
tiebreaker rather than by releases. Fix: a second pass fetching 100 nodes for the ~1,147
repositories that hit the ceiling (~23 queries), and display anything still at the
ceiling as "100+" rather than as an exact number.

### Still open

- Which GitHub account and repository name the project lives under.
- Whether the Internet Archive holds enough captures of the analytics file to backfill
  installation history.
- Sparkline payload size — estimated, never measured.
- 773 repositories gained no stars at all in 60 weeks. Worth surfacing as its own fact.
