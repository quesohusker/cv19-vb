#!/usr/bin/env python3
"""Check a scraped season for silently missing teams.

Why this exists: when a per-team page times out, ncaavolleyballr warns and returns
invisible() for that team, and the surrounding chunk still succeeds. So a scrape can
report "ok" the whole way through and still be missing teams. That is not
hypothetical -- it is what happened to the shipped 2025 D1 data, where 34 teams are
absent in conference-shaped blocks (the entire Sun Belt, 9 WCC, 7 WAC), while every
team that IS present has a full schedule. See ncaavolleyballr issue #24.

Run this after a scrape, before feeding anything to the pipeline.

    python scripts/check_coverage.py 2026
    python scripts/check_coverage.py 2026 --compare 2024
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

VENUE = re.compile(r"\s*@.*$")


def clean(name: str) -> str:
    n = name.strip()
    if n.startswith("@"):
        n = n[1:].strip()
    return VENUE.sub("", n).strip()


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("year", type=int)
    ap.add_argument("--compare", type=int, default=None,
                    help="prior season to diff against (default: year-1)")
    ap.add_argument("--division", type=int, default=1)
    ap.add_argument("--sport", default="wvb")
    ap.add_argument("--dir", type=Path, default=Path("data/ncaavolleyballr/data-csv"))
    args = ap.parse_args()
    prior_year = args.compare or (args.year - 1)

    def fname(label: str, yr: int) -> Path:
        return args.dir / f"{args.sport}_{label}_div{args.division}_{yr}.csv"

    print(f"=== {args.sport.upper()} D{args.division} {args.year} coverage ===\n")

    rows = load(fname("teammatch", args.year))
    if not rows:
        print(f"No team-match file at {fname('teammatch', args.year)}")
        return 1

    per_team = Counter(r["Team"] for r in rows)
    counts = sorted(per_team.values())
    median = counts[len(counts) // 2]
    print(f"  rows           {len(rows):,}")
    print(f"  teams          {len(per_team)}")
    print(f"  matches/team   median {median}, min {counts[0]}, max {counts[-1]}")

    thin = {t: n for t, n in per_team.items() if n < median / 2}
    if thin:
        print(f"\n  {len(thin)} teams with under half the median match count "
              "(likely partial, not merely early-season):")
        for t, n in sorted(thin.items(), key=lambda kv: kv[1])[:15]:
            print(f"    {n:>3}  {t}")

    prior = load(fname("teammatch", prior_year))
    if not prior:
        print(f"\n  (no {prior_year} file to diff against)")
        return 0

    prior_teams = {r["Team"] for r in prior}
    conf = {}
    for r in prior:
        conf.setdefault(r["Team"], r.get("Conference", "?"))
    missing = sorted(prior_teams - set(per_team))

    print(f"\n  present in {prior_year}, absent in {args.year}: {len(missing)}")
    wiped = False
    if missing:
        by_conf = Counter(conf.get(t, "?") for t in missing)
        prior_conf = Counter(conf.get(t, "?") for t in prior_teams)
        print("\n  by conference (marked WIPED when the whole conference is gone):")
        for c, n in by_conf.most_common():
            is_wiped = prior_conf.get(c) == n
            wiped = wiped or is_wiped
            flag = "  <-- WIPED" if is_wiped else ""
            print(f"    {c:<22} {n:>3} of {prior_conf.get(c, '?')}{flag}")
        print(f"\n  teams: {', '.join(missing[:20])}"
              f"{' ...' if len(missing) > 20 else ''}")
        print("\n  Conference-shaped gaps mean the scrape died inside those conferences.")
        print("  Re-run the same command -- checkpoints make it resume, and failed")
        print("  chunks are deliberately left uncached so they are retried.")
    else:
        print("  Nothing missing. Safe to run the pipeline.")
    # exit 2 signals a conference-shaped gap, so a driver can stop before
    # rebuilding the app on data that is missing whole conferences
    return 2 if wiped else 0


if __name__ == "__main__":
    raise SystemExit(main())
