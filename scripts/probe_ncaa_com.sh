#!/usr/bin/env bash
# Test data sources that are NOT stats.ncaa.org.
#
# stats.ncaa.org now returns "Access Denied" for every data-bearing path:
# /teams/<id>, /teams/<id>/roster, /teams/<id>/season_to_date_stats and
# /contests/livestream_scoreboards. A real browser with its own profile, a
# site-root warm-up and a genuine click-through from the team list page all
# fail identically, so the rule is on the path and there is nothing left to
# tune on that host.
#
# data.ncaa.com is a different host: the JSON feed behind ncaa.com's own
# scoreboards. If it answers, it is a better source than what we were
# scraping -- plain JSON, no browser, and a play-by-play endpoint per game.
#
# This walks the chain: scoreboard for a date -> a game ID -> that game's
# box score and play-by-play. Each step prints its HTTP status, so a partial
# failure is obvious.
#
#   scripts/probe_ncaa_com.sh              # a recent date
#   scripts/probe_ncaa_com.sh 2025/11/15   # a date from last season

set -uo pipefail

DATE="${1:-$(date -v-2d +%Y/%m/%d 2>/dev/null || date -d '2 days ago' +%Y/%m/%d)}"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

get() {  # get <label> <url> <outfile>
  local code
  code=$(curl -sS -o "$3" -w '%{http_code}' -m 30 -A "$UA" "$2" 2>/dev/null || echo 000)
  printf '  %-28s %s  %s\n' "$1" "$code" "$2"
  [ "$code" = "200" ]
}

echo "date: $DATE"
echo
echo "=== 1. scoreboard (data.ncaa.com) ==="
SB="https://data.ncaa.com/casablanca/scoreboard/volleyball-women/d1/${DATE}/scoreboard.json"
if get "scoreboard" "$SB" "$TMP/sb.json"; then
  python3 - "$TMP/sb.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
games = d.get("games", [])
print(f"  games on this date: {len(games)}")
ids = []
for g in games[:5]:
    gg = g.get("game", g)
    gid = gg.get("gameID") or gg.get("id")
    home = gg.get("home", {}).get("names", {}).get("short", "?")
    away = gg.get("away", {}).get("names", {}).get("short", "?")
    print(f"    {gid}  {away} at {home}")
    if gid: ids.append(str(gid))
open("/tmp/_gids.txt", "w").write("\n".join(ids))
PY
else
  echo "  scoreboard unavailable -- try another date, e.g. 2025/11/15"
fi

GID="$(head -1 /tmp/_gids.txt 2>/dev/null || true)"
if [ -n "$GID" ]; then
  echo
  echo "=== 2. per-game endpoints for game $GID ==="
  get "boxscore"    "https://data.ncaa.com/casablanca/game/${GID}/boxscore.json"   "$TMP/box.json" \
    && python3 -c "import json,sys;d=json.load(open('$TMP/box.json'));print('  top-level keys:',list(d)[:10])"
  get "play-by-play" "https://data.ncaa.com/casablanca/game/${GID}/pbp.json"       "$TMP/pbp.json" \
    && python3 -c "
import json
d=json.load(open('$TMP/pbp.json'))
print('  top-level keys:',list(d)[:10])
p=d.get('periods') or d.get('sets') or []
print('  periods/sets:',len(p))
if p:
    plays=p[0].get('playStats') or p[0].get('plays') or []
    print('  plays in first set:',len(plays))
    for x in plays[:4]: print('   ',x)
"
  get "game info"   "https://data.ncaa.com/casablanca/game/${GID}/gameInfo.json"  "$TMP/gi.json"
  get "team stats"  "https://data.ncaa.com/casablanca/game/${GID}/teamStats.json" "$TMP/ts.json"
fi

echo
echo "=== 3. public ncaa-api mirror (same data, different host) ==="
get "ncaa-api scoreboard" \
  "https://ncaa-api.henrygd.me/scoreboard/volleyball-women/d1/${DATE}" "$TMP/api.json" \
  && python3 -c "import json;d=json.load(open('$TMP/api.json'));print('  games:',len(d.get('games',[])))"

echo
echo "Reading the result:"
echo "  scoreboard + pbp both 200  -> a complete replacement source; no browser needed."
echo "  scoreboard only            -> we get schedules and scores, pbp needs another route."
echo "  all 403/000                -> this host is closed too; next stop is the GraphQL API."
