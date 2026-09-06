# Fetching a season the package does not ship yet

`ncaavolleyballr` publishes scraped CSVs only after a season completes, and it gates
every scrape on a hardcoded `most_recent_season()` that the maintainer bumps by hand
each year. Its bundled team-ID table stops at the same season. So an in-progress
season needs both the gate patched and the team table rebuilt.

`fetch_season.sh` does that end to end:

```bash
scripts/fetch_season.sh 2026            # women's D1, 3s delay, chunks of 10
scripts/fetch_season.sh 2026 1 WVB 5 5  # gentler: 5s delay, chunks of 5
```

Smoke-test the chain on a few teams before an hours-long run, to confirm the
season returns the columns the pipeline expects:

```bash
Rscript scripts/r/scrape_season.R 2026 1 WVB /tmp/vb-smoke 3 4 4
```

Stages: clone the package, patch the gate, install, discover the season's team IDs
live from stats.ncaa.org, rebuild the team table, reinstall, then scrape.

## stats.ncaa.org blocks plain HTTP

Confirmed on 2026-09-06: every plain-HTTP request returns **403 Forbidden**,
including for seasons the package already ships data for, and including with a
genuine Chrome user-agent string. It is fingerprinting the client, not reading
headers.

Headless Chrome gets through. The same URL that 403s over httr2 returns 348 team
links via `rvest::read_html_live()`.

The package already knows this -- its stats functions go through
`request_live_url()`, which wraps `read_html_live()`. Only `get_teams()` still
used plain `request_url()`, which is why team discovery was the step that failed.
`patch_get_teams.py` rewrites its two request sites to use the browser path, and
the driver applies it automatically at stage 2b.

Consequence: the scrape drives a real browser, so it is slower and Chrome will
open and close repeatedly. That is expected.

## Requirements

- R (any recent version) and `devtools`
- Google Chrome — several of the package's scrapers fall back to a headless browser
  via `chromote`, because some stats.ncaa.org pages need JS to render
- Patience. The maintainer's own 0.5.1 notes say "the NCAA is making it very difficult
  to scrape lots of data at once"; they could not finish D2/D3 for 2025. Expect hours
  over ~340 D1 teams, and expect to be throttled.

## It is resumable, and that matters

The scrape walks teams in chunks and checkpoints each one to
`data/checkpoints/<sport>_<year>/`. If it dies at team 300, re-run the same command
and it picks up from the last good chunk. Failed chunks are deliberately left
uncached so a re-run retries them.

Levels are scraped most-valuable-first: `teammatch` and `pbp` alone are enough to
light up the entire app, so if you stop early you still have something usable.
`teamseason` and `playermatch` only add player-level views.

Delete the checkpoints only once the CSVs look right.

## Check coverage before trusting a scrape

When a team page times out, `ncaavolleyballr` warns and returns `invisible()` for
that team, and the surrounding chunk still succeeds. A scrape can therefore print
`ok` the entire way through and still be missing teams. That is not hypothetical --
it is how the shipped 2025 D1 data ended up missing 34 teams in conference-shaped
blocks while every team present had a full schedule.

Chromote timeouts during the run (`timed out waiting for response to command
Page.navigate`) are retried internally and are usually harmless, but they are the
mechanism by which this happens. So always check:

```bash
python scripts/check_coverage.py 2026
```

It reports row and team counts, flags teams with suspiciously few matches, and
diffs against the prior season -- marking any conference that vanished entirely.
Conference-shaped gaps mean the scrape died inside those conferences; re-run the
same fetch command and the checkpoints will resume and retry the failed chunks.

## Output

Files land in `data/ncaavolleyballr/data-csv/` named exactly as the Python pipeline
expects, e.g. `wvb_teammatch_div1_2026.csv` — no renaming needed. Then:

```bash
python analytics/rally_engine.py data/ncaavolleyballr/data-csv/wvb_pbp_div1_2026.csv --out-dir data/rallies
python analytics/build_match_metrics.py --years 2021 2022 2023 2024 2025 2026
python analytics/build_app_data.py
```

Commit `app_data/` and the app picks up the new season.

## A caveat on mid-season data

Benchmark thresholds were calibrated on completed seasons. A team with eight matches
has a noisy grade and a thin power rating. The rankings page has a minimum-matches
slider for exactly this reason; set it higher early in a season.

## Tested how far

The scrape and discovery scripts were exercised end to end against a stub package
offline: chunking, checkpointing, resume, the list-vs-data-frame shapes the two level
types return, and the output filenames. What could **not** be tested is the live
scrape itself — stats.ncaa.org is unreachable from the environment these were written
in. Expect to debug the network-facing parts on first run.
