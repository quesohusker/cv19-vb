"""Biggest leads a team held in sets it went on to lose, from the play-by-play.

For every set the team lost, the largest lead it held at any point and the score when
it held it. A set whose play-by-play does not end on a legal final score is marked
unreadable rather than trusted; the 2026 feed garbles some sets. The count of sets
lost is checked against the official box scores, so a set missing from the feed is
reported, not silently skipped.

Usage:
    python3 analytics/blown_leads.py Nebraska 2025 2026
"""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def lost_sets(team: str, season: str) -> pd.DataFrame | None:
    path = ROOT / "data" / "rallies" / f"wvb_rallies_div1_{season}.parquet"
    if not path.exists():
        return None
    d = duckdb.sql(f"""
        WITH s AS (
            SELECT date, away_team, home_team, set_no, rally_no,
                   score_away + CASE WHEN winner = away_team THEN 1 ELSE 0 END AS a,
                   score_home + CASE WHEN winner = home_team THEN 1 ELSE 0 END AS h
            FROM read_parquet('{path}')
            WHERE (away_team = $team OR home_team = $team)
              AND score_away IS NOT NULL AND score_home IS NOT NULL),
        v AS (
            SELECT date, set_no, rally_no,
                   CASE WHEN away_team = $team THEN home_team ELSE away_team END AS opponent,
                   CASE WHEN away_team = $team THEN a ELSE h END AS us,
                   CASE WHEN away_team = $team THEN h ELSE a END AS them
            FROM s)
        SELECT date, opponent, set_no,
               arg_max(us, rally_no) AS us_final, arg_max(them, rally_no) AS them_final,
               max(us - them) AS max_lead,
               list(us - them ORDER BY rally_no) AS margins,
               list(us || '-' || them ORDER BY rally_no) AS scores
        FROM v GROUP BY ALL
    """, params={"team": team}).df()
    d["season"] = season
    cap = d.set_no.astype(int).map(lambda n: 15 if n == 5 else 25)
    hi = d[["us_final", "them_final"]].max(axis=1)
    gap = (d.us_final - d.them_final).abs()
    d["readable"] = (hi >= cap) & (gap >= 2) & ((hi == cap) | (gap == 2))
    # the first time the lead peaked, as a score
    d["lead_at"] = [s[list(m).index(max(m))] for m, s in zip(d.margins, d.scores)]
    return d[d.them_final > d.us_final].drop(columns=["margins", "scores"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("team")
    ap.add_argument("seasons", nargs="+")
    args = ap.parse_args()
    box = pd.read_parquet(ROOT / "app_data" / "matches.parquet")
    frames = []
    for season in args.seasons:
        d = lost_sets(args.team, season)
        if d is None:
            print(f"{season}: no rally table on this machine "
                  f"(data/rallies/wvb_rallies_div1_{season}.parquet)")
            continue
        b = box[(box.season == season) & (box.team == args.team)]
        through = b.match_date.max()
        pbp = int((pd.to_datetime(d.date, format="%m/%d/%Y") <= through).sum())
        print(f"{season}: through {through:%b %-d}, {pbp} lost sets in the play-by-play and "
              f"{int(b.sets_against.sum())} in the box scores"
              f"{'' if pbp == b.sets_against.sum() else ' -- MISMATCH, some sets are missing'}; "
              f"{len(d)} in all, {int((~d.readable).sum())} unreadable")
        frames.append(d)
    if not frames:
        return
    d = pd.concat(frames).sort_values(["max_lead", "date"], ascending=[False, True])
    d["final"] = d.us_final.astype(str) + "-" + d.them_final.astype(str)
    cols = ["season", "date", "opponent", "set_no", "max_lead", "lead_at", "final", "readable"]
    print(f"\nSets {args.team} lost, biggest lead first:")
    print(d[cols].to_string(index=False))


if __name__ == "__main__":
    main()
