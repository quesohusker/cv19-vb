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

MATCHES THE FEED NEVER SERVES. Some matches answer HTTP 502 run after run, and each
costs three attempts with back-off. Once a match more than GRACE_DAYS old answers
502, its ID goes in pbp/failed_<year>.json and is never asked for again;
--retry-failed asks once more and takes any that come back off the list. A match
inside the grace period is retried normally, because the feed is often just late
posting it.

--recent-days N fetches only matches from the last N days, which is all a routine
update needs.

Usage:
    python3 data_collection/fetch_ncaa_pbp.py 2026
    python3 data_collection/fetch_ncaa_pbp.py 2026 --recent-days 7
    python3 data_collection/fetch_ncaa_pbp.py 2026 --retry-failed
    python3 data_collection/fetch_ncaa_pbp.py 2026 --limit 50   # try a slice first
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

GRACE_DAYS = 3           # a 502 younger than this is the feed running late, not absent
GIVE_UP_ON = {"HTTP 502"}

# NCAA_API_BASE overrides this; see fetch_ncaa_results.py for why you want to.
BASE = os.environ.get("NCAA_API_BASE", "https://ncaa-api.henrygd.me").rstrip("/")
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


def write_json(path: Path, data) -> tuple[bool, str | None]:
    """Write one cached response, atomically, and never take the run down with it.

    Two failure modes seen in the wild, both on a checkout under ~/Documents, which
    macOS syncs to iCloud Drive by default:

    FIRST, the output directory can disappear underneath a long run. iCloud relocates
    and evicts folders while it syncs, and a run that writes ~1,700 small files over
    forty minutes is exactly the shape that provokes it. The directory was created once
    at startup and 920 files landed before the 921st raised FileNotFoundError and killed
    the process. So the directory is now re-made before every write -- an idempotent
    mkdir costs nothing next to an HTTP request -- and a write that still fails counts
    as a failed match and the loop carries on.

    SECOND, a write interrupted partway leaves a truncated file. The resume check only
    asks whether a file exists, so a half-written one would be skipped forever and then
    fail to parse in the rally builder, a long way from here. Writing to a temporary
    name and renaming into place makes the cached file either whole or absent.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
        return True, None
    except OSError as e:
        return False, f"{type(e).__name__}: {e}"


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
    ap.add_argument("--recent-days", type=int,
                    help="only fetch matches played in the last N days")
    ap.add_argument("--retry-failed", action="store_true",
                    help="ask again for matches on the never-served list")
    args = ap.parse_args()

    results = args.results or Path(
        f"data/ncaa_api/results_{args.sport}_{args.division}_{args.year}.json")
    if not results.exists():
        raise SystemExit(f"No results file at {results}\n"
                         f"Run: python3 data_collection/fetch_ncaa_results.py {args.year}")
    out_dir = args.out_dir or Path(f"data/ncaa_api/pbp/{args.year}")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolve once, to a path with no symlinks left in it. This stage runs for forty
    # minutes and writes ~1,700 files; every one of those writes would otherwise
    # re-traverse whatever links sit above it, so a link that is moved or replaced
    # halfway through -- a home directory symlinked for convenience, say -- turns every
    # remaining write into a failure against a path that no longer means what it did at
    # startup. Resolving up front pins the run to the real directory it began writing to.
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

    played = lambda g: datetime.strptime(g["date"], "%m/%d/%Y").date()  # noqa: E731
    ledger_path = out_dir.parent / f"failed_{args.year}.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    if ledger and not args.retry_failed:
        before = len(todo)
        todo = [g for g in todo if g["game_id"] not in ledger]
        print(f"  {before - len(todo):,} skipped: the feed never served them "
              f"(listed in {ledger_path.name}; --retry-failed to try again)")
    if args.recent_days is not None:
        since = date.today() - timedelta(days=args.recent_days)
        # --retry-failed reaches the listed matches however old they are
        recent = [g for g in todo if played(g) >= since
                  or (args.retry_failed and g["game_id"] in ledger)]
        print(f"  recent only: {len(recent):,} since {since:%b %-d}"
              f"{' or on the never-served list' if args.retry_failed else ''}; "
              f"{len(todo) - len(recent):,} older ones left for a full run")
        todo = recent
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
            if err in GIVE_UP_ON and played(g) < date.today() - timedelta(days=GRACE_DAYS):
                ledger[g["game_id"]] = {"date": g["date"], "away": g["away_team"],
                                        "home": g["home_team"], "error": err,
                                        "listed": f"{date.today():%Y-%m-%d}"}
                write_json(ledger_path, ledger)
        else:
            if ledger.pop(g["game_id"], None) is not None:
                write_json(ledger_path, ledger)
            # carry the date and teams through: the pbp payload has neither
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
            print(f"  [{i}/{len(todo)}] ok {ok:,} failed {failed:,}  "
                  f"~{left / 60:.0f} min left", flush=True)
        time.sleep(args.delay)

    have = len(list(out_dir.glob("*.json")))
    print(f"\n{out_dir}: {have:,} matches on disk "
          f"({have / len(games) * 100:.1f}% of the season)")
    if failed:
        print(f"{failed:,} failed this run -- re-run to retry only those.")
    if ledger:
        print(f"{len(ledger):,} on the never-served list ({ledger_path.name}).")


if __name__ == "__main__":
    main()
