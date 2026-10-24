"""The projected NCAA tournament field, for the Bracket tab.

THE FORMAT, as the committee ran it in 2025
-------------------------------------------
64 teams: one automatic bid per conference (31) and at-large picks for the rest. The
top 32 are seeded 1-8 inside four regions of 16; the other 32 are unseeded. The top 16
seeds host the first two rounds on campus, in pods of four: a 1-4 seed, a 5-8 seed and
two unseeded teams. Regional rounds and the Final Four are treated as neutral floors.

WHAT IS PROJECTED, AND HOW
--------------------------
Automatic bids go to the projected regular-season conference champion: conference
wins so far plus the win chances of every conference match left on the schedule, ties
broken by rating. Conference tournaments are not modelled, so a conference that awards
its bid in a tournament can produce a different champion.

At-large bids and seeding follow one of two orderings, the reader's choice:

  committee  RPI, computed here from the season's results. The committee works from
             RPI first, so this is the better guess at the bracket it will publish.
  power      the app's composite rating (Elo + ridge). The better guess at who is
             actually best, which is not the same question.

RPI is the standard 25/50/25 blend of a team's winning percentage, its opponents'
(excluding games against the team) and its opponents' opponents', over Division I
matches only. It is an approximation of the NCAA's figure, not a copy: the official
one can include adjustments this does not.

Seeds follow an S-curve: the four 1-seeds go to regions 1-4 in order, the 2-seeds come
back the other way, and so on. Unseeded teams are matched by rank, the strongest
unseeded team against the weakest seed. The committee places unseeded teams largely by
geography, which is not modelled.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from app import data as D

FIELD = 64
SEEDED = 32
# slot -> seed inside a region of 16, in bracket order. Pairs (0,1), (2,3), ... meet
# in the first round; each block of four is one campus pod hosted by its top slot.
REGION_SEEDS = [1, None, 8, None, 4, None, 5, None, 2, None, 7, None, 3, None, 6, None]


def rpi(season: str) -> pd.DataFrame:
    """25% own win %, 50% opponents' (minus games against us), 25% opponents' opponents'."""
    m = D.matches()
    ts = D.team_seasons()
    d1 = set(ts[(ts.season == season) & ts.conference.notna()
                & (ts.conference != "")].team)
    g = m[(m.season == season) & m.team.isin(d1) & m.opponent.isin(d1)][
        ["team", "opponent", "won"]].copy()
    g["won"] = g.won.astype(int)
    rec = g.groupby("team").won.agg(["sum", "count"])
    # head to head, so an opponent's record can be taken without its games against us
    h2h = g.groupby(["team", "opponent"]).won.agg(["sum", "count"])

    def wp_excluding(o, t):
        w, n = rec.at[o, "sum"], rec.at[o, "count"]
        if (o, t) in h2h.index:
            w, n = w - h2h.at[(o, t), "sum"], n - h2h.at[(o, t), "count"]
        return w / n if n else np.nan

    g["owp_game"] = [wp_excluding(o, t) for t, o in zip(g.team, g.opponent)]
    owp = g.groupby("team").owp_game.mean()
    g["oowp_game"] = g.opponent.map(owp)
    out = pd.DataFrame({"wp": rec["sum"] / rec["count"], "owp": owp,
                        "oowp": g.groupby("team").oowp_game.mean()})
    out["rpi"] = 0.25 * out.wp + 0.50 * out.owp + 0.25 * out.oowp
    out["rpi_rank"] = out.rpi.rank(ascending=False, method="min").astype(int)
    return out.reset_index()


