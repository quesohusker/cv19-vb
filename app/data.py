"""Data access for the Streamlit app.

Everything the app needs is precomputed into app_data/ by
analytics/build_app_data.py. Nothing here touches raw play-by-play, and nothing
recomputes a benchmark -- the flags and grades are baked in at build time so the
app and the analysis can never disagree about what a grade means.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
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



def schedule_strength(season: str, conference: str | None = None,
                      min_matches: int = 5) -> pd.DataFrame:
    """Schedule difficulty per team, with the rating it is being compared against.

    SOS is computed in the ratings pipeline as the mean rating_overall of the teams a
    side actually played. It is reported, never folded into the rating: the ridge
    already adjusts for opponents. Ranks stay national under a conference filter, the
    same as every other board here.
    """
    pr = power_ratings()
    pr = pr[(pr.season == season) & (pr.n_matches >= min_matches)]
    if "sos" not in pr.columns:
        return pd.DataFrame()
    ts = team_seasons()[["season", "team", "conference", "wins", "losses", "grade"]]
    out = pr.merge(ts, on=["season", "team"], how="left")
    if conference:
        out = out[out.conference == conference]
    return out.sort_values("rank_sos").reset_index(drop=True)


def conference_schedule(season: str, min_teams: int = 4) -> pd.DataFrame:
    """Mean schedule difficulty and mean rating by conference.

    Both columns are needed together: a conference can look hard because its members
    are good (they play each other) rather than because it reached outside for tough
    non-conference opponents. The gap between the two is the interesting number.
    """
    d = schedule_strength(season)
    if d.empty:
        return d
    d = d[d.conference.notna() & (d.conference != "")]
    g = d.groupby("conference").agg(teams=("team", "size"), sos=("sos", "mean"),
                                    rating=("rating_overall", "mean"))
    g = g[g.teams >= min_teams].reset_index()
    g["gap"] = g.sos - g.rating
    return g.sort_values("sos", ascending=False).reset_index(drop=True)


def team_schedule(season: str, team: str) -> pd.DataFrame:
    """Every opponent a team played, with that opponent's rating and the result."""
    tm = team_matches(season, team)
    if tm.empty:
        return tm
    pr = power_ratings()
    pr = pr[pr.season == season].set_index("team")
    out = tm[["match_date", "opponent", "won", "sets_for", "sets_against"]].copy()
    out["opp_rating"] = pr.rating_overall.reindex(out.opponent).to_numpy()
    out["opp_rank"] = pr.rank_composite.reindex(out.opponent).to_numpy()
    return out.sort_values("opp_rating", ascending=False).reset_index(drop=True)


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
PIN_HITTERS = "Pin hitters (both)"
PIN_BOARDS = ("Six-rotation hitter", "Front-row hitter")

POSITION_ORDER = ["Six-rotation hitter", "Front-row hitter", "Middle blocker",
                  "Setter", "Back row"]


def pin_hitters(season: str, conference: str | None = None) -> pd.DataFrame:
    """The two pin boards shown together, each player still rated on her own board.

    They are one position to a fan and two jobs to the model: a six-rotation hitter is
    graded on passing and digging, a front-row hitter on blocking, because that is what
    each is actually asked to do. Putting them in one table is a reading convenience, so
    rating and rank_in_position are left exactly as they were computed -- within her own
    board, against her own benchmarks. Nothing here re-ranks anyone.

    The consequence to be honest about: two players in this table can show the same
    rating and not be comparable, which is why the position column is not optional here.
    """
    p = players()
    out = p[(p.season == season) & p.ranked & p.position.isin(PIN_BOARDS)].copy()
    if conference:
        out = out[out.conference == conference]
    # Interleaved by rank rather than stacked board after board, so the top of the table
    # is the best pins rather than all of one kind.
    return (out.sort_values(["rank_in_position", "position"], na_position="last")
               .reset_index(drop=True))


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


def team_conference(season: str, team: str) -> str | None:
    """A team's conference, or None when the season file does not carry one."""
    ts = team_seasons()
    row = ts[(ts.season == season) & (ts.team == team)]
    if row.empty or pd.isna(row.conference.iloc[0]):
        return None
    return str(row.conference.iloc[0])


@lru_cache(maxsize=16)
def metric_ranks(season: str, conference: str | None = None,
                 min_matches: int = 5) -> pd.DataFrame:
    """Where each team sits on every graded metric, as a rank over a pool of teams.

    The season cell on the benchmark page is the team's own average, so the rank
    beside it has to rank the same quantity: each team's season average, not any
    single match. Direction comes from the benchmark, so 1 is always the best
    team on that metric. `conference` restricts the pool; None ranks nationally.
    Teams with fewer than `min_matches` graded matches are left out of the pool,
    for the same reason every other board here drops them: a three-match average
    is not comparable with a twenty-match one.
    """
    m = matches()
    m = m[m.season == season]
    if conference:
        m = m[m.conference == conference]
    cols = [b["metric"] for b in graded_benchmarks() if b["metric"] in m.columns]
    if m.empty or not cols:
        return pd.DataFrame()
    g = m.groupby("team")
    played = g.size()
    avg = g[cols].mean().loc[played[played >= min_matches].index]
    out = pd.DataFrame(index=avg.index)
    for b in graded_benchmarks():
        metric = b["metric"]
        if metric not in avg.columns:
            continue
        out[metric] = avg[metric].rank(
            ascending=b["direction"] != "higher_is_better", method="min")
    return out


