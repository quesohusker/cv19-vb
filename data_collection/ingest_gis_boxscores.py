"""Build a team-match box score file from the volleyball-gis player box scores.

stats.ncaa.org denies every /teams/<id> path, so the R scraper cannot reach 2026.
The volleyball-gis repository (github.com/jpitel24/volleyball-gis) publishes
per-player, per-match NCAA box scores as wvb_playermatch_div1_<year>.csv, which
summed by team reproduces exactly the team box score our pipeline reads.

WHAT THIS DOES AND DOES NOT COVER. Player box scores carry no match result: the
winner cannot be recovered from counting stats, because a team can lose 2-3 while
outscoring its opponent overall. Results therefore come from the ncaa-api
scoreboard (data_collection/fetch_ncaa_results.py) and are joined on (date,
unordered team pair) -- the two sources use different ID spaces, a
volleyball-gis ContestID being a stats.ncaa.org contest and an ncaa-api gameID an
ncaa.com game, with no overlap between them. Both use NCAA short names, so the
pair join matched 174 of 175 games on a test date.

That gets the four box-score benchmarks (hitting efficiency, opponent hitting
efficiency, ace-to-error, hitting margin) plus real win-loss records. Side-out %,
point-score % and won-set-1 need rally- or set-level data, which neither source
provides here; the ncaa-api play-by-play endpoint carries it, one call per match.

PROVENANCE. Only the plain NCAA box-score counts are read -- kills, errors,
attempts, assists, aces, service errors, digs, reception attempts and errors,
blocks. The repository's own derived metrics (GIS, GIS_Plus, the quality JSONs)
are deliberately not used.

Usage:
    python3 data_collection/ingest_gis_boxscores.py 2026 \\
        --gis-dir ../volleyball-gis/public/data \\
        --results data/ncaa_api/results_volleyball-women_d1_2026.json
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

# our column name -> the volleyball-gis column it sums from
SUM_COLS = {
    "Kills": "Kills", "Errors": "Errors", "Total Attacks": "TotalAttacks",
    "Assists": "Assists", "Aces": "Aces", "SErr": "SErr", "Digs": "Digs",
    "RetAtt": "RetAtt", "RErr": "RErr", "Block Solos": "BlockSolos",
    "Block Assists": "BlockAssists", "BErr": "BErr", "PTS": "PTS", "BHE": "BHE",
}
OUT_FIELDS = ["Season", "Date", "TeamID", "Team", "Conference", "Opponent", "Result",
              "S", "Kills", "Errors", "Total Attacks", "Hit Pct", "Assists", "Aces",
              "SErr", "Digs", "RetAtt", "RErr", "Block Solos", "Block Assists",
              "BErr", "PTS", "BHE"]


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def iso_to_us(d: str) -> str:
    """2026-08-28 -> 08/28/2026, the format the rest of the pipeline parses."""
    y, m, day = d.split("-")
    return f"{m}/{day}/{y}"


def load_results(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    out = {}
    for r in json.loads(path.read_text()):
        key = (r["date"], frozenset((r["away_team"].strip(), r["home_team"].strip())))
        out[key] = r
    return out


def aggregate(playermatch: Path) -> dict:
    """One row per team per contest, summed from its players."""
    teams: dict[tuple, dict] = {}
    for r in csv.DictReader(open(playermatch, newline="")):
        key = (r["ContestID"], r["Team"])
        t = teams.get(key)
        if t is None:
            t = teams[key] = {
                "Season": r["Season"], "Date": iso_to_us(r["Date"]),
                "TeamID": "", "Team": r["Team"], "Conference": r.get("Conference", ""),
                "Opponent": r.get("Opponent Team", ""), "Result": "", "S": 0.0,
                **{k: 0.0 for k in SUM_COLS},
            }
        # a player's S is the sets THEY played; the team's is the match length
        t["S"] = max(t["S"], num(r.get("S")))
        for ours, theirs in SUM_COLS.items():
            t[ours] += num(r.get(theirs))
    return teams


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--gis-dir", type=Path, default=Path("../volleyball-gis/public/data"))
    ap.add_argument("--results", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("data/ncaavolleyballr/data-csv"))
    ap.add_argument("--sport", default="wvb")
    ap.add_argument("--division", default="div1")
    args = ap.parse_args()

    src = args.gis_dir / f"{args.sport}_playermatch_{args.division}_{args.year}.csv"
    if not src.exists():
        raise SystemExit(
            f"Not found: {src}\n"
            "Clone the data repository next to this one:\n"
            "  git clone https://github.com/jpitel24/volleyball-gis ../volleyball-gis")

    teams = aggregate(src)
    results = load_results(args.results)

    rows, matched, unmatched = [], 0, []
    for (_contest, team), t in teams.items():
        key = (t["Date"], frozenset((team.strip(), t["Opponent"].strip())))
        res = results.get(key)
        if res:
            ours = res["away_sets"] if res["away_team"].strip() == team.strip() else res["home_sets"]
            theirs = res["home_sets"] if res["away_team"].strip() == team.strip() else res["away_sets"]
            t["Result"] = f"{'W' if res['winner'].strip() == team.strip() else 'L'} {ours}-{theirs}"
            matched += 1
        elif results:
            unmatched.append((t["Date"], team, t["Opponent"]))
        att = t["Total Attacks"]
        t["Hit Pct"] = round((t["Kills"] - t["Errors"]) / att, 3) if att else ""
        rows.append({k: t.get(k, "") for k in OUT_FIELDS})

    rows.sort(key=lambda r: (r["Date"], r["Team"]))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    dest = args.out_dir / f"{args.sport}_teammatch_{args.division}_{args.year}.csv"
    with open(dest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {dest}")
    print(f"  {len(rows):,} team-match rows  ({len(rows) // 2:,} matches, "
          f"{len({r['Team'] for r in rows}):,} teams)")
    print(f"  dates {rows[0]['Date']} .. {rows[-1]['Date']}")
    if results:
        print(f"  results joined: {matched:,} of {len(rows):,} "
              f"({matched / len(rows) * 100:.1f}%)")
        if unmatched:
            print(f"  {len(unmatched)} rows without a result, e.g. {unmatched[:3]}")
    else:
        print("  NO RESULTS FILE -- every Result is blank, and build_match_metrics.py\n"
              "  skips rows whose Result does not start with W or L, so this file will\n"
              "  produce nothing until you run:\n"
              f"    python3 data_collection/fetch_ncaa_results.py {args.year}")


if __name__ == "__main__":
    main()
