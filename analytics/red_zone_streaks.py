"""Longest runs of sets won after reaching 20 points first.

THE STAT
--------
"First to the red zone" is the team that reaches 20 points first in a set. A team's
streak counts the consecutive sets it won in which it got there first. A set where the
opponent reached 20 first neither extends nor breaks it; the streak ends the first time
the team reaches 20 first and loses the set anyway.

Only sets 1-4 count. They play to 25, so 20 is the red zone. A fifth set plays to 15
and only reaches 20 in an extended deuce, where getting there first means almost
nothing.

Streaks run across season boundaries. Nebraska's run is quoted as one streak across
2025 and 2026, and a team's sets are one sequence whatever the calendar says.

DATA LIMITS, stated where the numbers are printed
------------------------------------------------
- Scores come from play-by-play. A set whose play-by-play does not end in a legal
  final score (about 5% of sets) is left out, so a streak can run straight through a
  set that might have broken it. The table counts those unreadable sets inside every
  streak's span so the reader can see how much was taken on trust.
- A match missing from the data entirely (Louisiana's 2026 home matches, the 2025
  Sun Belt) is invisible here.
- The current season's play-by-play is not in the repository; it lives with whoever
  runs the pipeline. Without it, "active" means active at the end of the last season
  on disk.

Usage:
    python3 analytics/red_zone_streaks.py               # table + chart in analysis/
    python3 analytics/red_zone_streaks.py --top 25
"""
from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RED_ZONE = 20


def set_table(rally_glob: str) -> pd.DataFrame:
    """One row per set: who reached 20 first, the final score, and whether it is legal."""
    parts = []
    for path in sorted(glob.glob(rally_glob)):
        season = re.search(r"(\d{4})\.parquet$", path).group(1)
        d = duckdb.sql(f"""
            WITH s AS (
                SELECT date, away_team, home_team, set_no, rally_no,
                       score_away + CASE WHEN winner = away_team THEN 1 ELSE 0 END AS a,
                       score_home + CASE WHEN winner = home_team THEN 1 ELSE 0 END AS h
                FROM read_parquet('{path}')
                WHERE set_no BETWEEN 1 AND 4
                  AND score_away IS NOT NULL AND score_home IS NOT NULL),
            fin AS (
                SELECT date, away_team, home_team, set_no,
                       arg_max(a, rally_no) AS a, arg_max(h, rally_no) AS h
                FROM s GROUP BY ALL),
            rz AS (
                SELECT date, away_team, home_team, set_no,
                       arg_min(CASE WHEN a >= {RED_ZONE} THEN away_team ELSE home_team END,
                               rally_no) AS first20
                FROM s WHERE a >= {RED_ZONE} OR h >= {RED_ZONE} GROUP BY ALL)
            SELECT fin.*, rz.first20 FROM fin
            LEFT JOIN rz USING (date, away_team, home_team, set_no)
        """).df()
        d["season"] = season
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    df["a"] = df.a.astype(int)
    df["h"] = df.h.astype(int)
    hi, margin = np.maximum(df.a, df.h), (df.a - df.h).abs()
    # sets 1-4: the winner reached 25, by two, and stopped there (or won a deuce by two)
    df["legal"] = (hi >= 25) & (margin >= 2) & ((hi == 25) | (margin == 2))
    df["set_winner"] = np.where(df.a > df.h, df.away_team, df.home_team)
    df["date"] = pd.to_datetime(df.date, format="%m/%d/%Y", errors="coerce")
    return df.dropna(subset=["date"])


def team_view(sets: pd.DataFrame) -> pd.DataFrame:
    """Each set twice, once from each side, in the order the team played them."""
    rows = []
    for side, other in (("away_team", "home_team"), ("home_team", "away_team")):
        rows.append(pd.DataFrame({
            "team": sets[side].astype(str), "opponent": sets[other].astype(str),
            "date": sets.date, "season": sets.season, "set_no": sets.set_no,
            "legal": sets.legal,
            "first20": sets.first20.astype(str) == sets[side].astype(str),
            "won": sets.set_winner.astype(str) == sets[side].astype(str),
            "score": np.where(side == "away_team",
                              sets.a.astype(str) + "-" + sets.h.astype(str),
                              sets.h.astype(str) + "-" + sets.a.astype(str))}))
    t = pd.concat(rows, ignore_index=True)
    # Two matches on one date (a tournament day) cannot be ordered from the feed; the
    # opponent name is a stable stand-in. It only matters if a streak ends that day.
    return t.sort_values(["team", "date", "opponent", "set_no"]).reset_index(drop=True)


def streaks(t: pd.DataFrame) -> pd.DataFrame:
    """Every maximal run of first-to-20 sets won, with the set that ended it."""
    out = []
    for team, g in t.groupby("team", sort=False):
        rz = g[g.legal & g.first20]
        run = []                                   # the current run's won sets
        for r in rz.itertuples():
            if r.won:
                run.append(r)
                continue
            if run:
                out.append(_row(team, g, run, broke=r))
            run = []
        if run:                                    # still going at the end of the data
            out.append(_row(team, g, run, broke=None))
    return pd.DataFrame(out)


