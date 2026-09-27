"""Turn cached ncaa-api box scores into a volleyball-gis-shaped playermatch CSV.

A DROP-IN, ON PURPOSE. Five things read wvb_playermatch_div1_<year>.csv --
ingest_gis_boxscores.py, rally_from_ncaa_api.py (--serve-attempts),
in_system_kills.py, build_player_ratings.py, and setscores_check.py. Rather than
teach all five a second format, this writes the same columns under the same
filename, so every one of them works unchanged and only the directory they are
pointed at moves.

Matching that format exactly matters more than it looks. Four of its quirks are
load-bearing, and each is a silent failure if you get it wrong:

  P, not Position       build_player_ratings.POSITION_GROUPS keys off "P", and a row
                        whose label it cannot place is skipped, not flagged.
  "Opponent Team"       with the space. rally_from_ncaa_api joins on it.
  Season "2026-2027"    for year 2026 -- the academic year, <year>-<year+1>, not
                        "2026" and not <year-1>-<year>. in_system_kills.setter_names
                        records that keying on a bare "2025" matched nothing and every
                        kill came back out of system, and build_match_metrics carries
                        this column straight through from the teammatch CSV. Verified
                        against the volleyball-gis 2026 file, which reads "2026-2027".
  S is the PLAYER's     sets she played, not the match length. ingest_gis_boxscores
                        takes the max across a team's players to get match length,
                        which only works if the per-player value is hers.

CONFERENCE. The box score payload has no conference, and the scoreboard's is not
usable -- conferenceName comes back empty and the slug beside it looks like a
primary-conference field rather than a sport-specific one (it files Hawaii under
mountain-west). Affiliation is constant within a season, so it is looked up from
local data instead: an explicit --conference-map first, then the teammatch CSV this
pipeline already wrote, then any volleyball-gis playermatch file. Teams still
unmapped are reported by name, because build_match_metrics.py indexes
r["Conference"] directly and a missing column would fail there instead of here.

IDS. ContestID is the ncaa-api gameID -- the same id the play-by-play is cached
under, which is the whole point of moving off volleyball-gis. Date, Team and
Opponent Team are taken from the results file the fetcher stapled onto each payload
rather than from the payload's own nameShort, so every stage joins on one spelling.

"points" MEANS TWO DIFFERENT THINGS in this payload, and only one of them is PTS.
Under playerStats it is that player's scoring credit, kills + aces + block solos +
half her block assists. Under teamStats it is the rally points the team scored in
the match -- the set scores added up. Hawaii vs Utah Tech: the players sum to 53 and
teamStats says 76, which is 25 + 25 + 26 off the linescore. PTS here is the player
figure, because that is what volleyball-gis carried and what ingest_gis_boxscores
sums. So a reconciliation against teamStats will agree on all sixteen other columns
and disagree on this one; that is correct, not a mapping error. Nothing downstream
reads PTS today -- it is carried through to the teammatch CSV and no metric uses it.

Usage:
    python3 data_collection/build_playermatch.py 2026
    python3 data_collection/build_playermatch.py 2026 --import-historical
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

# our output column -> the ncaa-api playerStats field it comes from
STAT_COLS = {
    "Kills": "kills", "Errors": "attackErrors", "TotalAttacks": "attackAttempts",
    "Assists": "assists", "SetAtt": "setAttempts", "SetErr": "setErrors",
    "Aces": "serviceAces", "SErr": "serviceErrors", "ServeAtt": "serveAttempts",
    "Digs": "digs", "RetAtt": "receptionAttempts", "RErr": "receptionErrors",
    "BlockSolos": "blockSolos", "BlockAssists": "blockAssists",
    "BErr": "blockingErrors", "PTS": "points", "BHE": "ballHandlingErrors",
}
OUT_FIELDS = (["ContestID", "Season", "Date", "Team", "Conference", "Opponent Team",
               "Location", "Player", "P", "S"] + list(STAT_COLS))


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def us_to_iso(d: str) -> str:
    """08/28/2026 -> 2026-08-28, the format volleyball-gis used and the readers expect."""
    m, day, y = d.split("/")
    return f"{y}-{m}-{day}"


def conference_map(year: int, explicit: Path | None, teammatch_dir: Path,
                   gis_dir: Path | None) -> dict[str, str]:
    """team -> conference, from whichever local source answers first.

    Tried in order of how much we trust it: a map handed to us, then the teammatch CSV
    this pipeline wrote on an earlier run, then volleyball-gis. Later years first within
    each source, since a team that changed conference should read as its most recent.
    """
    def from_csv(path: Path, team_col: str = "Team") -> dict[str, str]:
        if not path.exists():
            return {}
        out = {}
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                team = (r.get(team_col) or "").strip()
                conf = (r.get("Conference") or "").strip()
                if team and conf:
                    out.setdefault(team, conf)
        return out

    out: dict[str, str] = {}
    if explicit:
        out.update(from_csv(explicit))
        print(f"  conference: {len(out):,} teams from {explicit}")
    for y in range(year, year - 6, -1):
        if len(out) > 300:
            break
        cands = [teammatch_dir / f"wvb_teammatch_div1_{y}.csv"]
        if gis_dir:
            cands.append(gis_dir / f"wvb_playermatch_div1_{y}.csv")
        for cand in cands:
            found = from_csv(cand)
            if found:
                before = len(out)
                for k, v in found.items():
                    out.setdefault(k, v)
                print(f"  conference: +{len(out) - before:,} teams from {cand.name}")
    return out


def player_rows(path: Path, season: str, conf: dict[str, str]) -> list[dict]:
    """Every participating player in one cached box score, both teams."""
    d = json.loads(path.read_text())
    date, away, home = d.get("_date"), d.get("_away_team"), d.get("_home_team")
    if not (date and away and home):
        raise ValueError("payload missing the _date/_away_team/_home_team the fetcher adds")

    # teams[] carries the names with string ids; teamBoxscore[] carries the stats with
    # integer ids. Normalise to str or nothing matches.
    is_home = {str(t.get("teamId")): bool(t.get("isHome")) for t in (d.get("teams") or [])}

    rows = []
    for tb in (d.get("teamBoxscore") or []):
        tid = str(tb.get("teamId"))
        if tid not in is_home:
            raise ValueError(f"teamBoxscore id {tid} is not in teams[]")
        team, opp = (home, away) if is_home[tid] else (away, home)
        for p in (tb.get("playerStats") or []):
            if not p.get("participated"):
                continue          # a listed non-participant is all zeroes; it would only
                                  # dilute the per-position pools in build_player_ratings
            name = " ".join(f"{p.get('firstName') or ''} {p.get('lastName') or ''}".split())
            if not name:
                continue
            rows.append({
                "ContestID": path.stem, "Season": season, "Date": us_to_iso(date),
                "Team": team, "Conference": conf.get(team, ""), "Opponent Team": opp,
                "Location": "Home" if is_home[tid] else "Away",
                "Player": name, "P": (p.get("position") or "").strip(),
                "S": num(p.get("gamesPlayed")),
                **{ours: num(p.get(theirs)) for ours, theirs in STAT_COLS.items()},
            })
    return rows


def import_historical(gis_dir: Path, out_dir: Path, skip_year: int) -> None:
    """Copy the seasons only volleyball-gis has, so one directory holds them all.

    build_player_ratings takes a single --gis-dir and its REFERENCE_SEASONS are
    2022-2025, so the fixed thresholds need those files sitting beside the generated
    one. Copied rather than symlinked: after this the pipeline does not need the clone
    to exist at all, which is the point, given it is what went stale.
    """
    for src in sorted(gis_dir.glob("wvb_playermatch_div1_*.csv")):
        year = src.stem.rsplit("_", 1)[-1]
        if year == str(skip_year):
            continue
        dest = out_dir / src.name
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            continue
        shutil.copy2(src, dest)
        print(f"  imported {src.name} ({src.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--boxscore-dir", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("data/playermatch"))
    ap.add_argument("--teammatch-dir", type=Path,
                    default=Path("data/ncaavolleyballr/data-csv"))
    ap.add_argument("--gis-dir", type=Path, default=Path("../volleyball-gis/public/data"))
    ap.add_argument("--conference-map", type=Path, help="CSV with Team,Conference")
    ap.add_argument("--import-historical", action="store_true",
                    help="also copy the volleyball-gis seasons into --out-dir")
    args = ap.parse_args()

    box_dir = args.boxscore_dir or Path(f"data/ncaa_api/boxscore/{args.year}")
    files = sorted(box_dir.glob("*.json"))
    if not files:
        raise SystemExit(
            f"No box scores in {box_dir}\n"
            f"Run: python3 data_collection/fetch_ncaa_boxscores.py {args.year}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    gis = args.gis_dir if args.gis_dir and args.gis_dir.exists() else None
    conf = conference_map(args.year, args.conference_map, args.teammatch_dir, gis)
    season = f"{args.year}-{args.year + 1}"      # academic year, as volleyball-gis wrote it

    rows, failures = [], []
    for f in files:
        try:
            rows.extend(player_rows(f, season, conf))
        except Exception as e:                                    # noqa: BLE001
            failures.append((f.name, str(e)[:70]))

    if not rows:
        raise SystemExit(f"{len(files):,} files read, no player rows produced.")
    rows.sort(key=lambda r: (r["Date"], r["Team"], r["Player"]))

    dest = args.out_dir / f"wvb_playermatch_div1_{args.year}.csv"
    tmp = dest.with_suffix(".csv.part")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(dest)

    teams = {r["Team"] for r in rows}
    unmapped = sorted(t for t in teams if not conf.get(t))
    print(f"\nwrote {dest}")
    print(f"  {len(rows):,} player-match rows from {len(files):,} matches, "
          f"{len(teams):,} teams")
    print(f"  dates {rows[0]['Date']} .. {rows[-1]['Date']}")
    if failures:
        print(f"  {len(failures)} files unreadable, e.g. {failures[:3]}")
    if unmapped:
        print(f"  NO CONFERENCE for {len(unmapped)} teams: {unmapped[:8]}\n"
              f"  build_match_metrics.py reads Conference directly, so fix these with\n"
              f"  --conference-map before relying on any conference view.")

    if args.import_historical:
        if not gis:
            print(f"\n  --import-historical: no {args.gis_dir}, nothing to copy")
        else:
            print(f"\nimporting other seasons from {gis}")
            import_historical(gis, args.out_dir, args.year)
            have = sorted(p.stem.rsplit("_", 1)[-1]
                          for p in args.out_dir.glob("wvb_playermatch_div1_*.csv"))
            print(f"  {args.out_dir} now holds: {', '.join(have)}")


if __name__ == "__main__":
    main()
