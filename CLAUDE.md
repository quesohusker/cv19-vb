# QuesoHusker's Volleyball

A Streamlit app over precomputed NCAA women's D1 volleyball tables. `streamlit_app.py`
is a read-only front end; everything it shows is built by the pipeline into `app_data/`.

## Running the pipeline

```bash
./scripts/publish.sh 2026          # update, show a diff, ask, commit, push
./scripts/update_season_api.sh 2026    # rebuild only, no publish
./scripts/publish.sh 2026 --skip-update    # publish what is already built
```

Eleven stages. 1 refresh the volleyball-gis clone (back years only), 2-4 ncaa-api
scoreboard, player box scores and the playermatch CSV built from them, 5 team box
scores, 6-7 play-by-play and rallies, 8 match metrics and app data, 9 in-system kill
share, 10 player ratings, 11 Elo and the composite. `NCAA_API_BASE` points the fetch
stages at a self-hosted ncaa-api instead of the rate-limited public demo.

`publish.sh` refuses to run while anything outside the published data is dirty. The
published set is `app_data/` plus `data/in_system_kills.parquet`, both of which the
pipeline rewrites every run.

## Where the data comes from, and the difference that keeps biting

Two sources, and confusing them wastes hours:

- **ncaa-api** (`ncaa-api.henrygd.me`) supplies the scoreboard (who won, set scores),
  the play-by-play, and, since late September 2026, the current season's player box
  scores (`fetch_ncaa_boxscores.py` -> `build_playermatch.py` -> `data/playermatch/`,
  written in volleyball-gis's column layout so every reader works unchanged).
- **`../volleyball-gis`** (a GitHub repo) is the only source of player box scores for
  2021-2025, which the player boards' fixed thresholds are fitted on. Stage 4 copies
  those seasons into `data/playermatch/`. It stopped publishing 2026 after 2026-09-20,
  which is why the current season moved off it.

Stage 2 reporting "195 final of 195" means the SCOREBOARD is complete for that date.
It says nothing about whether box scores exist; stage 3 reports that separately, and a
contest that returns no player rows is left uncached and retried on the next run.

`build_match_metrics.py` inner-joins box to rally, so a match missing from either
source is absent entirely. Note `build_match_metrics.py:159` turns a blank stat into
**0.0**, not null: any change that admits partial matches has to fix that first, or a
missing box score becomes a real zero and poisons the grade and the league baselines.

## Decisions that were tested, and should not be quietly reversed

Each of these was measured out of sample. The numbers live in the relevant commit
message and module docstring; read those before changing any of it.

- **The power rating is a 50/50 blend of a ridge model and Elo.** Weight fitted, not
  chosen: trained on three seasons and tested on the fourth it returned 52/49/50/49.
- **Strength of schedule is computed and published but carries ZERO weight.** It
  fitted to 12% and was the global optimum of 1,326 weights, and it improved
  calibration. It also changed 424 picks out of 12,508 for a net of *zero* extra
  correct and moved nobody in or out of the top 25. The ridge already adjusts for
  opponents; counting schedule twice to move nothing is a bad trade. It has its own
  page instead. `SOS_WEIGHT` in `analytics/composite_ratings.py` is the one number to
  change if this is ever revisited.
- **The ridge penalty stays at lambda 1.0.** Lowering it looks attractive on the ridge
  alone (~.008 of log loss) but is worth only .0007 at the system level, because Elo
  and SOS were already covering the same gap. Lambda 0 is not merely worse, it is
  broken: the schedule graph is disconnected in week one and the solve fails outright.
- **Player boards split by what a player did, not what the roster called her.** 43% of
  players listed as outside hitters almost never touch serve receive. Boards are
  "six-rotation" and "front-row", split at the 37th percentile of each season's
  attackers.
- **Charted quality is mostly unusable.** Reception, serve and block quality are
  scorer-contaminated (charted pass quality correlates +0.54 between teammates, higher
  than its own year over year). Only dig quality survived, and only for back row.
- **Wins and losses are not an input to any rating.** Tested: with the rating present,
  win% carries a negative coefficient. "Wins more than its rallies say" is schedule
  strength, not clutch, and the apparent skill vanishes once schedule is controlled.

## App conventions

- Six tabs. Every page ends with an **Ask an LLM** panel (a Markdown export of what the
  page is showing) and a **Download table (PNG)** button. Both are expected on a new
  page; `ask_panel()` and `app/png.py` are the shared helpers.
- Tables are hand-built HTML against `table.grid`, not `st.dataframe`. The PNG export
  collects its plain cells in the same loop that emits the markup so the two cannot
  drift.
- Explanations live in a collapsible `st.expander` above the table, in the app's own
  voice: what it measures, what was ruled out, and why.
- `matplotlib` is required for the PNG export. It fails soft — no button rather than a
  broken page — so a missing dependency is silent. Check for the button, not an error.

## Testing

Claims about the app are verified by driving it in a real browser, not by reading the
diff. Chromium and Playwright are available. Start it headless on a spare port, click
each tab, download what the page offers, and assert on what came back. Several
regressions here were caught that way and would have shipped otherwise.
