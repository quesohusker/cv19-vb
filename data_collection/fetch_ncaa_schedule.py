"""Fetch the rest of the season's schedule from the ncaa-api scoreboard.

The same endpoint fetch_ncaa_results.py reads lists every game on a date, played or
not; that script keeps only the finals. This one keeps the rest: every game from today
forward that is not final yet. The NCAA loads the whole regular season in advance
(checked 2026-10-04: 110 games on 10/10, 99 on 11/14), and the tournament is absent
until the bracket exists.

Every date through --end is read, with no early stop on a run of empty dates. A gap in
the published schedule must not end the walk early and silently drop the weeks after
it; the whole walk is about eighty requests, so there is nothing to save by guessing.

Nothing is cached. A schedule moves -- matches get added, moved, cancelled -- so every
run reads it fresh. Each date gets three attempts, because the mirror throws 502s
under load and one dropped date is a day of games missing from every projection. A
date that fails all three is named in the output. A run that gets
nothing back (no network, the mirror down) leaves the previous file in place and exits
cleanly: a stale schedule is better than none, and this must never stop the pipeline.

Usage:
    python3 data_collection/fetch_ncaa_schedule.py 2026
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

from fetch_ncaa_results import BASE, get_json


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--end", default="12/21", help="MM/DD, last date to read")
    ap.add_argument("--division", default="d1")
    ap.add_argument("--sport", default="volleyball-women")
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = args.out or Path(
        f"data/ncaa_api/schedule_{args.sport}_{args.division}_{args.year}.json")
    m, d_ = (int(x) for x in args.end.split("/"))
    last = date(args.year, m, d_)
    d = max(date.today(), date(args.year, 8, 20))

    rows, empty, failed_dates = [], 0, []
    while d <= last:
        url = f"{BASE}/scoreboard/{args.sport}/{args.division}/{d:%Y/%m/%d}"
        games, err = None, None
        for attempt in range(3):
            try:
                games = get_json(url).get("games", [])
                break
            except Exception as e:                                # noqa: BLE001
                err = e
                time.sleep(2 * (attempt + 1))
        if games is None:
            print(f"  {d} FAILED after 3 attempts: {err}", file=sys.stderr)
            failed_dates.append(f"{d:%m/%d}")
            d += timedelta(days=1)
            continue
        n = 0
        for g in games:
            gg = g.get("game", g)
            if gg.get("gameState") == "final":
                continue          # already played; fetch_ncaa_results.py has it
            a, h = gg.get("away", {}), gg.get("home", {})
            an = (a.get("names", {}).get("short") or "").strip()
            hn = (h.get("names", {}).get("short") or "").strip()
            if not an or not hn:
                continue
            rows.append({"date": f"{d:%m/%d/%Y}", "game_id": str(gg.get("gameID") or ""),
                         "away_team": an, "home_team": hn,
                         "state": gg.get("gameState") or ""})
            n += 1
        print(f"  {d}  {n:>3} to play")
        empty += 0 if games else 1
        d += timedelta(days=1)
        time.sleep(args.delay)

    if not rows:
        print(f"No scheduled games returned ({len(failed_dates)} date(s) failed). "
              f"Leaving {out} as it was.")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1))
    print(f"\n{empty} date(s) with no games, {len(failed_dates)} date(s) failed")
    if failed_dates:
        print(f"  MISSING: {', '.join(failed_dates)} -- re-run; the schedule is read "
              f"fresh every time")
    print(f"wrote {out}  {len(rows):,} games still to play across "
          f"{len({r['date'] for r in rows})} dates")


if __name__ == "__main__":
    main()
