"""Backtest the tournament simulation on 2023-2025, from the same point in the season.

THE QUESTION
------------
analytics/tournament_sim.py forecasts the NCAA field and every round from 2026 data
through Oct 24. How good would the same forecast have been, made at the same point, in
seasons whose answers are known?

SAME POINT IN THE SEASON
------------------------
Oct 24, 2026 is 36 days before Selection Sunday (Nov 29). Each backtest uses data
through 36 days before that year's Selection Sunday: Oct 21, 2023, Oct 26, 2024 and
Oct 25, 2025. That leaves about 72% of the regular season played in every year, 2026
included, and lands on the same weekday each time.

WHAT EACH RUN KNOWS
-------------------
- Results through the cutoff, from app_data/matches.parquet, the same table the live
  run reads, with the same gaps (2-3% of matches in 2023-24, 7% in 2025, most of it
  the WCC).
- Elo and the ridge as they stood at the cutoff.
- The three predictor coefficients refitted on seasons before the one tested (2023 is
  fitted on 2022 alone), so no coefficient has seen the season it forecasts.
- The rest of the regular season as it was actually scheduled, from the ncaavolleyballr
  team-match file. Conference tournaments are left out, as they are from the live run,
  which cannot know their pairings. Matches against non-Division I teams are left out;
  they move nothing but a little Elo.

THE ANSWERS
-----------
The real fields, seeds, hosts and results come from the same team-match files, whose
NCAA tournament rows are labelled and carry the regional seed. Each team's round is
its number of tournament wins. 2025's seed labels are unreliable in rounds one and
two, so 2025 seeds are read from the regional rounds only and the four 1-seeds were
checked against the NCAA's announcement.

Usage:
    python3 analytics/tournament_backtest.py --sims 5000      # all three seasons
    python3 analytics/tournament_backtest.py --season 2024 --sims 500
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analytics"))
from app import data as D          # noqa: E402
import matchup_model as MM         # noqa: E402
import tournament_sim as TS        # noqa: E402

CSV = ROOT / "data" / "ncaavolleyballr" / "data-csv" / "wvb_teammatch_div1_{}.csv"
SELECTION = {"2023": "2023-11-26", "2024": "2024-12-01", "2025": "2025-11-30",
             "2026": "2026-11-29"}
LEAD_DAYS = 36
SEASONS = ["2023", "2024", "2025"]
NCAA = re.compile(r"Division I (?:Women's )?Volleyball Championship")
POSTSEASON = re.compile(r"Tournament|Championship")
# rounds scored, as tournament_sim codes them: furthest round reached
ROUNDS = {4: "regional final", 5: "national semifinal", 6: "final", 7: "champion"}
SIZE = {4: 8, 5: 4, 6: 2, 7: 1}


# ---------------------------------------------------------------- the team-match file
def csv_rows(season: str) -> pd.DataFrame:
    """One row per team per match, opponent string parsed against known team names."""
    d = pd.read_csv(str(CSV).format(season), low_memory=False)
    d["day"] = pd.to_datetime(d.Date, format="%m/%d/%Y", errors="coerce")
    d = d.dropna(subset=["day", "Opponent", "Result"])
    # a team with no rows of its own (2025: San Diego, Arkansas St., Utah Valley) is
    # still a known name; team_seasons uses the same NCAA spellings in every season
    names = set(d.Team) | set(D.team_seasons().team)
    by_word: dict[str, list[str]] = {}
    for n in names:
        by_word.setdefault(n.split()[0], []).append(n)
    for v in by_word.values():
        v.sort(key=len, reverse=True)

    def parse(s: str):
        s = s.strip()
        away = s.startswith("@")
        s = re.sub(r"^@\s*", "", s)
        rank = re.match(r"^#(\d+)\s+", s)
        if rank:
            s = s[rank.end():]
        name = next((n for n in by_word.get(s.split()[0] if s else "", [])
                     if s == n or s.startswith(n + " ")), None)
        rest = s[len(name):] if name else s
        neutral = rest.lstrip().startswith("@")
        return name, int(rank.group(1)) if rank else None, away, neutral, rest

    p = pd.DataFrame([parse(x) for x in d.Opponent], index=d.index,
                     columns=["opp", "label", "away", "neutral", "tag"])
    d = pd.concat([d, p], axis=1)
    d["won"] = d.Result.str.startswith("W")
    d["ncaa"] = d.Opponent.str.contains(NCAA)
    d["post"] = d.tag.str.contains(POSTSEASON)
    d["home"] = np.where(d.away, d.opp, d.Team)
    return d


def matches_once(r: pd.DataFrame) -> pd.DataFrame:
    """Two rows per Division I pairing -> one, keyed on date and the unordered pair."""
    r = r.dropna(subset=["opp"]).copy()
    r["pair"] = [tuple(sorted(x)) for x in zip(r.Team, r.opp)]
    return r.drop_duplicates(["day", "pair"])


def remaining(season: str, cut: pd.Timestamp, sel: pd.Timestamp,
              rows: pd.DataFrame) -> pd.DataFrame:
    """The regular season left after the cutoff, as it was actually played."""
    r = rows[(rows.day > cut) & (rows.day < sel) & ~rows.post]
    r = matches_once(r)
    return pd.DataFrame({"season": season, "date": r.day.to_numpy(),
                         "home": r.home.to_numpy(),
                         "away": np.where(r.home == r.Team, r.opp, r.Team)})


def actual_tournament(rows: pd.DataFrame) -> pd.DataFrame:
    """The real field: round reached (1-7), host, regional seed where it is known."""
    t = rows[rows.ncaa & rows.opp.notna()]
    g = matches_once(t).sort_values("day")
    if len(g) != 63:
        raise ValueError(f"expected 63 tournament matches, found {len(g)}")
    teams = sorted(set(g.Team) | set(g.opp))
    winner = np.where(g.won, g.Team, g.opp)
    wins = pd.Series(winner).value_counts().reindex(teams, fill_value=0)
    if sorted(wins.value_counts().to_dict().items()) != [(0, 32), (1, 16), (2, 8),
                                                          (3, 4), (4, 2), (5, 1), (6, 1)]:
        raise ValueError("tournament results do not form a 64-team bracket")
    # a team's k-th tournament match is round k; hosts are home in rounds one and two
    order = pd.concat([pd.DataFrame({"team": g.Team, "day": g.day, "home": g.home,
                                     "neutral": g.neutral}),
                       pd.DataFrame({"team": g.opp, "day": g.day, "home": g.home,
                                     "neutral": g.neutral})])
    order["round"] = order.groupby("team").day.rank(method="first").astype(int)
    early = order[(order["round"] <= 2) & ~order.neutral]
    hosts = set(early.home)
    # seeds: the label is the opponent's regional seed. 2025 labels only hold up from
    # the regional rounds on, so read them there for every year, then fill from the
    # early rounds where the year's early labels agree with the late ones.
    lab = t.dropna(subset=["label"]).merge(order[["team", "day", "round"]],
                                           left_on=["opp", "day"], right_on=["team", "day"])
    late = lab[lab["round"] >= 3].groupby("opp").label.agg(lambda x: sorted(set(x)))
    early_l = lab[lab["round"] <= 2].groupby("opp").label.agg(lambda x: sorted(set(x)))
    agree = all(early_l.get(k) in (None, v) for k, v in late.items()) and \
        all(len(v) == 1 for v in early_l)
    seeds = {k: v[0] for k, v in (early_l.items() if agree else [])}
    seeds.update({k: v[0] for k, v in late.items() if len(v) == 1})
    return pd.DataFrame({"team": teams, "reached": (wins + 1).to_numpy(),
                         "host": [x in hosts for x in teams],
                         "seed": [seeds.get(x) for x in teams]}), agree


# ---------------------------------------------------------------- the forecast
def coef_before(season: str) -> tuple:
    """The predictor's three coefficients, fitted only on seasons before this one."""
    mp = pd.read_parquet(ROOT / "app_data" / "match_predictions.parquet")
    tr = mp[(mp.season > MM.BURN_IN) & (mp.season < season)]
    return tuple(MM.logit_fit(MM.design(tr, MM.SPECS["blend"]), tr.home_won.to_numpy()))