def _row(team: str, g: pd.DataFrame, run: list, broke) -> dict:
    first, last = run[0], run[-1]
    upto = broke.date if broke is not None else g.date.max()
    span = g[(g.date >= first.date) & (g.date <= upto)]
    return {"team": team, "length": len(run),
            "start": first.date, "end": last.date,
            "seasons": f"{first.season}-{last.season}" if first.season != last.season
                       else first.season,
            "active": broke is None,
            "broken_by": None if broke is None else broke.opponent,
            "broken_on": None if broke is None else broke.date,
            "broken_score": None if broke is None else broke.score,
            "unreadable_sets": int((~span.legal).sum())}


# ---------------------------------------------------------------- chart
NU_RED = "#e41c38"        # Nebraska, the app's accent
OTHER = "#a8a7a1"         # every other team: context, not competition for the eye
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def chart(top: pd.DataFrame, path: Path, through: str, note: str,
          subtitle: str | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    n = len(top)
    fig, ax = plt.subplots(figsize=(10, 0.42 * n + 1.9), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    y = np.arange(n)[::-1]
    vmax = top.length.max()
    bar_h = 0.62
    for yi, r in zip(y, top.itertuples()):
        color = NU_RED if r.team == "Nebraska" else OTHER
        # square at the baseline, 4px-ish rounding at the data end only
        ax.add_patch(FancyBboxPatch((0, yi - bar_h / 2), r.length, bar_h,
                                    boxstyle="round,pad=0,rounding_size=0.18",
                                    mutation_aspect=vmax / n / 6,
                                    linewidth=0, facecolor=color))
        ax.add_patch(plt.Rectangle((0, yi - bar_h / 2), min(r.length, vmax * .02), bar_h,
                                   linewidth=0, facecolor=color))
        label = getattr(r, "label", None)
        tail = (label if isinstance(label, str) and label else
                "active" if r.active else f"ended {r.broken_on:%b %-d, %Y} vs {r.broken_by}")
        ax.text(r.length + vmax * 0.012, yi, f"{r.length}", va="center", ha="left",
                fontsize=10.5, fontweight="bold", color=INK)
        # the label starts after the value, however many digits the value has
        ax.text(r.length + vmax * (0.024 + 0.019 * len(str(r.length))), yi, tail,
                va="center",
                ha="left", fontsize=8.5, color=INK2)
        ax.text(-vmax * 0.012, yi + 0.13, r.team, va="center", ha="right", fontsize=10,
                fontweight="bold" if r.team == "Nebraska" else "normal", color=INK)
        span = (f"{r.start:%b %Y} \u2013 {r.end:%b %Y}" if r.start.year != r.end.year
                or r.start.month != r.end.month else f"{r.start:%b %Y}")
        ax.text(-vmax * 0.012, yi - 0.22, span, va="center", ha="right", fontsize=7.5,
                color=INK2)
    ax.set_xlim(0, vmax * 1.62)
    ax.set_ylim(-0.7, n - 0.3)
    ax.set_yticks([])
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis="x", colors=INK2, labelsize=8, length=0)
    ax.set_xlabel("Consecutive sets won after reaching 20 points first", color=INK2,
                  fontsize=9)
    H = 0.42 * n + 1.9                                   # figure height, inches
    fig.text(0.02, 1 - 0.18 / H, "Longest red-zone streaks in Division I women's volleyball",
             fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.02, 1 - 0.50 / H,
             subtitle or f"Sets won in a row after reaching 20 first, sets 1-4. "
                         f"Data {through}.",
             fontsize=9, color=INK2, va="top")
    fig.text(0.02, 0.012, note, fontsize=7, color=INK2, va="bottom")
    fig.subplots_adjust(left=0.24, right=0.98, top=1 - 0.85 / H, bottom=0.75 / H)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rallies", default="data/rallies/wvb_rallies_div1_*.parquet")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--out-dir", type=Path, default=Path("analysis"))
    args = ap.parse_args()

    sets = set_table(args.rallies)
    t = team_view(sets)
    st = streaks(t)
    st = st.sort_values(["length", "start"], ascending=[False, True]).reset_index(drop=True)
    st.insert(0, "rank", st.length.rank(ascending=False, method="min").astype(int))
    top = st.head(args.top)

    seasons = sorted(sets.season.unique())
    through = f"{seasons[0]}\u2013{seasons[-1]}, through {sets.date.max():%b %-d, %Y}"
    unreadable = 1 - sets.legal.mean()
    note = (f"Source: NCAA play-by-play. {unreadable:.1%} of sets have no readable final "
            "score and are skipped; a streak can pass through one. "
            "\"Active\" = unbroken at the last set on file.")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    png = args.out_dir / "red_zone_streaks.png"
    chart(top, png, through, note)
    cols = ["rank", "team", "length", "seasons", "start", "end", "active", "broken_by",
            "broken_on", "broken_score", "unreadable_sets"]
    top[cols].to_csv(args.out_dir / "red_zone_streaks.csv", index=False)

    print(f"{len(sets):,} sets 1-4 read, {sets.legal.mean():.1%} with a legal final "
          f"score; {through}")
    print(top[cols].to_string(index=False))
    nu = st[st.team == "Nebraska"].sort_values("start").tail(3)
    print("\nNebraska's most recent runs:")
    print(nu[cols].to_string(index=False))
    print(f"\nwrote {png} and {args.out_dir / 'red_zone_streaks.csv'}")


if __name__ == "__main__":
    main()
