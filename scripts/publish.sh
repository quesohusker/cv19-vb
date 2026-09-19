#!/usr/bin/env bash

set -euo pipefail

YEAR=2026
ASSUME_YES=0
SKIP_UPDATE=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    --skip-update) SKIP_UPDATE=1 ;;
    [0-9][0-9][0-9][0-9]) YEAR="$arg" ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

DIRTY="$(git status --porcelain -- . ':!app_data' | head -5)"
if [ -n "$DIRTY" ]; then
  echo "Uncommitted changes outside app_data:" >&2
  echo "$DIRTY" >&2
  echo >&2
  echo "Commit or stash them first, so the publish commit contains only data." >&2
  exit 1
fi

if [ "$SKIP_UPDATE" -eq 0 ]; then
  step "build ${YEAR}"
  scripts/update_season_api.sh "$YEAR"
fi

step "what would be published"
if git diff --quiet -- app_data && git diff --cached --quiet -- app_data; then
  echo "app_data is unchanged -- nothing new to publish."
  echo "(If the season has new matches, the pipeline may have found none yet.)"
  exit 0
fi
git diff --stat -- app_data

"${ROOT}/.venv/bin/python" - "$YEAR" <<'PY' || true
import subprocess, sys, io
import pandas as pd
year = sys.argv[1]
try:
    old = pd.read_parquet(io.BytesIO(subprocess.run(
        ["git", "show", "HEAD:app_data/matches.parquet"],
        capture_output=True, check=True).stdout), columns=["season", "team"])
    new = pd.read_parquet("app_data/matches.parquet", columns=["season", "team"])
    o, n = len(old[old.season == year]), len(new[new.season == year])
    print(f"\n  {year}: {o:,} -> {n:,} team-match rows  ({n - o:+,})")
    print(f"  all seasons: {len(old):,} -> {len(new):,}")
    lost = sorted(set(old.season.unique()) - set(new.season.unique()))
    if lost:
        print(f"  WARNING: these seasons would disappear: {', '.join(lost)}")
except Exception as e:
    print(f"  (could not diff matches.parquet: {e})")
PY

if [ "$ASSUME_YES" -eq 0 ]; then
  echo
  read -r -p "Publish to GitHub? This redeploys the live app. [y/N] " reply
  case "$reply" in [yY]*) ;; *) echo "Not published."; exit 0 ;; esac
fi

step "publish"
git add app_data
git commit -q -m "Update ${YEAR} season data"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
for attempt in 1 2 3 4; do
  if git push -u origin "$BRANCH"; then break; fi
  [ "$attempt" -eq 4 ] && { echo "Push failed after 4 attempts." >&2; exit 1; }
  if ! git diff --quiet "$BRANCH" "origin/$BRANCH" 2>/dev/null; then
    echo "  the remote moved; rebasing onto it and retrying"
    git pull --rebase --quiet || {
      echo "Rebase hit a conflict. Resolve it, then: git push" >&2; exit 1; }
    continue
  fi
  sleep $((2 ** attempt))
done

step "done"
echo "Pushed. Streamlit Cloud redeploys on its own, usually within a minute or two."