def forecast(season: str, sims: int, seed: int, rows: pd.DataFrame) -> tuple:
    sel = pd.Timestamp(SELECTION[season])
    cut = sel - pd.Timedelta(days=LEAD_DAYS)
    m = D.matches()
    m = m[m.match_date <= cut]
    rem = remaining(season, cut, sel, rows)
    coef = coef_before(season)
    I = TS.inputs(season, matches=m, sched=rem, coef=coef)
    runs, meta = TS.run(season, sims, seed, I=I)
    reg = rows[(rows.day < sel) & ~rows.post]
    meta.update({"cutoff": str(cut.date()), "selection": str(sel.date()),
                 "coef": [round(c, 4) for c in coef],
                 "share_played": round(float((reg.day <= cut).mean()), 3)})
    return runs, meta


# ---------------------------------------------------------------- scoring
def team_table(runs: pd.DataFrame, sims: int, actual: pd.DataFrame,
               d1: pd.DataFrame) -> pd.DataFrame:
    """Every Division I team x basis: forecast probabilities beside what happened."""
    s = TS.summarise(runs, sims)
    out = []
    for basis in ("committee", "power"):
        x = d1.merge(s[s.basis == basis].drop(columns="basis"), on="team", how="left")
        x = x.merge(actual, on="team", how="left")
        x["basis"] = basis
        out.append(x)
    t = pd.concat(out, ignore_index=True)
    p = [c for c in t.columns if c.startswith("p_")]
    t[p] = t[p].fillna(0.0)
    t["in_field"] = t.reached.notna()
    t["reached"] = t.reached.fillna(0).astype(int)
    t["host"] = t.host.fillna(False).astype(bool)
    return t