# ------------------------------------------------------------------ predictor
# Built by analytics/matchup_model.py. Win probability is a three-number logistic on the
# two published ratings, Elo and the ridge, plus the home edge, fitted on pre-match
# information only. See that module's docstring for what was tested and left out.

@lru_cache(maxsize=1)
def matchup_model() -> dict:
    f = DATA_DIR / "matchup_model.json"
    return json.loads(f.read_text()) if f.exists() else {}


@lru_cache(maxsize=1)
def match_predictions() -> pd.DataFrame:
    """Every match from the first fitted season on, with its PRE-match home win chance."""
    f = DATA_DIR / "match_predictions.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame()


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


VENUES = ("a", "neutral", "b")      # A hosts / neutral floor / B hosts


def predict(season: str, a: str, b: str, venue: str = "neutral") -> dict | None:
    """Win probability, scoreline odds and projected side-out for A against B.

    Uses the ratings the Power Rankings page publishes for `season`, which for the
    current season means "as of the latest match". None when either team has no rating.
    """
    m = matchup_model()
    pr = power_ratings()
    pr = pr[pr.season == season].set_index("team")
    if not m or a not in pr.index or b not in pr.index:
        return None
    ra, rb = pr.loc[a], pr.loc[b]
    if pd.isna(ra.elo) or pd.isna(rb.elo):
        return None
    v = {"a": 1.0, "neutral": 0.0, "b": -1.0}[venue]
    de = (ra.elo - rb.elo) / 100.0
    dr = (ra.rating_overall - rb.rating_overall) / 10.0
    c, ca = m["coef"], m["coef_alone"]
    p = _sigmoid(c["home"] * v + c["elo_per_100"] * de + c["ridge_per_10"] * dr)
    p_elo = _sigmoid(ca["elo"]["home"] * v + ca["elo"]["elo_per_100"] * de)
    p_ridge = _sigmoid(ca["ridge"]["home"] * v + ca["ridge"]["ridge_per_10"] * dr)

    # scorelines: what actually happened to favourites this size, scaled to sum to p
    tab = pd.DataFrame(m["scorelines"])
    fav_is_a = p >= 0.5
    pf = p if fav_is_a else 1.0 - p
    raw = {o: float(np.interp(pf, tab.p_fav, tab[o])) for o in
           ("fav_3_0", "fav_3_1", "fav_3_2", "dog_3_2", "dog_3_1", "dog_3_0")}
    fsum = raw["fav_3_0"] + raw["fav_3_1"] + raw["fav_3_2"]
    dsum = raw["dog_3_2"] + raw["dog_3_1"] + raw["dog_3_0"]
    fav = {k: raw[f"fav_{k}"] * pf / fsum for k in ("3_0", "3_1", "3_2")}
    dog = {k: raw[f"dog_{k}"] * (1 - pf) / dsum for k in ("3_0", "3_1", "3_2")}
    sets_a, sets_b = (fav, dog) if fav_is_a else (dog, fav)

    # The ridge's own structure gives each side's expected side-out rate. Neutral floor:
    # the ridge carries no home term, so this does not move with the venue.
    lg = float(ra.league_sideout)
    return {
        "p_a": p, "p_b": 1.0 - p, "p_elo": p_elo, "p_ridge": p_ridge,
        "sets_a": sets_a, "sets_b": sets_b,
        "five_sets": sets_a["3_2"] + sets_b["3_2"],
        "sideout_a": lg + ra.rating_off - rb.rating_def,
        "sideout_b": lg + rb.rating_off - ra.rating_def,
        "elo_a": float(ra.elo), "elo_b": float(rb.elo),
        "ridge_a": float(ra.rating_overall), "ridge_b": float(rb.rating_overall),
        "rank_a": int(ra.rank_composite), "rank_b": int(rb.rank_composite),
    }


def _team_view(season: str) -> pd.DataFrame:
    """match_predictions turned to one row per team per match, from that team's side."""
    mp = match_predictions()
    if mp.empty:
        return mp
    s = mp[mp.season == season]
    h = pd.DataFrame({"date": s.date, "team": s.home, "opponent": s.away, "venue": "home",
                      "p": s.p_home, "won": s.home_won, "sf": s.home_sets,
                      "sa": s.away_sets})
    a = pd.DataFrame({"date": s.date, "team": s.away, "opponent": s.home, "venue": "away",
                      "p": 1.0 - s.p_home, "won": 1 - s.home_won, "sf": s.away_sets,
                      "sa": s.home_sets})
    return pd.concat([h, a], ignore_index=True).sort_values(["team", "date"])


