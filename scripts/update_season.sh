#!/usr/bin/env bash
# One command: scrape a season, verify it, and rebuild everything the app reads.
#
#   scripts/update_season.sh 2026
#   scripts/update_season.sh 2026 1 WVB 6 10      # division, sport, delay, chunk
#   FORCE=1 scripts/update_season.sh 2026         # rebuild even if coverage is gappy
#
# Stops before rebuilding if the coverage check finds a conference-shaped gap,
# because that means the scrape died mid-conference and the right move is to
# re-run it (checkpoints resume) rather than publish a hole.

set -euo pipefail

YEAR="${1:-2026}"
DIVISION="${2:-1}"
SPORT="${3:-WVB}"
DELAY="${4:-6}"
CHUNK="${5:-10}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SPORT_LC="$(echo "$SPORT" | tr 'A-Z' 'a-z')"
CSV_DIR="data/ncaavolleyballr/data-csv"
PBP="${CSV_DIR}/${SPORT_LC}_pbp_div${DIVISION}_${YEAR}.csv"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

step "1/4  scrape ${YEAR} D${DIVISION} ${SPORT}"
echo "A browser window will open and stay open. Leave it alone."
echo "Safe to interrupt -- every chunk is checkpointed and re-running resumes."
scripts/fetch_season.sh "$YEAR" "$DIVISION" "$SPORT" "$DELAY" "$CHUNK"

step "2/4  verify coverage"
set +e
python3 scripts/check_coverage.py "$YEAR" --division "$DIVISION" --sport "$SPORT_LC"
COVERAGE=$?
set -e
if [ "$COVERAGE" -eq 2 ] && [ -z "${FORCE:-}" ]; then
  cat >&2 <<MSG

Stopping: whole conferences are missing, which means the scrape died inside
them rather than dropping teams at random.

  Re-run the same command -- checkpoints resume and failed chunks are retried:
    scripts/update_season.sh ${YEAR} ${DIVISION} ${SPORT} ${DELAY} ${CHUNK}

  Or rebuild anyway, accepting the hole:
    FORCE=1 scripts/update_season.sh ${YEAR} ${DIVISION} ${SPORT}
MSG
  exit 2
fi

step "3/4  rally table"
if [ ! -f "$PBP" ]; then
  echo "No play-by-play file at ${PBP}." >&2
  echo "The pbp level did not complete. Re-run to retry it." >&2
  exit 1
fi
python3 analytics/rally_engine.py "$PBP" --out-dir data/rallies

step "4/4  match metrics and app data"
YEARS=""
for f in "${CSV_DIR}/${SPORT_LC}_teammatch_div${DIVISION}_"*.csv; do
  [ -e "$f" ] || continue
  y="${f##*_}"; y="${y%.csv}"
  [ -f "data/rallies/${SPORT_LC}_rallies_div${DIVISION}_${y}.parquet" ] && YEARS="${YEARS} ${y}"
done
echo "seasons with both a rally table and box scores:${YEARS}"
# shellcheck disable=SC2086
python3 analytics/build_match_metrics.py --years $YEARS
python3 analytics/build_app_data.py

step "done"
cat <<MSG
${YEAR} is in the app. Check it locally, then publish:

  streamlit run streamlit_app.py
  git add app_data && git commit -m "Add ${YEAR} season data" && git push

Raw data under data/ stays local and gitignored; only app_data/ is committed.
MSG