PCOL = {4: "p_regional_final", 5: "p_national_semifinal", 6: "p_final", 7: "p_champion"}


def score_season(t: pd.DataFrame) -> dict:
    """Headline numbers for one season and one basis."""
    out = {}
    field = t[t.in_field]
    top = t.nlargest(64, "p_field")
    out["field_hits"] = int(top.in_field.sum())
    # field teams the data cannot see at all (2025's missing leagues) cannot be picked
    out["field_invisible"] = sorted(field[~field.visible].team)
    out["field_mean_p"] = round(float(field.p_field.mean()), 3)
    out["field_missed"] = [(r.team, round(r.p_field, 2))
                           for r in field.sort_values("p_field").itertuples()
                           if r.team not in set(top.team)]
    out["field_wrong"] = [(r.team, round(r.p_field, 2))
                          for r in top.sort_values("p_field").itertuples()
                          if not r.in_field]
    # leagues that sent one team: the bid is a conference-title question
    n_bids = field.groupby("conference").size()
    seen = set(field[field.visible].conference)
    one = n_bids[(n_bids == 1) & n_bids.index.isin(seen)].index
    pick = t[t.conference.isin(one)].sort_values("p_auto", ascending=False) \
        .groupby("conference").head(1)
    out["one_bid_leagues"] = int(len(one))
    out["one_bid_right"] = int(pick.in_field.sum())
    multi = field[~field.conference.isin(one) & field.visible]
    out["multi_bid_teams"] = int(len(multi))
    out["multi_bid_hits"] = int(multi.team.isin(top.team).sum())
    out["host_hits"] = int(t.nlargest(16, "p_host").host.sum())
    ones = set(t[t.seed == 1].team)
    out["one_seed_hits"] = int(t.nlargest(4, "p_1seed").team.isin(ones).sum()) \
        if len(ones) == 4 else None
    for k, name in ROUNDS.items():
        n, col = SIZE[k], PCOL[k]
        got = t[t.reached >= k]
        picks = t.nlargest(n, col)
        y = (t.reached >= k).astype(float)
        brier = float(((t[col] - y) ** 2).sum())
        # the hindsight baseline: the real 64 known, each given the same chance
        base = float(((np.where(t.in_field, n / 64, 0.0) - y) ** 2).sum())
        out[name] = {"hits": int(picks.team.isin(got.team).sum()), "of": n,
                     "invisible": sorted(got[~got.visible].team),
                     "picked": picks.team.tolist(), "actual": got.team.tolist(),
                     "p_actual": [round(float(v), 3) for v in got[col]],
                     "mean_p_actual": round(float(got[col].mean()), 3),
                     "brier_skill_vs_uniform": round(1 - brier / base, 3)}
    champ = t[t.reached == 7].iloc[0]
    out["champion"]["rank"] = int((t.p_champion > champ.p_champion).sum() + 1)
    # title odds once in the Final Four, for the four who got there
    ff = t[t.reached >= 5]
    cond = (ff.p_champion / ff.p_national_semifinal.where(ff.p_national_semifinal > 0))
    out["title_given_ff"] = {r.team: round(float(c), 3) if pd.notna(c) else None
                             for r, c in zip(ff.itertuples(), cond)}
    out["title_given_ff_sum"] = round(float(cond.fillna(0).sum()), 3)
    return out


