"""Fetch per-match play-by-play from the ncaa-api mirror. Resumable.

Driven by the results file that fetch_ncaa_results.py writes, because that is
where the gameIDs come from -- the scoreboard is the only endpoint that
enumerates matches.

One request per match, so a season is thousands of calls rather than the ~25 the
scoreboard needs. Every response is written to its own file and existing files
are skipped, so the run can be interrupted and restarted freely; that matters
more than speed here.

WHAT THIS FEED IS. Point-summary play-by-play: the event that ended each rally,
plus substitutions, and nothing in between. There are no serve, reception, set,
dig or first-ball rows, which the old stats.ncaa.org feed had. Side-out % and
point-score % survive anyway because serve order is reconstructible (see
analytics/rally_from_ncaa_api.py); first-ball side-out does not, which is part of
why it is no longer a graded benchmark.

Usage:
    python3 data_collection/fetch_ncaa_pbp.py 2026
    python3 data_collection/fetch_ncaa_pbp.py 2026 --limit 50   # try a slice first
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ncaa-api.henrygd.me"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def fetch_one(game_id: str, timeout: int, retries: int = 2):
    url = f"{BASE}/game/{game_id}/play-by-play"
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
    out_dir = args.out_dir or Path(f"data/ncaa_api/pbp/{args.year}")
    out_dir.mkdir(parents=True, exist_ok=True)

    games = [r for r in json.loads(results.read_text()) if r.get("game_id")]
    todo = [g for g in games if not (out_dir / f"{g['game_id']}.json").exists()]
    print(f"{len(games):,} matches in results, {len(games) - len(todo):,} already "
          f"fetched, {len(todo):,} to go")
    if args.limit:
        todo = todo[:args.limit]
        print(f"  limited to {len(todo):,} this run")

    ok = failed = 0
    started = time.time()
    for i, g in enumerate(todo, 1):
        data, err = fetch_one(g["game_id"], args.timeout)
        if data is None:
            failed += 1
            print(f"  [{i}/{len(todo)}] {g['game_id']} FAILED ({err})", file=sys.stderr)
        else:
            # carry the date and teams through: the pbp payload has neither
            data["_date"] = g["date"]
            data["_away_team"] = g["away_team"]
            data["_home_team"] = g["home_team"]
            (out_dir / f"{g['game_id']}.json").write_text(json.dumps(data))
            ok += 1
        if i % 25 == 0 or i == len(todo):
            rate = i / max(time.time() - started, 1e-9)
            left = (len(todo) - i) / max(rate, 1e-9)
            print(f"  [{i}/{len(todo)}] ok {ok:,} failed {failed:,}  "
                  f"~{left / 60:.0f} min left", flush=True)
        time.sleep(args.delay)

    have = len(list(out_dir.glob("*.json")))
    print(f"\n{out_dir}: {have:,} matches on disk "
          f"({have / len(games) * 100:.1f}% of the season)")
    if failed:
        print(f"{failed:,} failed this run -- re-run to retry only those.")


if __name__ == "__main__":
    main()
