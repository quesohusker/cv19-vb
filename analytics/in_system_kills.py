"""Per player, the share of her kills that came in system.

IN SYSTEM means the team's designated setter delivered the ball. When the pass or dig
is bad she cannot reach it, and a libero, DS or outside puts up the second touch
instead -- that is the out-of-system state, and it is worth a great deal. Across 1.3
million 2024 attacks:

    in system       36.3% kill rate    .211 efficiency
    out of system   30.2% kill rate    .157 efficiency

BLOCKS ARE NOT IN THIS. A kill is a terminated attack. A stuff block is a separate
stat and belongs to the blocker, not to whoever set the ball.

WHY THE SHARE OF KILLS AND NOT OF ATTACKS. The attack-level version needs to know who
set every swing, including the ones that ended in an error, and that requires
touch-level play-by-play. The current feed does not carry it: there are no pass, set
or dig rows, only the event that ended each rally. But a kill's ending event names
both players -- "Kill by Tali Hakas (from Adrianna Arquette)" -- on 97% of kills. So
the share of KILLS that were in system survives the feed where the share of ATTACKS
does not, and it is the same quantity restricted to the rallies that scored.

IT IS CONTEXT, NOT QUALITY, and must not be graded directly. A hitter's in-system kill
share correlates +0.251 with her own hitting efficiency: a low share marks someone
getting worse balls, not someone heroically terminating garbage. What it is good for
is adjusting efficiency -- a hitter at 68% in system who hits .250 is doing more than
one at 90% who hits .250, and the boards currently cannot tell them apart.

It is, however, hers. Split-half 0.680 within a season, 0.810 over a full one, and a
teammate correlation of +0.056 -- only 8.6% of the variance is the team she plays for.

Two readers, because two feeds. The 2021-2025 seasons come from the old
stats.ncaa.org export, which carries a Set row before each attack; 2026 comes from the
ncaa-api point summary, which carries "(from NAME)" on each kill. They are the same
quantity measured two ways, and they agree: 77.8% of 2024 kills were in system by the
touch feed, 83.1% of one 2026 match by the summary feed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

KILL_FROM = re.compile(r"^Kill by (?P<hitter>.+?)\s*\(from (?P<setter>[^)]+)\)\.?$")
KILL_SOLO = re.compile(r"^Kill by (?P<hitter>.+?)\.?$")


def norm(name: str) -> str:
    """Names arrive as "Halle Schroder", "HERRON, Keira" and "Rachow,Zoe"."""
    n = " ".join((name or "").split())
    if "," in n:
        last, _, first = n.partition(",")
        n = f"{first.strip()} {last.strip()}"
    return n.casefold()


def setter_names(playermatch_csv: Path) -> dict[str, set[str]]:
    """team -> the normalised names carrying a setter label.

    Keyed on team alone, not (season, team): each file is already one season, and the
    Season column in this source reads "2025-2026" rather than "2025", so keying on it
    silently matched nothing and every kill came back out of system.
    """
    out: dict[str, set[str]] = defaultdict(set)
    with open(playermatch_csv, newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("P") or "").strip() == "S":
                out[r["Team"]].add(norm(r["Player"]))
    return out


def read_summary_pbp(pbp_dir: Path, setters: dict) -> pd.DataFrame:
    """Kills, and whether a setter set them, from the ncaa-api point summary."""
    rows = []
    files = sorted(pbp_dir.glob("*.json"))
    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        teams = {}
        for t in d.get("teams") or []:
            tid = t.get("teamId") or (t.get("team") or {}).get("teamId")
            nm = (t.get("nameShort") or t.get("shortName")
                  or (t.get("team") or {}).get("nameShort") or "")
            if tid is not None:
                teams[str(tid)] = nm
        for p in d.get("periods") or []:
            for e in p.get("playbyplayStats") or []:
                team = teams.get(str(e.get("teamId")), "")
                for pl in e.get("plays") or []:
                    txt = (pl.get("playText") or "").strip()
                    m = KILL_FROM.match(txt)
                    if m:
                        rows.append((team, norm(m["hitter"]), norm(m["setter"]), True))
                    elif txt.startswith("Kill by"):
                        m2 = KILL_SOLO.match(txt)
                        if m2:
                            rows.append((team, norm(m2["hitter"]), "", False))
        if i % 200 == 0:
            print(f"  read {i:,}/{len(files):,} matches", flush=True)
    df = pd.DataFrame(rows, columns=["team", "hitter", "setter", "assisted"])
    return df


def summarise(df: pd.DataFrame, season: str, setters: dict) -> pd.DataFrame:
    """Per hitter: kills, and how many a designated setter delivered."""
    if df.empty:
        return pd.DataFrame(columns=["season", "team", "_key", "kills_charted",
                                     "in_system_kills", "in_system_kill_pct"])
    known = {t: setters.get(t, set()) for t in df.team.unique()}
    df = df.copy()
    df["in_system"] = [bool(s) and s in known.get(t, ()) for t, s in
                       zip(df.team, df.setter)]
    g = (df.groupby(["team", "hitter"], as_index=False)
           .agg(kills_charted=("in_system", "size"),
                in_system_kills=("in_system", "sum")))
    g["season"] = season
    g["in_system_kill_pct"] = g.in_system_kills / g.kills_charted
    return g.rename(columns={"hitter": "_key"})[
        ["season", "team", "_key", "kills_charted", "in_system_kills",
         "in_system_kill_pct"]]


def from_touch_pbp(year: int, pbp_csv: Path, playerseason_csv: Path) -> pd.DataFrame:
    """The 2021-2025 route: in_system.py already flags who set each attack."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import in_system as I
    pos = I.load_positions(playerseason_csv)
    a = I.extract_attacks(pbp_csv, pos)
    k = a[a.kill == 1]
    g = (k.groupby(["team", "attacker"], as_index=False)
           .agg(kills_charted=("in_system", "size"),
                in_system_kills=("in_system", "sum")))
    g["season"] = str(year)
    g["in_system_kill_pct"] = g.in_system_kills / g.kills_charted
    g["_key"] = g.attacker.map(norm)
    return g[["season", "team", "_key", "kills_charted", "in_system_kills",
              "in_system_kill_pct"]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("year", type=int)
    ap.add_argument("--pbp-dir", type=Path)
    ap.add_argument("--gis-dir", type=Path, default=Path("../volleyball-gis/public/data"))
    ap.add_argument("--out", type=Path, default=Path("data/in_system_kills.parquet"))
    ap.add_argument("--touch-pbp", type=Path,
                    help="the old stats.ncaa.org pbp CSV, for 2021-2025")
    ap.add_argument("--playerseason", type=Path,
                    help="roster positions for the touch route")
    args = ap.parse_args()

    if args.touch_pbp:
        print(f"touch route: {args.touch_pbp}")
        out = from_touch_pbp(args.year, args.touch_pbp, args.playerseason)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        prev = (pd.read_parquet(args.out) if args.out.exists()
                else pd.DataFrame(columns=out.columns))
        prev = prev[prev.season != str(args.year)]
        pd.concat([prev, out], ignore_index=True).to_parquet(args.out, index=False)
        q = out[out.kills_charted >= 50]
        print(f"wrote {args.out}: {len(out):,} hitters ({len(q):,} with 50+ kills)")
        print(f"  in-system kill %: median {q.in_system_kill_pct.median():.3f}")
        return

    pm = args.gis_dir / f"wvb_playermatch_div1_{args.year}.csv"
    if not pm.exists():
        raise SystemExit(f"No {pm}")
    setters = setter_names(pm)
    print(f"{sum(len(v) for v in setters.values()):,} setter names across "
          f"{len(setters):,} teams")
    unmatched = 0

    pbp_dir = args.pbp_dir or Path(f"data/ncaa_api/pbp/{args.year}")
    if not pbp_dir.is_dir():
        raise SystemExit(f"No play-by-play at {pbp_dir}. Run the pipeline first.")
    print(f"reading {pbp_dir}")
    raw = read_summary_pbp(pbp_dir, setters)
    print(f"  {len(raw):,} kills, {raw.assisted.mean():.1%} with an assist named")
    out = summarise(raw, str(args.year), setters)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    prev = (pd.read_parquet(args.out) if args.out.exists()
            else pd.DataFrame(columns=out.columns))
    prev = prev[prev.season != str(args.year)]
    pd.concat([prev, out], ignore_index=True).to_parquet(args.out, index=False)
    q = out[out.kills_charted >= 50]
    print(f"wrote {args.out}: {len(out):,} hitters ({len(q):,} with 50+ kills)")
    if len(q):
        print(f"  in-system kill %: median {q.in_system_kill_pct.median():.3f}, "
              f"10th {q.in_system_kill_pct.quantile(.1):.3f}, "
              f"90th {q.in_system_kill_pct.quantile(.9):.3f}")


if __name__ == "__main__":
    main()
