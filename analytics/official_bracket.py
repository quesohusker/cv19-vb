"""Check, or start, the committee's official bracket file.

The bracket lives in tournament/official_bracket_<season>.csv, one row per team; the
format is in tournament/README.md and app/bracket.py official_bracket(). This script:

  --check     (default) loads it exactly as the app and the simulator will, and either
              prints the bracket region by region or lists every problem in it --
              misspelled teams come with the closest names the data knows.
  --template  writes tournament/official_bracket_<season>_template.csv from the
              projected committee-style field, so filling in the real bracket is
              editing names rather than typing 64 rows.

Usage:
    python3 analytics/official_bracket.py 2026
    python3 analytics/official_bracket.py 2026 --template
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import bracket as BR      # noqa: E402

# projected regions are in S-curve order, whose semifinals are 1 v 4 and 2 v 3; the
# file is in printed order, whose semifinals are 1 v 2 and 3 v 4
PRINTED = [0, 3, 1, 2]


def template(season: str) -> Path:
    b = BR.bracket_data(season)
    f = b["fields"]["committee"]
    rows = []
    for order, rg in enumerate(PRINTED, start=1):
        for line in range(16):
            seed = BR.REGION_SEEDS[line]
            rows.append({"region": f["slots"][rg * 16], "region_order": order,
                         "line": line + 1, "seed": seed or "",
                         "team": f["slots"][rg * 16 + line],
                         "pod_host": "Y" if seed and seed <= 4 else "",
                         "regional_host": ""})
    out = BR.TOURNEY_DIR / f"official_bracket_{season}_template.csv"
    out.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def show(ob: dict) -> None:
    for r in range(4):
        host = ob["regional_hosts"][r]
        print(f"\n{ob['region_names'][r]} region (printed position {r + 1})"
              f"{f', regionals hosted by {host}' if host else ', regionals neutral'}")
        for p in range(4):
            pos = ob["pod_host_pos"][4 * r + p]
            host = ob["slots"][pos] if pos >= 0 else "neutral site"
            print(f"  pod {p + 1} (hosted by {host}):")
            for k in range(2):
                i = 16 * r + 4 * p + 2 * k
                a, b = ob["slots"][i], ob["slots"][i + 1]
                sa, sb = ob["seeds"][i], ob["seeds"][i + 1]
                print(f"    {f'({sa}) ' if sa else ''}{a}  v  {f'({sb}) ' if sb else ''}{b}")
    print("\nNational semifinals: " + f"{ob['region_names'][0]} v {ob['region_names'][1]}, "
          f"{ob['region_names'][2]} v {ob['region_names'][3]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("season")
    ap.add_argument("--template", action="store_true")
    args = ap.parse_args()
    if args.template:
        print(f"wrote {template(args.season)}")
        return
    try:
        ob = BR.official_bracket(args.season)
    except BR.BracketError as e:
        sys.exit(f"NOT READY -- fix these and run again:\n{e}")
    if ob is None:
        sys.exit(f"No {BR.TOURNEY_DIR / f'official_bracket_{args.season}.csv'} yet.")
    show(ob)
    print("\nOK: 64 teams, every name known. The app and --official will use this file.")


if __name__ == "__main__":
    main()
