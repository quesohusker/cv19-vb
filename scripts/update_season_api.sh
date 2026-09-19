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
PLAYERMATCH="${GIS_DIR}/public/data/wvb_playermatch_div1_${YEAR}.csv"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

step "1/9  box-score source"
if [ -d "${GIS_DIR}/.git" ]; then
  echo "  updating ${GIS_DIR}"
  git -C "${GIS_DIR}" pull --ff-only --quiet || echo "  (pull skipped; using what is on disk)"
else
  echo "  cloning volleyball-gis into ${GIS_DIR} (~400 MB)"
  git clone --depth 1 https://github.com/jpitel24/volleyball-gis "${GIS_DIR}"
fi
[ -f "${PLAYERMATCH}" ] || { echo "No ${PLAYERMATCH}. That season is not published there." >&2; exit 1; }

step "2/9  match results (ncaa-api scoreboard, ~25 requests)"
"$PY" data_collection/fetch_ncaa_results.py "${YEAR}"

step "3/9  team box scores"
"$PY" data_collection/ingest_gis_boxscores.py "${YEAR}" \
  --gis-dir "${GIS_DIR}/public/data" --results "${RESULTS}"

step "4/9  play-by-play (one request per match -- the long one, resumable)"
echo "Safe to interrupt: every match is cached and re-running fetches only what is missing."
"$PY" data_collection/fetch_ncaa_pbp.py "${YEAR}" ${PBP_LIMIT:+--limit "${PBP_LIMIT}"}

step "5/9  rally table"
"$PY" analytics/rally_from_ncaa_api.py "${YEAR}" --serve-attempts "${PLAYERMATCH}"

step "6/9  match metrics and app data"
YEARS=""
for f in data/ncaavolleyballr/data-csv/wvb_teammatch_div1_*.csv; do
  [ -e "$f" ] || continue
  y="${f##*_}"; y="${y%.csv}"
  [ -f "data/rallies/wvb_rallies_div1_${y}.parquet" ] && YEARS="${YEARS} ${y}"
done
echo "seasons with both a rally table and box scores:${YEARS}"
"$PY" analytics/build_match_metrics.py --years $YEARS
"$PY" analytics/build_app_data.py

step "7/9  in-system kill share"
"$PY" analytics/in_system_kills.py "${YEAR}" --gis-dir "${GIS_DIR}/public/data"

step "8/9  position rankings for individual players"
PLAYER_YEARS=""
for f in "${GIS_DIR}"/public/data/wvb_playermatch_div1_*.csv; do
  [ -e "$f" ] || continue
  y="${f##*_}"; PLAYER_YEARS="${PLAYER_YEARS} ${y%.csv}"
done
"$PY" analytics/build_player_ratings.py --gis-dir "${GIS_DIR}/public/data" \
  --years $PLAYER_YEARS --current-season "${YEAR}"

step "9/9  elo ratings"
"$PY" analytics/elo_ratings.py

step "done"
cat <<MSG
${YEAR} is in the app. Check it, then publish:

  streamlit run streamlit_app.py
  git add app_data && git commit -m "Add ${YEAR} season data" && git push

If stage 4 was interrupted, re-run this script -- it resumes and only the
matches already fetched contribute to the rally table until then.
MSG
