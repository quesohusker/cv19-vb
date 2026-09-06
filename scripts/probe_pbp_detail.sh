#!/usr/bin/env bash
# Does play-by-play detail vary between games?
#
# The one game sampled so far (Utah Tech at Hawaii) carries only rally-ENDING
# events: kills, attack errors, service errors, aces and bad sets, plus subs.
# No serve, reception, set, dig or "first ball kill" rows. That is enough for
# side-out % and point-score % -- reconstructed serve counts matched the box
# score exactly, 74/74 and 54/54 -- but first-ball side-out has no source in it.
#
# Before treating FBSO as lost for 2026, this checks whether the detail level
# is a property of the feed or of the venue. Scoring is entered courtside, and
# different arenas run different stat software, so a Big Ten match may well
# carry touch-level events that a mid-major one does not.
#
# For each game it reports the distinct event phrasings and whether serve,
# reception, dig or first-ball rows appear at all.
#
#   scripts/probe_pbp_detail.sh              # a recent date
#   scripts/probe_pbp_detail.sh 2026/09/05 8 # date, number of games to sample

set -uo pipefail
DATE="${1:-$(date -v-2d +%Y/%m/%d 2>/dev/null || date -d '2 days ago' +%Y/%m/%d)}"
N="${2:-8}"
BASE="https://ncaa-api.henrygd.me"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

curl -sS -m 30 "${BASE}/scoreboard/volleyball-women/d1/${DATE}" -o "$TMP/sb.json" || exit 1

python3 - "$TMP/sb.json" "$N" <<'PY' > "$TMP/games.txt"
import json, sys
d = json.load(open(sys.argv[1])); n = int(sys.argv[2])
out = []
for g in d.get("games", []):
    gg = g.get("game", g)
    if gg.get("gameState") != "final": continue
    a = gg.get("away", {}).get("names", {}).get("short", "?")
    h = gg.get("home", {}).get("names", {}).get("short", "?")
    out.append(f"{gg.get('gameID')}\t{a} at {h}")
    if len(out) >= n: break
print("\n".join(out))
PY

echo "date: $DATE   sampling $(wc -l < "$TMP/games.txt" | tr -d ' ') completed games"
echo
while IFS=$'\t' read -r gid label; do
  [ -z "$gid" ] && continue
  curl -sS -m 30 "${BASE}/game/${gid}/play-by-play" -o "$TMP/p.json" 2>/dev/null
  python3 - "$TMP/p.json" "$label" <<'PY'
import json, re, sys, collections
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print(f"  {sys.argv[2]:<34} unreadable"); raise SystemExit
texts = [pl.get("playText","")
         for p in d.get("periods", [])
         for ev in (p.get("playbyplayStats") or [])
         for pl in (ev.get("plays") or [])]
def kind(t):
    t = re.sub(r'\(.*?\)', '', re.sub(r'\s+',' ',t.strip()))
    t = re.sub(r'\b[A-Z][a-zA-Z.\'-]+ [A-Z][a-zA-Z.\'-]+\b','NAME',t)
    return re.sub(r'\d+','N',t)[:40]
c = collections.Counter(kind(t) for t in texts)
has = lambda w: any(w.lower() in t.lower() for t in texts)
flags = "".join(x if has(x) else "-" for x in ["Serve","Reception","Dig","First ball"])
print(f"  {sys.argv[2]:<34} rows:{len(texts):<5} phrasings:{len(c):<3} "
      f"serve:{'Y' if has('serve by') else 'n'} recep:{'Y' if has('reception') else 'n'} "
      f"dig:{'Y' if has('dig by') else 'n'} firstball:{'Y' if has('first ball') else 'n'}")
PY
  sleep 1
done < "$TMP/games.txt"

echo
echo "All 'n' in the serve/recep/dig/firstball columns means the feed is"
echo "point-summary everywhere, and first-ball side-out has no 2026 source."
