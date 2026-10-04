#!/usr/bin/env bash

set -euo pipefail

YEAR="${1:-2026}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="python3"
fi
if ! "$PY" -c "import pyarrow, duckdb, pandas" 2>/dev/null; then
  cat >&2 <<'HINT'
Missing Python dependencies. Create the project virtualenv once:

  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt

Then re-run this script. It picks .venv up on its own.
HINT
  exit 1
fi

GIS_DIR="${GIS_DIR:-$ROOT/../volleyball-gis}"
RESULTS="data/ncaa_api/results_volleyball-women_d1_${YEAR}.json"
# Player box scores come from the ncaa-api now, not volleyball-gis, and land here in
# the shape volleyball-gis published. See data_collection/build_playermatch.py.
PM_DIR="${PM_DIR:-data/playermatch}"
PLAYERMATCH="${PM_DIR}/wvb_playermatch_div1_${YEAR}.csv"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

# Stages 2, 3 and 6 make ~4,400 requests between them -- two per match plus the
# scoreboard. Against the public demo instance that is slow and impolite; against a
# local container it is neither.
API="${NCAA_API_BASE:-https://ncaa-api.henrygd.me}"
echo "ncaa-api: ${API}"
case "${API}" in
  *ncaa-api.henrygd.me*)
    cat <<'HINT'
  That is the author's public demo instance, rate limited to 5 req/sec. For a full
  season, self-host instead and re-run:
    docker run -d -p 3000:3000 henrygd/ncaa-api
    export NCAA_API_BASE=http://localhost:3000
HINT
    ;;
esac

step "1/11  historical player box scores (volleyball-gis, back years only)"
# volleyball-gis stopped publishing partway through the 2026 season, so it is no longer
# the current-season source -- stages 3 and 4 below replace it. It is still the only
# source for 2021-2025, which build_player_ratings fits its fixed thresholds on, so the
# clone is kept up to date and stage 4 copies those seasons in beside the generated one.
if [ -d "${GIS_DIR}/.git" ]; then
  echo "  updating ${GIS_DIR}"
  git -C "${GIS_DIR}" pull --ff-only --quiet || echo "  (pull skipped; using what is on disk)"
else
  echo "  cloning volleyball-gis into ${GIS_DIR}"
  git clone https://github.com/jpitel24/volleyball-gis "${GIS_DIR}"
fi

step "2/11  match results and the rest of the schedule (ncaa-api scoreboard)"
"$PY" data_collection/fetch_ncaa_results.py "${YEAR}"
# Every date from today to Dec 21, read fresh each run. Never fails the pipeline: a run
# that gets nothing keeps the previous schedule, and stage 11 projects from it.
"$PY" data_collection/fetch_ncaa_schedule.py "${YEAR}"

step "3/11  player box scores (one request per match -- resumable)"
echo "Safe to interrupt: every match is cached and re-running fetches only what is missing."
"$PY" data_collection/fetch_ncaa_boxscores.py "${YEAR}" ${BOX_LIMIT:+--limit "${BOX_LIMIT}"}

step "4/11  playermatch CSV (drop-in for the volleyball-gis file)"
"$PY" data_collection/build_playermatch.py "${YEAR}" \
  --out-dir "${PM_DIR}" --gis-dir "${GIS_DIR}/public/data" --import-historical
[ -f "${PLAYERMATCH}" ] || { echo "No ${PLAYERMATCH} -- stage 4 produced nothing." >&2; exit 1; }

step "5/11  team box scores"
"$PY" data_collection/ingest_gis_boxscores.py "${YEAR}" \
  --gis-dir "${PM_DIR}" --results "${RESULTS}"

step "6/11  play-by-play (one request per match -- the long one, resumable)"
echo "Safe to interrupt: every match is cached and re-running fetches only what is missing."
"$PY" data_collection/fetch_ncaa_pbp.py "${YEAR}" ${PBP_LIMIT:+--limit "${PBP_LIMIT}"}

step "7/11  rally table"
"$PY" analytics/rally_from_ncaa_api.py "${YEAR}" --serve-attempts "${PLAYERMATCH}"

step "8/11  match metrics and app data"
YEARS=""
for f in data/ncaavolleyballr/data-csv/wvb_teammatch_div1_*.csv; do
  [ -e "$f" ] || continue
  y="${f##*_}"; y="${y%.csv}"
  [ -f "data/rallies/wvb_rallies_div1_${y}.parquet" ] && YEARS="${YEARS} ${y}"
done
echo "seasons with both a rally table and box scores:${YEARS}"
"$PY" analytics/build_match_metrics.py --years $YEARS
"$PY" analytics/build_app_data.py

step "9/11  in-system kill share"
"$PY" analytics/in_system_kills.py "${YEAR}" --gis-dir "${PM_DIR}"

step "10/11  position rankings for individual players"
PLAYER_YEARS=""
for f in "${PM_DIR}"/wvb_playermatch_div1_*.csv; do
  [ -e "$f" ] || continue
  y="${f##*_}"; PLAYER_YEARS="${PLAYER_YEARS} ${y%.csv}"
done
"$PY" analytics/build_player_ratings.py --gis-dir "${PM_DIR}" \
  --years $PLAYER_YEARS --current-season "${YEAR}"

step "11/11  elo ratings, the composite power ranking, and the matchup predictor"
"$PY" analytics/elo_ratings.py
"$PY" analytics/composite_ratings.py
# Refits nothing on the current season: its coefficients come from completed seasons
# only, so this re-scores the new matches out of sample and rebuilds expected wins.
"$PY" analytics/matchup_model.py

step "done"
cat <<MSG
${YEAR} is in the app. Check it, then publish:

  streamlit run streamlit_app.py
  git add app_data && git commit -m "Add ${YEAR} season data" && git push

If stage 4 was interrupted, re-run this script -- it resumes and only the
matches already fetched contribute to the rally table until then.
MSG
