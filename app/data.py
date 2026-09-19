"""Data access for the Streamlit app.

Everything the app needs is precomputed into app_data/ by
analytics/build_app_data.py. Nothing here touches raw play-by-play, and nothing
recomputes a benchmark -- the flags and grades are baked in at build time so the
app and the analysis can never disagree about what a grade means.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "app_data"


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / name)


@lru_cache(maxsize=1)
def matches() -> pd.DataFrame:
    """One row per team per match, with the seven flags and the 0-7 grade."""
    return _read("matches.parquet")


@lru_cache(maxsize=1)
def team_seasons() -> pd.DataFrame:
    """One row per team-season: mean grade, per-benchmark hit rate, record, ranks."""
    return _read("team_seasons.parquet")


@lru_cache(maxsize=1)
def league_baselines() -> pd.DataFrame:
    """Per-season percentile table for every metric."""
    return _read("league_baselines.parquet")


@lru_cache(maxsize=1)
def benchmarks() -> list[dict]:
    """Benchmark definitions. Filter on `graded` for the seven that make up the grade."""
    return json.loads((DATA_DIR / "benchmarks.json").read_text())


@lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads((DATA_DIR / "meta.json").read_text())


def graded_benchmarks() -> list[dict]:
    return [b for b in benchmarks() if b["graded"]]


def context_benchmarks() -> list[dict]:
    return [b for b in benchmarks() if not b["graded"]]


def seasons() -> list[str]:
    return sorted(matches().season.unique().tolist(), reverse=True)


def conferences(season: str) -> list[str]:
    ts = team_seasons()
    return sorted(ts[ts.season == season].conference.dropna().unique().tolist())


def power_rankings(season: str, conference: str | None = None,
                   min_matches: int = 15) -> pd.DataFrame:
    """Teams ordered by mean match grade. Ranks are league-wide even when filtered,
    so a conference view still shows where its teams sit nationally."""
    ts = team_seasons()
    out = ts[(ts.season == season) & (ts.graded_matches >= min_matches)].copy()
    if conference:
        out = out[out.conference == conference]
    return out.sort_values("grade", ascending=False).reset_index(drop=True)


def team_matches(season: str, team: str) -> pd.DataFrame:
    m = matches()
    return m[(m.season == season) & (m.team == team)].sort_values("match_date")


def benchmark_profile(season: str, team: str) -> pd.DataFrame:
    """Per-benchmark hit rate for one team against the league median, for a team page."""
    tm = team_matches(season, team)
    league = matches()
    league = league[league.season == season]
    rows = []
    for b in graded_benchmarks():
        col = b["flag_column"]
        if col not in tm.columns:
            continue
        rows.append({
            "benchmark": b["label"], "phase": b["phase"],
            "team_rate": tm[col].mean(), "league_rate": league[col].mean(),
        })
    out = pd.DataFrame(rows)
    out["vs_league"] = out.team_rate - out.league_rate
    return out


def grade_vs_wins(season: str, min_matches: int = 15) -> pd.DataFrame:
    ts = team_seasons()
    return ts[(ts.season == season) & (ts.graded_matches >= min_matches)][
        ["team", "conference", "grade", "win_pct", "graded_matches"]]


@lru_cache(maxsize=1)
def power_ratings() -> pd.DataFrame:
    """Opponent-adjusted ratings: overall / offense / defense, with national ranks."""
    return _read("power_ratings.parquet")


def rankings(season: str, conference: str | None = None,
             min_matches: int = 5) -> pd.DataFrame:
    """Power rankings joined to record and conference.

    Ranks stay national when a conference filter is applied, matching the CFB app.
    """
    pr = power_ratings()
    pr = pr[(pr.season == season) & (pr.n_matches >= min_matches)]
    ts = team_seasons()[["season", "team", "conference", "wins", "losses",
                         "win_pct", "grade", "grade_rank", "graded_matches"]]
    out = pr.merge(ts, on=["season", "team"], how="left")
    if conference:
        out = out[out.conference == conference]
    # The board leads with the composite. Fall back to the ridge rank if the composite
    # stage has not been run, so a half-built app_data still renders.
    key = "rank_composite" if "rank_composite" in out.columns else "rank_overall"
    return out.sort_values(key).reset_index(drop=True)


@lru_cache(maxsize=1)
def players() -> pd.DataFrame:
    """One row per player-season, with position, benchmarks and the ranked rating."""
    return _read("players.parquet")


@lru_cache(maxsize=1)
def player_benchmarks() -> dict:
    return json.loads((DATA_DIR / "player_benchmarks.json").read_text())


def positions() -> list[str]:
    return sorted(players().position.dropna().unique().tolist())


def player_rankings(season: str, position: str, conference: str | None = None,
                    team: str | None = None, include_unranked: bool = False
                    ) -> pd.DataFrame:
    """A position board for one season, national ranks preserved under any filter.

    The rank is computed once at build time over everyone eligible, so filtering to a
    conference or a team shows where those players sit nationally rather than
    renumbering them 1..n. Players held out by the recency rule are excluded unless
    asked for, and never carry a rank.
    """
    p = players()
    out = p[(p.season == season) & (p.position == position)].copy()
    if not include_unranked:
        out = out[out.ranked]
    if conference:
        out = out[out.conference == conference]
    if team:
        out = out[out.team == team]
    return out.sort_values("rank_in_position", na_position="last").reset_index(drop=True)


def player_conferences(season: str) -> list[str]:
    p = players()
    return sorted(p[p.season == season].conference.dropna().replace("", pd.NA)
                  .dropna().unique().tolist())


@lru_cache(maxsize=1)
def player_matches() -> pd.DataFrame:
    """Match-by-match lines for every ranked player. A season number is an average,
    and an average hides a slump."""
    return _read("player_matches.parquet")


def player_log(season: str, team: str, player: str) -> pd.DataFrame:
    """One player's season, match by match, with the rate metrics computed per match."""
    m = player_matches()
    g = m[(m.season == season) & (m.team == team) & (m.player == player)].copy()
    if g.empty:
        return g
    sets = g.S.replace(0, pd.NA)
    g["hit_pct"] = (g.Kills - g.Errors) / g.TotalAttacks.where(g.TotalAttacks >= 3)
    g["kills_per_set"] = g.Kills / sets
    g["digs_per_set"] = g.Digs / sets
    g["assists_per_set"] = g.Assists / sets
    g["blocks_per_set"] = (g.BlockSolos + g.BlockAssists / 2) / sets
    g["aces_per_set"] = g.Aces / sets
    g["rec_err_rate"] = g.RErr / g.RetAtt.where(g.RetAtt >= 3)
    return g.sort_values("date")


