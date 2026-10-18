#!/usr/bin/env bash
#
# Mirror the whole project -- code, git history, app_data, and every downloaded and
# derived file under data/ -- to a second drive.
#
# WHY. The current season's source data is excluded from git on purpose (it is rebuilt
# on every update and would bloat the history), so GitHub holds only the finished app
# tables. Without this, the season's box scores, play-by-play and rally table live on
# one drive and nowhere else, and the mirror they came from is a hobby server: both
# earlier sources, stats.ncaa.org and volleyball-gis, have already gone dark.
#
# WHAT IT NEVER DOES. It never deletes from the backup. A file that disappears from the
# project (a stale schedule, a cleaned-up cache) stays in the backup. That is the point
# of a backup; the cost is a little disk.
#
# It never fails the caller. A missing drive or a full disk prints a warning and exits
# 0, because losing an update over a backup problem would be the wrong trade.
#
# Usage:
#   scripts/backup_local.sh                 # to ~/cv19-vb-backup
#   CV19_BACKUP_DIR=/some/where scripts/backup_local.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${CV19_BACKUP_DIR:-$HOME/cv19-vb-backup}"

if [ "$(cd "$DEST" 2>/dev/null && pwd)" = "$ROOT" ]; then
  echo "backup: $DEST is the project itself; nothing to do" >&2
  exit 0
fi
if ! mkdir -p "$DEST" 2>/dev/null; then
  echo "backup: WARNING -- cannot create $DEST; nothing was backed up" >&2
  exit 0
fi

printf '\n\033[1m=== local backup -> %s ===\033[0m\n' "$DEST"
# .venv is rebuilt from requirements.txt in a minute; __pycache__ and Finder litter
# are noise. Everything else goes, .git included, so the backup is a working clone.
if rsync -a --exclude '.venv/' --exclude '__pycache__/' --exclude '.DS_Store' \
         "$ROOT/" "$DEST/"; then
  echo "  done: $(du -sh "$DEST" 2>/dev/null | cut -f1) in $DEST"
  date '+%Y-%m-%d %H:%M:%S' > "$DEST/.last_backup"
else
  echo "backup: WARNING -- rsync failed; the backup may be incomplete" >&2
fi
exit 0
