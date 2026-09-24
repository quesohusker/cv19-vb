"""Fetch match results for a season from the ncaa-api mirror, one call per date.

stats.ncaa.org denies every /teams/<id> path, so the old scraper cannot reach
2026 at all. The volleyball-gis repository publishes 2026 player box scores but
carries no results, no set scores and no play-by-play for that season -- its own
pbp coverage stops at contest 6501666, well below the 6583616+ range 2026 uses.

The scoreboard endpoint closes exactly that gap. Each game carries both teams'
sets won and a winner flag, which is everything the `Result` column needs, and
one request covers every match on a date -- roughly 25 requests for a season so
far, against 1,541 if we asked per match.

Results are keyed by (date, unordered team pair) rather than by ID. The two
sources use different ID spaces: a volleyball-gis ContestID is a stats.ncaa.org
contest, an ncaa-api gameID is an ncaa.com game, and they do not overlap at all.
Both do use NCAA short names, so the pair join matched 174 of 175 games on a
test date.

A date is fetched once and then left alone. Beside the results file we keep a
manifest of how many games each date had and how many were final; a date whose
games are all final, and which is old enough that a late correction is unlikely,
is served from the stored rows instead of the network. A date that came back
short -- "51 final of 52" -- stays unsettled and is retried every run until it
fills in. That turns a routine update from ~25 requests into two or three.

Usage:
    python3 data_collection/fetch_ncaa_results.py 2026
    python3 data_collection/fetch_ncaa_results.py 2026 --start 08/21 --end 12/20
    python3 data_collection/fetch_ncaa_results.py 2026 --refetch   # ignore the cache
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = "https://ncaa-api.henrygd.me"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def season_dates(year: int, start: str | None, end: str | None) -> list[date]:
    """Late August through mid-December, clipped to today."""
    first = date(year, 8, 20) if not start else _md(start, year)
    last = date(year, 12, 21) if not end else _md(end, year)
    last = min(last, date.today())
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _md(s: str, year: int) -> date:
    m, d = s.split("/")
    return date(year, int(m), int(d))


def manifest_path(out: Path) -> Path:
    return out.with_suffix(".manifest.json")


def load_cache(out: Path) -> tuple[dict, dict]:
    """Stored rows grouped by date, and what we know about each date's completeness."""
    rows_by_date: dict[str, list[dict]] = {}
    if out.exists():
        try:
            for r in json.loads(out.read_text()):
                rows_by_date.setdefault(r["date"], []).append(r)
        except (json.JSONDecodeError, KeyError, TypeError):
            print("  (results file unreadable; refetching everything)", file=sys.stderr)
    man = {}
    mp = manifest_path(out)
    if mp.exists():
        try:
            man = json.loads(mp.read_text())
        except json.JSONDecodeError:
            print("  (manifest unreadable; refetching everything)", file=sys.stderr)
    return rows_by_date, man


def settled(d: date, man: dict, rows_by_date: dict, grace_days: int,
            stale_days: int = 21) -> bool:
    """True when a date is finished and safe to serve from disk.

    Every scheduled game has to be final, because a date that came back short may
    simply have been read too early. The date has to be older than the grace window,
    because a late final or a corrected score lands after midnight. And we have to
    actually still hold its rows -- a manifest that outlived its results file must
    not talk us out of fetching.

    The one exception is a date that stays short forever. A cancelled or abandoned
    match leaves the scoreboard reading "51 final of 52" for good, and without a cut
    off that date would be re-read on every run for the rest of the season. After
    stale_days we take what is there: anything not final three weeks on never will be.
    """
    e = man.get(f"{d:%Y-%m-%d}")
    if not e:
        return False
    age = (date.today() - d).days
    if age < grace_days:
        return False
    if e.get("games", 0) == 0:
        return True              # a day with no volleyball on it stays that way
    if f"{d:%m/%d/%Y}" not in rows_by_date:
        return False
    return e.get("finals") == e.get("games") or age >= stale_days


def fetch(year: int, start, end, division: str, sport: str, delay: float,
          out: Path, refetch: bool = False, grace_days: int = 2,
          stale_days: int = 21) -> list[dict]:
    rows_by_date, man = ({}, {}) if refetch else load_cache(out)
    rows, empty_run, fetched, reused = [], 0, 0, 0
    for d in season_dates(year, start, end):
        if settled(d, man, rows_by_date, grace_days, stale_days):
            cached = rows_by_date.get(f"{d:%m/%d/%Y}", [])
            rows.extend(cached)
            reused += 1
            e = man[f"{d:%Y-%m-%d}"]
            empty_run = empty_run + 1 if not e.get("games") else 0
            print(f"  {d}  {len(cached):>3} final of {e.get('games', 0):>3}   cached")
            continue
        url = f"{BASE}/scoreboard/{sport}/{division}/{d:%Y/%m/%d}"
        try:
            data = get_json(url)
        except urllib.error.HTTPError as e:
            print(f"  {d} HTTP {e.code}", file=sys.stderr)
            continue
        except Exception as e:                                    # noqa: BLE001
            print(f"  {d} failed: {e}", file=sys.stderr)
            continue

        games = data.get("games", [])
        finals = 0
        for g in games:
            gg = g.get("game", g)
            if gg.get("gameState") != "final":
                continue          # scheduled or in progress; nothing to record yet
            a, h = gg.get("away", {}), gg.get("home", {})
            an = (a.get("names", {}).get("short") or "").strip()
            hn = (h.get("names", {}).get("short") or "").strip()
            if not an or not hn:
                continue
            try:
                asets, hsets = int(a.get("score") or 0), int(h.get("score") or 0)
            except ValueError:
                continue
            rows.append({
                "date": f"{d:%m/%d/%Y}", "game_id": str(gg.get("gameID") or ""),
                "away_team": an, "home_team": hn,
                "away_sets": asets, "home_sets": hsets,
                "winner": an if a.get("winner") else (hn if h.get("winner") else
                                                     (an if asets > hsets else hn)),
            })
            finals += 1
        print(f"  {d}  {finals:>3} final of {len(games):>3}")
        man[f"{d:%Y-%m-%d}"] = {"games": len(games), "finals": finals}
        fetched += 1
        empty_run = empty_run + 1 if not games else 0
        if empty_run >= 14:
            print("  14 empty dates in a row -- stopping early.")
            break
        time.sleep(delay)

    mp = manifest_path(out)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(dict(sorted(man.items())), indent=1))
    print(f"\n  {fetched} date(s) fetched, {reused} served from cache")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--start", help="MM/DD, defaults to 08/20")
    ap.add_argument("--end", help="MM/DD, defaults to 12/21 or today")
    ap.add_argument("--division", default="d1")
    ap.add_argument("--sport", default="volleyball-women")
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the cache and re-read every date")
    ap.add_argument("--grace-days", type=int, default=2,
                    help="always re-read dates this recent (default 2)")
    ap.add_argument("--stale-days", type=int, default=21,
                    help="stop retrying a date short of finals after this "
                         "many days (a cancelled match never fills in)")
    args = ap.parse_args()

    out = args.out or Path(f"data/ncaa_api/results_{args.sport}_{args.division}_{args.year}.json")
    rows = fetch(args.year, args.start, args.end, args.division, args.sport,
                 args.delay, out, args.refetch, args.grace_days,
                 args.stale_days)
    if not rows:
        raise SystemExit("No final results returned. Check the season and the endpoint.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1))
    dates = {r["date"] for r in rows}
    print(f"\nwrote {out}  {len(rows):,} matches across {len(dates)} dates")


if __name__ == "__main__":
    main()
