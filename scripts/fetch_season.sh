#!/usr/bin/env bash
# Fetch an NCAA volleyball season that ncaavolleyballr does not ship yet.
#
# The package gates every scrape on a hardcoded most_recent_season(), bumped by hand
# each year, and its bundled team-ID table stops at the same season. This patches both
# and then scrapes, in stages, because the team table has to be rebuilt and the package
# reinstalled before the stats functions can see the new season.
#
#   stage 1  clone the package
#   stage 2  patch most_recent_season() to the target year
#   stage 2b route get_teams() through headless Chrome -- stats.ncaa.org 403s plain
#            HTTP no matter the user agent, but a real browser gets through
#   stage 3  install the patched package
#   stage 4  discover the season's team IDs live, rebuild the team table
#   stage 5  reinstall so the stats functions can see them
#   stage 6  scrape, chunked and resumable
#
# Usage:  scripts/fetch_season.sh [year] [division] [sport] [delay] [chunk]

set -euo pipefail

YEAR="${1:-2026}"
DIVISION="${2:-1}"
SPORT="${3:-WVB}"
DELAY="${4:-3}"
CHUNK="${5:-10}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG_DIR="${REPO_ROOT}/.ncaavolleyballr-src"
OUT_DIR="${REPO_ROOT}/data/ncaavolleyballr/data-csv"

command -v Rscript >/dev/null || { echo "Rscript not found. Install R first."; exit 1; }

echo "=== stage 1: package source ==="
if [ -d "${PKG_DIR}/.git" ]; then
  echo "  already cloned at ${PKG_DIR}"
else
  git clone --depth 1 https://github.com/JeffreyRStevens/ncaavolleyballr "${PKG_DIR}"
fi

echo "=== stage 2: patch the season gate to ${YEAR} ==="
GATE_FILE="${PKG_DIR}/R/utils.R"
grep -q "most_recent_season" "${GATE_FILE}" || { echo "most_recent_season() not found; upstream changed."; exit 1; }
# replace the integer the function returns, whatever it currently is
perl -0pi -e "s/(most_recent_season <- function\(\)\s*\{\s*)\d{4}/\${1}${YEAR}/s" "${GATE_FILE}"
echo -n "  now returns: "
perl -0ne 'print $1 if /most_recent_season <- function\(\)\s*\{\s*(\d{4})/s' "${GATE_FILE}"; echo

echo "=== stage 2b: route get_teams() through headless Chrome ==="
python3 "${REPO_ROOT}/scripts/patch_get_teams.py" "${PKG_DIR}"

echo "=== stage 3: install patched package ==="
Rscript -e 'if (!requireNamespace("devtools", quietly=TRUE)) install.packages("devtools", repos="https://cloud.r-project.org")'
Rscript -e "devtools::install('${PKG_DIR}', upgrade = FALSE, quick = TRUE)"

echo "=== stage 4: discover ${YEAR} division ${DIVISION} team IDs ==="
Rscript "${REPO_ROOT}/scripts/r/discover_teams.R" "${PKG_DIR}" "${YEAR}" "${SPORT}" "${DIVISION}"

echo "=== stage 5: reinstall with the new team table ==="
Rscript -e "devtools::install('${PKG_DIR}', upgrade = FALSE, quick = TRUE)"

echo "=== stage 6: scrape (resumable -- safe to re-run) ==="
Rscript "${REPO_ROOT}/scripts/r/scrape_season.R" \
  "${YEAR}" "${DIVISION}" "${SPORT}" "${OUT_DIR}" "${DELAY}" "${CHUNK}"

cat <<MSG

Scrape finished. Now rebuild the app data:

  python analytics/rally_engine.py ${OUT_DIR}/$(echo "${SPORT}" | tr 'A-Z' 'a-z')_pbp_div${DIVISION}_${YEAR}.csv --out-dir data/rallies
  python analytics/build_match_metrics.py --years 2021 2022 2023 2024 2025 ${YEAR}
  python analytics/build_app_data.py

then commit app_data/ and the app picks up ${YEAR}.
MSG
