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
- **The matchup predictor is three numbers: Elo gap, ridge gap, home edge.**
  `analytics/matchup_model.py`, a logistic fitted on pre-match information only (Elo
  as of the match, ridge refitted weekly on prior matches). It is fitted on every
  completed season except 2021, the Elo burn-in; the current season is never in the
  fit, so it is a live out-of-sample test. Held out a season at a time the blend beat
  either rating alone on log loss in every season, and again on 2026. A weight sliding
  from Elo to ridge as the season fills in gained ~.002 in the four fitted seasons and
  lost on 2026, so it is out, consistent with the composite's own finding.
- **Scorelines are empirical, not independent sets.** Treating sets as coin flips
  predicts 26% sweeps among near-even matches; 35% happen. The 3-0/3-1/3-2 odds come
  from the observed results of favourites of the same size, scaled to the match
  probability. On 2026 every outcome landed within 1.3 points.
- **Expected wins minus actual wins is luck. Say so.** Odd vs even matches r = -0.04,
  first vs second half -0.09, season to season -0.05 to -0.13; the z-scores have sd
  0.97 against 1.00 for pure chance. Do not build a "clutch" feature on this gap.
- **Projected records use today's ratings, held fixed.** `fetch_ncaa_schedule.py`
  reads every date from today to Dec 21 (no early stop, three attempts per date) and
  `matchup_model.py` scores the unplayed matches into `app_data/schedule.parquet`. An
  opponent never seen in a rated match gets the 5th-percentile D1 rating and is named
  in the build output. If no schedule file exists the parquet is deleted rather than
  left stale.

## Open for the 2027 season: the seventh benchmark

Deferred deliberately, not forgotten. Changing a benchmark mid-season would make the
current year's grades incomparable to the ones already published, so this waits for
the rollover.

**Won set 1 does not survive its own test.** Thresholds fitted on 2021-2023 and scored
out of sample on 2024, measured as the lift in win rate between teams that cleared a
benchmark and teams that missed it, split by how long the match went:

    benchmark            3 sets   4 sets   5 sets
    Out-hit opponent     +98.1%   +82.7%   +35.8%
    Side-out %           +85.6%   +58.8%   +24.4%
    Point-score %        +85.9%   +58.9%   +24.4%
    Hit eff / Opp hit    +80.7%   +54.2%   +19.7%
    Ace-to-error         +37.2%   +20.4%    +5.8%
    Won set 1            +99.6%   +33.1%    -1.2%

Won set 1 is the strongest benchmark on the board in a sweep and the only one that is
NEGATIVE in a five-setter. That shape is the signature of a metric restating the
result rather than describing the play: in a three-set match "won set 1" is nearly
"won the match". Pooled across all matches it looks fine, which is how it got in.

Judge any candidate on five-set matches alone. Pooled numbers reward a metric for
being close to the scoreboard. Two candidates were tested and rejected on exactly
that basis -- "first to 20 in 2+ sets" (+94.1% in sweeps, +0.5% in five-setters) and
"swept the opponent", which has zero counterexamples in 49,000 matches because it is
the result, not a correlate of it.

What the out-of-sample five-set lift says about the alternatives:

    rally win %     +0.424   but 99.4% explained by side-out and point-score together,
                             so it is their pooled form and fails the redundancy rule
    kill %          +0.177   usable now; a component of hitting efficiency
    first-ball SO   +0.153   NULL for 2026, the feed cannot reconstruct it
    transition SO   +0.136   NULL for 2026, same reason
    attack error %  +0.123   usable now; the other component of hitting efficiency
    long volleys    +0.102   the most independent thing tested (overlap .26-.36 against
                             out-hit's .36-.66) but needs touch detail, NULL for 2026

At grade level, out of sample on 2024: the current seven score r=0.3756 against winning
inside five-set matches, and simply DROPPING Won set 1 scores 0.4050 -- better than any
replacement tried. Season-level correlation barely moves (0.8331 to 0.8271).

So the live recommendation for 2027 is six benchmarks rather than a substitution,
unless the feed regains touch detail, in which case long volleys is worth re-testing
as a seventh because it measures something nothing else on the board does.


## App conventions

- Eight tabs. Every page ends with an **Ask an LLM** panel (a Markdown export of what the
  page is showing) and a **Download table (PNG)** button. Both are expected on a new
  page; `ask_panel()` and `app/png.py` are the shared helpers.
- Tables are hand-built HTML against `table.grid`, not `st.dataframe`. The PNG export
  collects its plain cells in the same loop that emits the markup so the two cannot
  drift.
- Explanations live in a collapsible `st.expander` above the table, in the app's own
  voice: what it measures, what was ruled out, and why.
- The Volleyball 7 season column carries a rank in parentheses. It ranks each team's
  *season average* on that metric, from `D.metric_ranks`, over teams with five or more
  graded matches — never a rank of the single match beside it. The radio offers
  national or conference, and "conference" means each side inside its own, so a
  cross-conference pairing ranks the two in different pools. It reads "Big Ten" only
  when both sides share a conference.
- The Matchup Predictor and Expected Wins read `matchup_model.json` and
  `match_predictions.parquet`, both written by `analytics/matchup_model.py` in stage
  11 of the pipeline. The predictor uses the published `power_ratings` (ridge + Elo),
  which match the training features exactly; keep it that way, or the coefficients
  stop meaning what they were fitted to mean.
- `matplotlib` is required for the PNG export. It fails soft — no button rather than a
  broken page — so a missing dependency is silent. Check for the button, not an error.

## Testing

Claims about the app are verified by driving it in a real browser, not by reading the
diff. Chromium and Playwright are available. Start it headless on a spare port, click
each tab, download what the page offers, and assert on what came back. Several
regressions here were caught that way and would have shipped otherwise.
