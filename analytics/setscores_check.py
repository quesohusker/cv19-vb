"""Cross-check won-set-1 against the set scores volleyball-gis publishes.

WHY THIS IS A CHECK AND NOT A SOURCE. The idea was to take `won_set1` from
wvb_setscores_<year>.json and stop needing the ncaa-api play-by-play for it -- that
stage is thousands of requests and is blocked outright on some networks. It does not
work, for two separate reasons, and both are recorded here so the idea is not retried
from scratch.

ORIENTATION. The file is `{contest_id: [[home, away], ...]}` -- confirmed from the
generator in the volleyball-gis repo, not inferred. Using it therefore needs to know
which team was home, and for 2026 nothing does: the Location column reads "Neutral"
on all 44,260 rows, where 2025 carries a proper Home/Away split. match_pbp_coverage.json
does carry homeTeam, but on a different contest-id space with zero overlap. Two
fallbacks were measured and both are too weak to grade on: CSV row order puts the home
team first 98.5% of the time, and reconstructing each side's points from the box score
(kills + aces + opponent errors, NOT counting blocks, which are already charged as the
opponent's attack errors) resolves only 91.5% by a clear margin. Combined they credit
the wrong team with set 1 about 5% of the time, and a silent flip is worse than no
answer.

AGREEMENT, WHERE ORIENTATION IS KNOWN. On 2025, where Location is populated, all 5,097
contests orient and the answer matches the rally-derived table on 97.7% of team-matches.
The remaining 2.3% are not set-1 disputes: 54% of them also disagree about how many sets
the match went, so the two feeds disagree about the match itself. That is worth knowing
and is what this script reports.

So: run it to find matches where the two sources contradict each other. If
volleyball-gis ever populates Location for the current season, this becomes a cheap
second opinion on every set-1 flag, and the remaining question -- which feed is right
when they differ -- gets decided against a third source rather than assumed.

Usage:
    python3 analytics/setscores_check.py 2025
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


def contest_index(playermatch: Path) -> tuple[dict, dict, dict]:
    """contest -> date, the two teams, and the home team when one is recorded."""
    date: dict[str, str] = {}
    teams: dict[str, list[str]] = defaultdict(list)
    home: dict[str, str] = {}
    with open(playermatch, newline="") as f:
        for r in csv.DictReader(f):
            c, t = r["ContestID"], r["Team"]
            date[c] = r["Date"]
            if t not in teams[c]:
                teams[c].append(t)
            if (r.get("Location") or "").strip() == "Home":
                home[c] = t
    return date, teams, home


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--gis-dir", type=Path, default=Path("../volleyball-gis/public/data"))
    ap.add_argument("--matches", type=Path, default=Path("app_data/matches.parquet"))
    ap.add_argument("--out", type=Path, help="write the disagreements to this CSV")
    args = ap.parse_args()

    scores_path = args.gis_dir / f"wvb_setscores_{args.year}.json"
    if not scores_path.exists():
        raise SystemExit(f"No {scores_path}")
    scores = json.loads(scores_path.read_text())
    date, teams, home = contest_index(
        args.gis_dir / f"wvb_playermatch_div1_{args.year}.csv")

    if not home:
        raise SystemExit(
            f"{args.year}: no contest records a home team -- the Location column is "
            f"'Neutral' throughout, so [home, away] cannot be oriented. Nothing to check "
            f"until volleyball-gis populates it.")

    m = pd.read_parquet(args.matches)
    m = m[(m.season == str(args.year)) & m.won_set1.notna()]
    truth = {(str(r.match_date)[:10], r.team): int(r.won_set1) for r in m.itertuples()}
    nsets = {(str(r.match_date)[:10], r.team): int(r.sets_for) + int(r.sets_against)
             for r in m.itertuples()}

    agree = 0
    rows = []
    for c, sets in scores.items():
        h, ts = home.get(c), teams.get(c)
        if not h or not ts or len(ts) != 2:
            continue
        away = [t for t in ts if t != h]
        if len(away) != 1 or not sets or sets[0][0] == sets[0][1]:
            continue
        away = away[0]
        d = date[c]
        if (d, h) not in truth:
            continue
        won_home = int(sets[0][0] > sets[0][1])
        if truth[(d, h)] == won_home:
            agree += 1
            continue
        rows.append({"contest": c, "date": d, "home": h, "away": away,
                     "set_scores": ";".join(f"{a}-{b}" for a, b in sets),
                     "sets_in_scorefile": len(sets),
                     "sets_in_match_table": nsets.get((d, h)),
                     "set1_per_scorefile": h if won_home else away,
                     "set1_per_rally_table": h if truth[(d, h)] else away})
    out = pd.DataFrame(rows)
    total = agree + len(out)
    print(f"{args.year}: {total:,} contests comparable")
    print(f"  agree on who won set 1: {agree:,} ({agree / max(total, 1):.2%})")
    print(f"  disagree:               {len(out):,}")
    if len(out):
        mism = (out.sets_in_scorefile != out.sets_in_match_table).mean()
        print(f"  of those, the two feeds also disagree on the number of sets played: "
              f"{mism:.0%} -- they are describing different matches, not different set 1s")
    if args.out is not None and len(out):
        out.to_csv(args.out, index=False)
        print(f"  wrote {args.out}")


if __name__ == "__main__":
    main()
