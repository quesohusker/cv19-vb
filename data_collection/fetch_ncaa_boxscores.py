"""Fetch per-match player box scores from the ncaa-api mirror. Resumable.

The companion to fetch_ncaa_pbp.py, and deliberately its twin: same results file
for gameIDs, same one-file-per-match cache, same resume rules. Only the endpoint
differs -- /game/<id>/boxscore instead of /game/<id>/play-by-play.

WHY THIS EXISTS. 2026 player box scores came from the volleyball-gis repository,
which stopped publishing mid-season. This endpoint carries the same NCAA counting
stats, and carries them keyed by the gameID the rest of the 2026 pipeline already
uses. That second part is the real gain: volleyball-gis ContestIDs are
stats.ncaa.org contests and had to be joined to ncaa-api results on (date,
unordered team pair), which drops roughly 6% of team-matches -- mostly same-day
repeat pairings at tournaments. Fetching box scores by gameID makes that join an
identity.

WHAT THE PAYLOAD HAS. Per player: position, jersey, sets played, kills, attack
errors and attempts, assists, set errors and attempts, service aces and errors,
serve attempts, digs, reception attempts and errors, block solos, assists and
errors, points, ball-handling errors, and starter/participated flags. Per team,
the same totals plus a per-set attack split. It does NOT carry conference, which
build_playermatch.py fills from local data.

Two teams' stats live under teamBoxscore[], keyed by teamId; the names sit under
teams[] and the ids there are strings while the ones under teamBoxscore[] are
integers, so anything matching the two must normalise.

Usage:
    python3 data_collection/fetch_ncaa_boxscores.py 2026
    python3 data_collection/fetch_ncaa_boxscores.py 2026 --limit 20   # a slice first
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# NCAA_API_BASE overrides this; see fetch_ncaa_results.py for why you want to.
BASE = os.environ.get("NCAA_API_BASE", "https://ncaa-api.henrygd.me").rstrip("/")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def fetch_one(game_id: str, timeout: int, retries: int = 2):
    url = f"{BASE}/game/{game_id}/boxscore"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < retries:
                time.sleep(3 * (attempt + 1))     # mirror is rate limited; back off
                continue
            return None, f"HTTP {e.code}"
        except Exception as e:                                    # noqa: BLE001
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            return None, str(e)[:60]
    return None, "exhausted retries"


def write_json(path: Path, data) -> tuple[bool, str | None]:
    """Write one cached response, atomically, and never take the run down with it.

    Same two failure modes fetch_ncaa_pbp.py documents, for the same reason -- this
    stage writes the same ~1,700 small files over the same tens of minutes.

    FIRST, the output directory can disappear underneath a long run when the checkout
    sits somewhere macOS syncs to iCloud Drive, so the directory is re-made before every
    write and a write that still fails counts as a failed match rather than killing the
    process.

    SECOND, a write interrupted partway leaves a truncated file, and the resume check
    would skip it forever. Writing to a temporary name and renaming into place makes the
    cached file either whole or absent.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
        return True, None
    except OSError as e:
        return False, f"{type(e).__name__}: {e}"


def has_players(data) -> bool:
    """Did this response actually carry player rows?

    A 200 is not enough. Some contests answer with the envelope and an empty
    teamBoxscore, and one cached like that would be skipped by the resume check for the
    rest of the season and then quietly contribute no players. Those count as empty
    rather than ok, and are left uncached so a later run retries them.
    """
    try:
        return any(t.get("playerStats") for t in (data.get("teamBoxscore") or []))
    except AttributeError:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--results", type=Path)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--sport", default="volleyball-women")
    ap.add_argument("--division", default="d1")
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--limit", type=int, help="stop after this many new fetches")
    args = ap.parse_args()

    results = args.results or Path(
        f"data/ncaa_api/results_{args.sport}_{args.division}_{args.year}.json")
    if not results.exists():
        raise SystemExit(f"No results file at {results}\n"
                         f"Run: python3 data_collection/fetch_ncaa_results.py {args.year}")
    out_dir = args.out_dir or Path(f"data/ncaa_api/boxscore/{args.year}")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolved once, for the reason fetch_ncaa_pbp.py gives: a long run that re-traverses
    # symlinks on every write breaks wholesale if one of them moves halfway through.
    out_dir = out_dir.resolve()
    results = results.resolve()
    print(f"writing to {out_dir}")

    games = [r for r in json.loads(results.read_text()) if r.get("game_id")]

    def cached(gid: str) -> bool:
        f = out_dir / f"{gid}.json"
        # size, not just existence: a file left truncated by an interrupted run must be
        # fetched again rather than silently skipped and failed on much later
        return f.exists() and f.stat().st_size > 2

    for stale in out_dir.glob("*.json.part"):
        stale.unlink(missing_ok=True)
    todo = [g for g in games if not cached(g["game_id"])]
    print(f"{len(games):,} matches in results, {len(games) - len(todo):,} already "
          f"fetched, {len(todo):,} to go")
    if args.limit:
        todo = todo[:args.limit]
        print(f"  limited to {len(todo):,} this run")

    ok = failed = empty = 0
    started = time.time()
    for i, g in enumerate(todo, 1):
        data, err = fetch_one(g["game_id"], args.timeout)
        if data is None:
            failed += 1
            print(f"  [{i}/{len(todo)}] {g['game_id']} FAILED ({err})", file=sys.stderr)
        elif not has_players(data):
            empty += 1
            print(f"  [{i}/{len(todo)}] {g['game_id']} no player rows -- not cached",
                  file=sys.stderr)
        else:
            # carry the date and teams through: the payload names the teams itself, but
            # the results file is what the rest of the pipeline joins on, so its
            # spelling is the one that has to travel with the row
            data["_date"] = g["date"]
            data["_away_team"] = g["away_team"]
            data["_home_team"] = g["home_team"]
            wrote, werr = write_json(out_dir / f"{g['game_id']}.json", data)
            if wrote:
                ok += 1
            else:
                failed += 1
                print(f"  [{i}/{len(todo)}] {g['game_id']} WRITE FAILED ({werr})",
                      file=sys.stderr)
        if i % 25 == 0 or i == len(todo):
            rate = i / max(time.time() - started, 1e-9)
            left = (len(todo) - i) / max(rate, 1e-9)
            print(f"  [{i}/{len(todo)}] ok {ok:,} failed {failed:,} empty {empty:,}  "
                  f"~{left / 60:.0f} min left", flush=True)
        time.sleep(args.delay)

    # counted against the results file we were given, not against everything in the
    # directory: a --results subset would otherwise report more than 100% of "the season"
    have = sum(1 for g in games if cached(g["game_id"]))
    print(f"\n{out_dir}: {have:,} of {len(games):,} matches in {results.name} "
          f"({have / len(games) * 100:.1f}%)")
    if failed:
        print(f"{failed:,} failed this run -- re-run to retry only those.")
    if empty:
        print(f"{empty:,} returned no player rows. Re-running retries them; a contest "
              f"that stays empty has no box score published.")


if __name__ == "__main__":
    main()