def conference_champions(season: str, teams: pd.DataFrame) -> dict[str, str]:
    """Projected regular-season champion per conference."""
    conf = teams.set_index("team").conference
    m = D.matches()
    m = m[(m.season == season) & (m.location == "home")]
    m = m[m.team.map(conf).eq(m.opponent.map(conf)) & m.team.map(conf).notna()]
    xw: dict[str, float] = {}
    games: dict[str, float] = {}
    for t, o, w in zip(m.team, m.opponent, m.won.astype(int)):
        xw[t] = xw.get(t, 0) + w
        xw[o] = xw.get(o, 0) + (1 - w)
        games[t] = games.get(t, 0) + 1
        games[o] = games.get(o, 0) + 1
    s = D.schedule()
    if not s.empty:
        s = s[(s.season == season)]
        s = s[s.home.map(conf).eq(s.away.map(conf)) & s.home.map(conf).notna()]
        for h, a, p in zip(s.home, s.away, s.p_home):
            xw[h] = xw.get(h, 0) + p
            xw[a] = xw.get(a, 0) + (1 - p)
            games[h] = games.get(h, 0) + 1
            games[a] = games.get(a, 0) + 1
    t = teams.copy()
    t["conf_pct"] = [xw.get(x, 0) / games[x] if games.get(x) else np.nan for x in t.team]
    t = t.sort_values(["conference", "conf_pct", "rating_composite"],
                      ascending=[True, False, False])
    return {c: g.team.iloc[0] for c, g in t.dropna(subset=["conf_pct"]).groupby("conference")}


def place(order: list[str]) -> list[str]:
    """Sixty-four teams in overall order -> 64 bracket slots, region by region."""
    slots: list[str | None] = [None] * FIELD
    seeded, unseeded = order[:SEEDED], order[SEEDED:FIELD]
    for i, team in enumerate(seeded):
        line, k = divmod(i, 4)                   # seed line 0-7, position on it
        region = k if line % 2 == 0 else 3 - k   # snake
        pos = REGION_SEEDS.index(line + 1)
        slots[region * 16 + pos] = team
        # the first-round opponent: overall 64 meets overall 1, 63 meets 2 ...
        slots[region * 16 + pos + 1] = unseeded[SEEDED - 1 - i]
    return slots


@lru_cache(maxsize=8)
def bracket_data(season: str) -> dict | None:
    """Everything the bracket component needs, for both seeding orders."""
    m = D.matchup_model()
    pr = D.power_ratings()
    pr = pr[(pr.season == season) & pr.elo.notna()]
    if not m or pr.empty:
        return None
    ts = D.team_seasons()
    ts = ts[ts.season == season][["team", "conference", "wins", "losses"]]
    t = pr.merge(ts, on="team", how="left")
    t = t[t.conference.notna() & (t.conference != "")]
    t = t.merge(rpi(season)[["team", "rpi", "rpi_rank"]], on="team", how="left")
    champs = conference_champions(season, t)
    auto = set(champs.values())

    fields = {}
    for basis, key in (("committee", "rpi"), ("power", "rating_composite")):
        ranked = t.sort_values(key, ascending=False).team.tolist()
        at_large = [x for x in ranked if x not in auto][:FIELD - len(auto)]
        field = [x for x in ranked if x in auto or x in at_large]
        fields[basis] = {"slots": place(field), "order": ranked,
                         "pool": [x for x in ranked if x not in field]}

    teams = {
        r.team: {"conf": r.conference,
                 "rec": f"{int(r.wins)}-{int(r.losses)}" if pd.notna(r.wins) else "",
                 "elo": round(float(r.elo), 1), "ridge": round(float(r.rating_overall), 3),
                 "comp": round(float(r.rating_composite), 2),
                 "comp_rank": int(r.rank_composite),
                 "rpi": None if pd.isna(r.rpi) else round(float(r.rpi), 4),
                 "rpi_rank": None if pd.isna(r.rpi_rank) else int(r.rpi_rank),
                 "auto": r.team in auto}
        for r in t.itertuples()}
    c = m["coef"]
    return {"season": season, "coef": [c["home"], c["elo_per_100"], c["ridge_per_10"]],
            "teams": teams, "fields": fields, "champions": champs,
            "n_auto": len(auto)}