ALL_POSITIONS = "All positions"

POSITION_ORDER = ["Six-rotation hitter", "Front-row hitter", "Middle blocker",
                  "Setter", "Back row"]


def all_positions(season: str, conference: str | None = None,
                  team: str | None = None) -> pd.DataFrame:
    """Every ranked player in one season, across all five boards.

    Ordered by position and then by national rank, never by rating across positions:
    the boards grade different jobs, so a setter's 92 and a middle's 92 are not the
    same 92 and stacking them would invent a pecking order the numbers cannot carry.
    """
    p = players()
    out = p[(p.season == season) & p.ranked].copy()
    if conference:
        out = out[out.conference == conference]
    if team:
        out = out[out.team == team]
    order = {g: i for i, g in enumerate(POSITION_ORDER)}
    out["_o"] = out.position.map(order).fillna(99)
    return (out.sort_values(["_o", "rank_in_position"], na_position="last")
               .drop(columns="_o").reset_index(drop=True))


def team_board(season: str, team: str, include_unranked: bool = False) -> pd.DataFrame:
    """Every ranked player on one team, across all five positions.

    Ordered by position and then by national rank rather than by rating, because a
    rating is only comparable inside a position -- the boards grade different things,
    so a setter's 92 and a middle's 92 are not the same 92 and stacking them would
    invent a roster pecking order the numbers cannot support.
    """
    p = players()
    out = p[(p.season == season) & (p.team == team)].copy()
    if not include_unranked:
        out = out[out.ranked]
    order = {g: i for i, g in enumerate(POSITION_ORDER)}
    out["_o"] = out.position.map(order).fillna(99)
    return (out.sort_values(["_o", "rank_in_position"], na_position="last")
               .drop(columns="_o").reset_index(drop=True))


def player_teams(season: str) -> list[str]:
    p = players()
    return sorted(p[(p.season == season) & p.ranked].team.unique().tolist())