FOCUS = "Nebraska"
FINISH = {1: "first round", 2: "second round", 3: "regional semifinal",
          4: "regional final", 5: "national semifinal", 6: "final", 7: "champion"}


def focus_team(t: pd.DataFrame, rows: pd.DataFrame, team: str = FOCUS) -> dict:
    """One team's October odds beside its December: seed, each round, who ended it."""
    me = t[t.team == team].iloc[0]
    out = {c: round(float(me[c]), 3) for c in ["p_field", "p_host", "p_1seed"] + list(PCOL.values())}
    out["title_rank"] = int((t.p_champion > me.p_champion).sum() + 1)
    out["seed"] = None if pd.isna(me.seed) else int(me.seed)
    out["finish"] = FINISH.get(int(me.reached), "not in the field")
    games = rows[rows.ncaa & (rows.Team == team)].sort_values("day")
    if len(games) and not games.iloc[-1].won:
        last = games.iloc[-1]
        foe = t[t.team == last.opp].iloc[0]
        out["lost_to"] = {"team": last.opp, "result": last.Result,
                          "seed": None if pd.isna(foe.seed) else int(foe.seed),
                          "p_champion": round(float(foe.p_champion), 3),
                          "p_regional_final": round(float(foe.p_regional_final), 3)}
    return out


def chalk(t: pd.DataFrame) -> dict:
    """What the committee's own seeds, known only on Selection Sunday, got right."""
    out = {}
    for k, seeds in ((4, (1, 2)), (5, (1,))):
        s = t[t.seed.isin(seeds)]
        out[ROUNDS[k]] = (int((s.reached >= k).sum()), int(len(s)))
    return out


def title_check(tables: list[pd.DataFrame], draws: int = 100_000) -> dict:
    """Were the real champions given less than a calibrated forecast would give them?

    If the title odds were right, the champion each year is a draw from them. Draw it
    that way many times and count how often the three champions' odds come out as low
    as the real ones did."""
    rng = np.random.default_rng(0)
    obs, sim, out = 0.0, np.zeros(draws), {}
    for s, t in zip(SEASONS, tables):
        t = t[t.p_champion > 0]
        p = t.p_champion.to_numpy() / t.p_champion.sum()
        champ = t[t.reached == 7]
        got = float(champ.p_champion.iloc[0]) if len(champ) else 0.0
        out[s] = {"champion_odds": round(got, 3),
                  "calibrated_expectation": round(float((p ** 2).sum()), 3)}
        obs += np.log(max(got, 1e-4))
        sim += np.log(p[rng.choice(len(p), size=draws, p=p)])
    out["share_of_calibrated_worlds_as_bad"] = round(float((sim <= obs).mean()), 3)
    return out


