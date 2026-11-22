"""The projected NCAA tournament field, for the Bracket tab.

THE FORMAT, as the committee ran it in 2025
-------------------------------------------
64 teams: one automatic bid per conference (31) and at-large picks for the rest. The
top 32 are seeded 1-8 inside four regions of 16; the other 32 are unseeded. The top 16
seeds host the first two rounds on campus, in pods of four: a 1-4 seed, a 5-8 seed and
two unseeded teams. Regional rounds and the Final Four are treated as neutral floors.

WHAT IS PROJECTED, AND HOW
--------------------------
An automatic bid that has been won is taken as won: tournament/auto_bids_<season>.csv
lists them as conferences finish. Every other bid goes to the projected regular-season
champion: conference wins so far plus the win chances of every conference match left
on the schedule, ties broken by rating. Conference tournaments are not modelled, so
until a league's winner is listed its bid is a regular-season guess.

Once the committee publishes the real bracket, tournament/official_bracket_<season>.csv
replaces all of this: the Bracket tab offers it first, and analytics/tournament_sim.py
--official plays it out.

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

import difflib
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app import data as D

FIELD = 64
SEEDED = 32
INDEPENDENT = "DI Independent"
# Hand-kept tournament facts: automatic bids as they are won, and the official bracket
# once the committee publishes it. See tournament/README.md.
TOURNEY_DIR = Path(__file__).resolve().parent.parent / "tournament"
# slot -> seed inside a region of 16, in bracket order, top to bottom: the 1 seed's pod
# at the top and the 2 seed's at the bottom, as every printed bracket has it. Pairs
# (0,1), (2,3), ... meet in the first round; each block of four is one campus pod,
# hosted by its 1-4 seed, which is not always the first slot (the 5 sits above the 4).
REGION_SEEDS = [1, None, 8, None, 5, None, 4, None, 6, None, 3, None, 7, None, 2, None]


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


def auto_bids(season: str) -> dict[str, str]:
    """Automatic bids already won: conference -> team, from tournament/auto_bids_<season>.csv."""
    f = TOURNEY_DIR / f"auto_bids_{season}.csv"
    if not f.exists():
        return {}
    d = pd.read_csv(f, dtype=str).dropna(subset=["conference", "team"])
    return dict(zip(d.conference.str.strip(), d.team.str.strip()))


class BracketError(ValueError):
    """The official bracket file is malformed; the message lists every problem."""


def official_bracket(season: str) -> dict | None:
    """The committee's bracket from tournament/official_bracket_<season>.csv, or None.

    One row per team: region, region_order (1-4 as printed: top left, bottom left, top
    right, bottom right, so the national semifinals are 1 v 2 and 3 v 4), line (1-16,
    top to bottom; lines 1-2 meet in the first round, 1-4 form one campus pod), seed,
    team, pod_host (Y on the team hosting its pod's first two rounds) and regional_host
    (Y on the team hosting its region's semifinal and final). Returns the 64 teams in
    bracket order with seeds, host positions and region names.
    """
    f = TOURNEY_DIR / f"official_bracket_{season}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, dtype=str).fillna("")
    d.columns = [c.strip().lower() for c in d.columns]
    problems = []
    need = {"region", "region_order", "line", "team"}
    if need - set(d.columns):
        raise BracketError(f"{f.name}: missing columns {sorted(need - set(d.columns))}")
    for c in ("seed", "pod_host", "regional_host"):
        if c not in d.columns:
            d[c] = ""
    d = d.apply(lambda s: s.str.strip())
    d = d[d.team != ""]
    try:
        d["region_order"] = d.region_order.astype(int)
        d["line"] = d.line.astype(int)
    except ValueError:
        raise BracketError(f"{f.name}: region_order and line must be whole numbers")
    if len(d) != FIELD:
        problems.append(f"{len(d)} teams, not {FIELD}")
    for r in range(1, 5):
        g = d[d.region_order == r]
        if sorted(g.line) != list(range(1, 17)):
            problems.append(f"region_order {r}: lines must be 1-16 once each "
                            f"(has {sorted(g.line)})")
        if g.region.nunique() > 1:
            problems.append(f"region_order {r}: more than one region name "
                            f"{sorted(g.region.unique())}")
        if (g.regional_host.str.upper() == "Y").sum() > 1:
            problems.append(f"region_order {r}: more than one regional_host")
        for p in range(4):
            pod = g[(g.line - 1) // 4 == p]
            if (pod.pod_host.str.upper() == "Y").sum() > 1:
                problems.append(f"region_order {r}, lines {4*p+1}-{4*p+4}: more than one pod_host")
    dup = d.team[d.team.duplicated()].tolist()
    if dup:
        problems.append(f"listed twice: {dup}")
    ts = D.team_seasons()
    known = set(ts[ts.season == season].team)
    every = sorted(set(ts.team))
    for t in d.team:
        if t not in known:
            # the NCAA prints "Penn State", "Western Kentucky"; the data says "Penn St."
            alt = (t.replace(" State", " St.").replace("Saint ", "St. ")
                   .replace("Kentucky", "Ky.").replace("Carolina", "Caro."))
            near = list(dict.fromkeys(
                difflib.get_close_matches(alt, every, n=3, cutoff=0.6)
                + difflib.get_close_matches(t, every, n=3, cutoff=0.6)))[:3]
            problems.append(f"unknown team '{t}'" + (f" (did you mean {', '.join(near)}?)"
                                                       if near else ""))
    bad_seed = [s for s in d.seed if s and not s.isdigit()]
    if bad_seed:
        problems.append(f"seeds must be numbers or blank: {bad_seed}")
    if problems:
        raise BracketError(f"{f.name}:\n  " + "\n  ".join(problems))

    d = d.sort_values(["region_order", "line"]).reset_index(drop=True)
    pod_host = []
    for p in range(16):
        rows = d.index[(d.index // 4 == p) & (d.pod_host.str.upper() == "Y")]
        pod_host.append(int(rows[0]) if len(rows) else -1)
    regional = []
    for r in range(4):
        rows = d[(d.index // 16 == r) & (d.regional_host.str.upper() == "Y")]
        regional.append(rows.team.iloc[0] if len(rows) else None)
    return {"slots": d.team.tolist(),
            "seeds": [int(s) if s else None for s in d.seed],
            "region_names": [d.region.iloc[16 * r] for r in range(4)],
            "pod_host_pos": pod_host, "regional_hosts": regional, "semis": "adjacent"}


def conference_champions(season: str, teams: pd.DataFrame) -> dict[str, str]:
    """Each conference's automatic bid: the winner where it has been decided
    (tournament/auto_bids_<season>.csv), otherwise the projected regular-season
    champion."""
    teams = teams[teams.conference != INDEPENDENT]
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
    champs = {c: g.team.iloc[0] for c, g in t.dropna(subset=["conf_pct"]).groupby("conference")}
    champs.update({c: x for c, x in auto_bids(season).items() if x in set(teams.team)})
    return champs


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
    official_error = None
    try:
        ob = official_bracket(season)
    except BracketError as e:
        ob, official_error = None, str(e)
    if ob:
        ranked = t.sort_values("rpi", ascending=False).team.tolist()
        fields["official"] = dict(ob, order=ranked,
                                  pool=[x for x in ranked if x not in ob["slots"]])

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
            "n_auto": len(auto), "n_clinched": len(auto_bids(season)),
            "official_error": official_error}
