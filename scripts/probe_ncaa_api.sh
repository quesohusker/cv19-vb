#!/usr/bin/env bash
# Map the ncaa-api endpoints, and save sample JSON so a parser can be written
# against the real shape rather than a guessed one.
#
# data.ncaa.com answered 404 but the ncaa-api mirror returned 175 games for
# 2026/09/04 over plain curl -- no browser, no chromote, no Akamai. That is the
# way back in now that every stats.ncaa.org data path is denied.
#
# What matters next is whether it carries play-by-play. The rally engine, and
# therefore side-out %, FBSO and everything else in the Volleyball 7, is built
# entirely from pbp. Box scores alone would give us records and hitting lines
# but none of the rally-level metrics.
#
# Samples land in samples/ncaa_api/ (small, and outside the gitignored /data/)
# so they can be committed and read.
#
#   scripts/probe_ncaa_api.sh              # a recent date
#   scripts/probe_ncaa_api.sh 2025/11/15   # last season, for back-year coverage

set -uo pipefail

DATE="${1:-$(date -v-2d +%Y/%m/%d 2>/dev/null || date -d '2 days ago' +%Y/%m/%d)}"
BASE="https://ncaa-api.henrygd.me"
OUT="samples/ncaa_api"
mkdir -p "$OUT"

get() {  # get <label> <path> <outfile>
  local code
  code=$(curl -sS -o "$3" -w '%{http_code}' -m 30 "${BASE}$2" 2>/dev/null || echo 000)
  printf '  %-26s %s  %s\n' "$1" "$code" "$2"
  [ "$code" = "200" ]
}

echo "date: $DATE     base: $BASE"
echo
echo "=== scoreboard ==="
get "scoreboard" "/scoreboard/volleyball-women/d1/${DATE}" "$OUT/scoreboard.json" || exit 1

python3 - "$OUT/scoreboard.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("  top-level keys:", list(d))
games = d.get("games", [])
print("  games:", len(games))
if games:
    g = games[0].get("game", games[0])
    print("  game keys:", list(g))
    gid = g.get("gameID") or g.get("id")
    print("  first gameID:", gid)
    print("  matchup:", g.get("away", {}).get("names", {}).get("short", "?"),
          "at", g.get("home", {}).get("names", {}).get("short", "?"))
    print("  finalMessage:", g.get("finalMessage"), "| state:", g.get("gameState"))
    open("/tmp/_gid.txt", "w").write(str(gid or ""))
PY

GID="$(cat /tmp/_gid.txt 2>/dev/null || true)"
[ -z "$GID" ] && { echo "no game ID found"; exit 1; }

echo
echo "=== per-game endpoints for game $GID ==="
get "boxscore"         "/game/${GID}/boxscore"         "$OUT/boxscore.json"
get "play-by-play"     "/game/${GID}/play-by-play"     "$OUT/pbp.json"
get "team-stats"       "/game/${GID}/team-stats"       "$OUT/team-stats.json"
get "scoring-summary"  "/game/${GID}/scoring-summary"  "$OUT/scoring-summary.json"
get "game info"        "/game/${GID}"                  "$OUT/game.json"

echo
echo "=== play-by-play shape (this is what the rally engine needs) ==="
python3 - "$OUT/pbp.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("  not JSON:", e); raise SystemExit
print("  top-level keys:", list(d))
periods = d.get("periods") or d.get("sets") or []
print("  periods/sets:", len(periods))
if periods:
    p0 = periods[0]
    print("  period keys:", list(p0))
    plays = p0.get("playStats") or p0.get("plays") or []
    print("  plays in set 1:", len(plays))
    for x in plays[:6]:
        print("   ", json.dumps(x)[:220])
    total = sum(len(p.get("playStats") or p.get("plays") or []) for p in periods)
    print("  plays in match:", total)
PY

echo
echo "=== back-year coverage: does the same date shape work for old seasons? ==="
for y in 2024 2022 2020; do
  c=$(curl -sS -o /dev/null -w '%{http_code}' -m 25 \
      "${BASE}/scoreboard/volleyball-women/d1/${y}/11/15" 2>/dev/null || echo 000)
  n=$(curl -sS -m 25 "${BASE}/scoreboard/volleyball-women/d1/${y}/11/15" 2>/dev/null \
      | python3 -c "import json,sys;print(len(json.load(sys.stdin).get('games',[])))" 2>/dev/null || echo "-")
  printf '  %s/11/15  %s  games:%s\n' "$y" "$c" "$n"
done

echo
echo "Samples written to $OUT/ -- commit and push them:"
echo "  git add samples/ncaa_api && git commit -m 'Add ncaa-api samples' && git push"