def expected_wins(season: str, conference: str | None = None,
                  min_matches: int = 5) -> pd.DataFrame:
    """Actual wins against the sum of pre-match win probabilities, per team."""
    t = _team_view(season)
    if t.empty:
        return t
    t["upset_w"] = (t.won == 1) & (t.p < 0.5)
    t["upset_l"] = (t.won == 0) & (t.p > 0.5)
    g = t.groupby("team")
    out = pd.DataFrame({
        "matches": g.size(), "wins": g.won.sum(), "xw": g.p.sum(),
        "var": g.p.apply(lambda p: float((p * (1 - p)).sum())),
        "upset_wins": g.upset_w.sum(), "upset_losses": g.upset_l.sum(),
    }).reset_index()
    out["losses"] = out.matches - out.wins
    out["xl"] = out.matches - out.xw
    out["diff"] = out.wins - out.xw
    out["z"] = out["diff"] / np.sqrt(out["var"].where(out["var"] > 0))
    ts = team_seasons()
    out = out.merge(ts[ts.season == season][["team", "conference"]], on="team", how="left")
    pj = projections(season)
    if not pj.empty:
        out = out.merge(pj, on="team", how="left")
        # a team with nothing left to play finishes on its current record
        out["left"] = out.left.fillna(0).astype(int)
        out["left_xw"] = out.left_xw.fillna(0.0)
        out["win_out"] = out.win_out.fillna(1.0)
        out["proj_w"] = out.wins + out.left_xw
        out["proj_l"] = out.losses + out.left - out.left_xw
        out["proj_lo"] = out.wins + out.lo.fillna(0)
        out["proj_hi"] = out.wins + out.hi.fillna(0)
    out = out[out.matches >= min_matches]
    if conference:
        out = out[out.conference == conference]
    # Expected wins as a share of the schedule, not a raw total: a raw total ranks a
    # 32-match schedule over a 28-match one at equal strength, which put Pittsburgh and
    # Louisville above Nebraska for no reason but the length of their calendars.
    if "proj_w" in out.columns:
        rate = out.proj_w / (out.matches + out.left)
    else:
        rate = out.xw / out.matches
    return out.assign(_r=rate).sort_values("_r", ascending=False).drop(
        columns="_r").reset_index(drop=True)


def team_predictions(season: str, team: str) -> pd.DataFrame:
    """One team's matches with the pre-match chance it was given, and the running tally."""
    t = _team_view(season)
    if t.empty:
        return t
    t = t[t.team == team].copy()
    t["cum_w"] = t.won.cumsum()
    t["cum_xw"] = t.p.cumsum()
    return t.reset_index(drop=True)


def head_to_head(season: str, a: str, b: str) -> pd.DataFrame:
    """This season's meetings between A and B, from A's side."""
    t = team_predictions(season, a)
    return t[t.opponent == b] if not t.empty else t


@lru_cache(maxsize=1)
def schedule() -> pd.DataFrame:
    """Unplayed matches with a win chance on today's ratings. Current season only."""
    f = DATA_DIR / "schedule.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame()


def _win_dist(ps) -> np.ndarray:
    """Exact distribution of wins over independent matches (Poisson-binomial)."""
    d = np.array([1.0])
    for p in ps:
        d = np.append(d * (1 - p), 0.0) + np.append(0.0, d * p)
    return d


def upcoming(season: str, team: str) -> pd.DataFrame:
    """A team's remaining matches, from its own side."""
    s = schedule()
    if s.empty:
        return s
    s = s[s.season == season]
    h = s[s.home == team].assign(opponent=lambda x: x.away, venue="home", p=lambda x: x.p_home)
    a = s[s.away == team].assign(opponent=lambda x: x.home, venue="away",
                                 p=lambda x: 1 - x.p_home)
    return pd.concat([h, a])[["date", "opponent", "venue", "p", "fallback"]].sort_values(
        "date").reset_index(drop=True)


def projections(season: str) -> pd.DataFrame:
    """Final record per team: wins so far plus the remaining schedule's win chances."""
    s = schedule()
    if s.empty or season not in set(s.season):
        return pd.DataFrame()
    s = s[s.season == season]
    side = pd.concat([pd.DataFrame({"team": s.home, "p": s.p_home}),
                      pd.DataFrame({"team": s.away, "p": 1 - s.p_home})])
    rows = []
    for team, g in side.groupby("team"):
        dist = _win_dist(g.p.to_numpy())
        cdf = np.cumsum(dist)
        rows.append({"team": team, "left": len(g), "left_xw": float(g.p.sum()),
                     "lo": int(np.searchsorted(cdf, 0.10)),
                     "hi": int(np.searchsorted(cdf, 0.90)),
                     "win_out": float(dist[-1])})
    return pd.DataFrame(rows)