def calibration(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Pooled over seasons and the four rounds: forecast bins against what happened."""
    rows = []
    for t in tables:
        for k, col in PCOL.items():
            rows.append(pd.DataFrame({"p": t[col], "y": (t.reached >= k).astype(int)}))
    d = pd.concat(rows)
    d = d[d.p > 0]
    bins = [0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.70, 1.0001]
    d["bin"] = pd.cut(d.p, bins, right=False)
    g = d.groupby("bin", observed=True).agg(n=("y", "size"), forecast=("p", "sum"),
                                            happened=("y", "sum"))
    g["forecast"] = g.forecast.round(1)
    return g.reset_index()


# ---------------------------------------------------------------- report
def report(results: dict, cal: dict, out: Path) -> str:
    L = ["# Tournament forecast backtest, 2023-2025", "",
         f"Each season forecast {LEAD_DAYS} days before Selection Sunday, the same point "
         "as the 2026 forecast (Oct 24). Same simulation, same settings; coefficients "
         "fitted only on earlier seasons.", ""]
    # the focus team first, with this year's live forecast beside the three tested
    live = ROOT / "analysis" / "tournament_sim_2026_summary.csv"
    now = None
    if live.exists():
        s26 = pd.read_csv(live)
        s26 = s26[(s26.basis == "committee") & (s26.team == FOCUS)]
        now = s26.iloc[0] if len(s26) else None
    F = {s: results[s]["focus"] for s in SEASONS}
    head = SEASONS + (["2026 (live)"] if now is not None else [])
    L += [f"## {FOCUS} (committee basis)", "",
          "| October odds | " + " | ".join(head) + " |", "|---|" + "---|" * len(head)]
    for label, col in (("1-seed", "p_1seed"), ("Regional final", "p_regional_final"),
                       ("Final Four", "p_national_semifinal"), ("Final", "p_final"),
                       ("Title", "p_champion")):
        cells = [f"{F[s][col]:.0%}" for s in SEASONS]
        if now is not None:
            cells.append(f"{now[col]:.0%}")
        L.append(f"| {label} | " + " | ".join(cells) + " |")
    L.append("| Title-odds rank | " + " | ".join(str(F[s]["title_rank"]) for s in SEASONS)
             + (" | 1 |" if now is not None else " |"))
    L.append("| **What happened** | " + " | ".join(
        f"{F[s]['seed']}-seed; {F[s]['finish']}"
        + (f", lost {F[s]['lost_to']['result'][2:]} to {F[s]['lost_to']['team']}"
           f" ({F[s]['lost_to']['p_champion']:.0%} title odds)" if "lost_to" in F[s] else "")
        for s in SEASONS) + (" | — |" if now is not None else " |"))
    exp = {name: sum(F[s][PCOL[k]] for s in SEASONS) for k, name in ROUNDS.items()}
    got = {name: sum(1 for s in SEASONS if F[s]["finish"] in
                     [FINISH[j] for j in range(k, 8)]) for k, name in ROUNDS.items()}
    L += ["", "Expected against actual, three seasons: " + "; ".join(
        f"{name} {exp[name]:.1f} vs {got[name]}" for name in ROUNDS.values()) + ".", ""]
    for basis in ("committee", "power"):
        L += [f"## {basis.title()} seeding", "",
              "| | " + " | ".join(SEASONS) + " | Total |", "|---|" + "---|" * 4]

        def row(label, f):
            vals = [f(results[s][basis]) for s in SEASONS]
            nums = [v for v in vals if isinstance(v, tuple)]
            tot = (sum(a for a, _ in nums), sum(b for _, b in nums)) if nums else ""
            cell = lambda v: f"{v[0]}/{v[1]}" if isinstance(v, tuple) else str(v)
            L.append(f"| {label} | " + " | ".join(cell(v) for v in vals) +
                     f" | {cell(tot) if tot else ''} |")
        row("Field (top 64 by odds)", lambda r: (r["field_hits"], 64))
        row("  one-bid leagues: right team", lambda r: (r["one_bid_right"], r["one_bid_leagues"]))
        row("  multi-bid leagues", lambda r: (r["multi_bid_hits"], r["multi_bid_teams"]))
        row("Hosts (top 16)", lambda r: (r["host_hits"], 16))
        row("1-seeds", lambda r: (r["one_seed_hits"], 4) if r["one_seed_hits"] is not None else "n/a")
        for name in ROUNDS.values():
            row(f"{name.title()}: top picks right", lambda r, n=name: (r[n]["hits"], r[n]["of"]))
        for name in ROUNDS.values():
            row(f"{name.title()}: mean odds given to those who made it",
                lambda r, n=name: f"{r[n]['mean_p_actual']:.0%}")
        for name in ROUNDS.values():
            row(f"{name.title()}: Brier skill vs uniform",
                lambda r, n=name: f"{r[n]['brier_skill_vs_uniform']:+.2f}")
        row("Champion: rank in title odds", lambda r: r["champion"]["rank"])
        L.append("")
    L += ["## The committee's own seeds (known only on Selection Sunday)", "",
          "| | " + " | ".join(SEASONS) + " |", "|---|---|---|---|"]
    for name in ("regional final", "national semifinal"):
        lab = "1- and 2-seeds in the regional final" if name == "regional final" \
            else "1-seeds in the Final Four"
        L.append(f"| {lab} | " + " | ".join(
            f"{results[s]['chalk'][name][0]}/{results[s]['chalk'][name][1]}"
            for s in SEASONS) + " |")
    tc = cal["title"]
    L += ["", "## Title odds against a calibrated forecast (committee basis)", "",
          "| | " + " | ".join(SEASONS) + " |", "|---|---|---|---|",
          "| Odds given to the real champion | " + " | ".join(
              f"{tc[s]['champion_odds']:.1%}" for s in SEASONS) + " |",
          "| Odds a calibrated forecast gives its winner, on average | " + " | ".join(
              f"{tc[s]['calibrated_expectation']:.1%}" for s in SEASONS) + " |", "",
          f"Champions this unlikely, three years running, happen in "
          f"{tc['share_of_calibrated_worlds_as_bad']:.0%} of worlds where the odds are "
          "right."]
    L += ["", "## Calibration, pooled (committee basis, all four rounds)", "",
          "| Forecast | Team-rounds | Expected | Happened |", "|---|---|---|---|"]
    for r in cal["committee"].itertuples():
        L.append(f"| {r.bin.left:.0%}-{min(r.bin.right, 1):.0%} | {r.n} | "
                 f"{r.forecast} | {r.happened} |")
    L += ["", "## Season detail (committee basis)", ""]
    for s in SEASONS:
        r = results[s]["committee"]
        m = results[s]["meta"]
        L += [f"### {s}  (data through {m['cutoff']}, {m['share_played']:.0%} of the "
              "regular season played)", "",
              f"- Missed field teams: {', '.join(f'{a} ({b:.0%})' for a, b in r['field_missed'])}",
              f"- Projected in, stayed out: {', '.join(f'{a} ({b:.0%})' for a, b in r['field_wrong'])}"]
        for name in ROUNDS.values():
            x = r[name]
            L.append(f"- {name.title()}: picked {', '.join(x['picked'])}; actual "
                     + ", ".join(f"{a} ({p:.0%})" for a, p in zip(x["actual"], x["p_actual"])))
        L.append("- Title odds once in the Final Four: " + ", ".join(
            f"{a} {p:.0%}" if p is not None else f"{a} n/a"
            for a, p in r["title_given_ff"].items())
            + f" (sum {r['title_given_ff_sum']:.2f}; one of them won)")
        L.append("")
    text = "\n".join(L)
    out.write_text(text)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", action="append")
    ap.add_argument("--sims", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out-dir", type=Path, default=Path("analysis"))
    args = ap.parse_args()
    seasons = args.season or SEASONS
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = D.team_seasons()
    results, tables = {}, {}
    for season in seasons:
        rows = csv_rows(season)
        actual, early_ok = actual_tournament(rows)
        d1 = ts[(ts.season == season) & ts.conference.notna() & (ts.conference != "")][
            ["team", "conference"]].assign(visible=True)
        # field teams with no data this season keep their last known conference
        missing = sorted(set(actual.team) - set(d1.team))
        last = ts[ts.season < season].sort_values("season").groupby("team").conference.last()
        d1 = pd.concat([d1, pd.DataFrame({"team": missing,
                                          "conference": [last.get(x) for x in missing],
                                          "visible": False})], ignore_index=True)
        if missing:
            print(f"  {season}: {len(missing)} field teams have no data: {missing}")
        print(f"{season}: forecasting from {LEAD_DAYS} days out, {args.sims:,} runs",
              flush=True)
        runs, meta = forecast(season, args.sims, args.seed, rows)
        meta["early_round_seed_labels_used"] = bool(early_ok)
        t = team_table(runs, args.sims, actual, d1)
        t.to_csv(args.out_dir / f"tournament_backtest_{season}_teams.csv", index=False)
        tables[season] = t
        results[season] = {b: score_season(t[t.basis == b]) for b in ("committee", "power")}
        results[season]["chalk"] = chalk(t[t.basis == "committee"])
        results[season]["focus"] = focus_team(t[t.basis == "committee"], rows)
        results[season]["meta"] = meta
        print(json.dumps({k: v for k, v in results[season]["committee"].items()
                          if not isinstance(v, (dict, list))}), flush=True)
    if set(seasons) != set(SEASONS):
        return
    cal = {b: calibration([tables[s][tables[s].basis == b] for s in SEASONS])
           for b in ("committee", "power")}
    cal["title"] = title_check([tables[s][tables[s].basis == "committee"] for s in SEASONS])
    results["title_check"] = cal["title"]
    (args.out_dir / "tournament_backtest.json").write_text(
        json.dumps(results, indent=1, default=str))
    print(report(results, cal, args.out_dir / "tournament_backtest.md"))


if __name__ == "__main__":
    main()
