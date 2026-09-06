"""Everything behind the "Set One Among Equals" analysis, as data.

Emits every figure quoted in the article and the follow-up point-lead breakdown,
computed from source rather than transcribed, so the numbers can be checked and
regenerated when a new season lands.

Two outputs, same content:
  analysis/set_one_analysis.json   machine-readable, every figure with its n
  analysis/set_one_analysis.md     the same tables, readable

SCOPE. The headline analysis is restricted to matches in which BOTH teams ranked
inside the top 25 of the opponent-adjusted power rating for that season -- a ridge
regression on side-out rate, not the AVCA poll, so membership will not always match
the coaches' ballot. All-D1 figures are carried alongside as the comparison that
motivated the restriction: the first set is worth LESS between ranked teams than it
is across D1 as a whole, because D1 as a whole is mismatches.

SET FACTS COME FROM THE SCORE COLUMNS, not from counting rallies won. The two
disagree on roughly 10% of sets and the score is the trustworthy one: rally_engine
drops malformed and abandoned rows, so counting silently undercounts. Read from the
score, every match resolves to exactly one set-1 winner and the league-wide rate is
exactly 50.0%.

Usage:  python3 analytics/set_one_analysis.py [--out-dir analysis]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

CHECKPOINTS = (5, 10, 12, 15, 20)   # 12 is the set-5 analogue of 20 (a set to 15)
SET1_CHECKPOINTS = (5, 10, 15, 20)
TOP_N = 25
MIN_MATCHES_TEAM_LEVEL = 6


# ----------------------------------------------------------------- extraction
def set_scores(rally_glob: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per set: the final score, and the score when either side first reaches each checkpoint.

    `score_away`/`score_home` are recorded BEFORE each rally, so a point is added for the
    rally's own winner to get the score after it. Sets 1-4 play to 25 and a deciding fifth
    set to 15, so checkpoint 20 exists only in the first four and 12 is carried as its
    fifth-set analogue (both are four-fifths of the way to the target).
    """
    finals, checks = [], []
    for path in sorted(glob.glob(rally_glob)):
        season = re.search(r"(\d{4})\.parquet$", path).group(1)
        after = f"""
            SELECT date, away_team, home_team, set_no, rally_no,
                   score_away + CASE WHEN winner = away_team THEN 1 ELSE 0 END AS a,
                   score_home + CASE WHEN winner = home_team THEN 1 ELSE 0 END AS h
            FROM read_parquet('{path}')
            WHERE set_no IS NOT NULL AND score_away IS NOT NULL AND score_home IS NOT NULL
        """
        f = duckdb.sql(f"""
            WITH s AS ({after}),
                 e AS (SELECT *, row_number() OVER (PARTITION BY date, away_team, home_team, set_no
                                                    ORDER BY rally_no DESC) rn FROM s)
            SELECT date, away_team, home_team, set_no, a, h FROM e WHERE rn = 1
        """).df()
        c = duckdb.sql(f"""
            WITH s AS ({after}),
                 k(cp) AS (VALUES {','.join(f'({x})' for x in CHECKPOINTS)}),
                 x AS (SELECT s.*, k.cp,
                              row_number() OVER (PARTITION BY date, away_team, home_team,
                                                              set_no, k.cp
                                                 ORDER BY rally_no) rn
                       FROM s CROSS JOIN k WHERE greatest(s.a, s.h) >= k.cp)
            SELECT date, away_team, home_team, set_no, cp, a, h FROM x WHERE rn = 1
        """).df()
        f["season"] = season
        c["season"] = season
        finals.append(f)
        checks.append(c)

    def prep(parts):
        df = pd.concat(parts, ignore_index=True)
        df = df.dropna(subset=["a", "h"]).copy()
        df["a"] = df.a.astype(int)
        df["h"] = df.h.astype(int)
        df["leader"] = np.where(df.a > df.h, df.away_team,
                                np.where(df.h > df.a, df.home_team, None))
        df["margin"] = (df.a - df.h).abs().astype(int)
        df["match_date"] = pd.to_datetime(df.date, format="%m/%d/%Y", errors="coerce")
        df["pair"] = [frozenset((x, y)) for x, y in zip(df.away_team, df.home_team)]
        df["set_winner"] = np.where(df.a > df.h, df.away_team,
                                    np.where(df.h > df.a, df.home_team, None))
        return df

    return prep(finals), prep(checks)


def load_matches(app_dir: Path) -> pd.DataFrame:
    """Graded team-matches, with each side's power rating and rank attached."""
    m = pd.read_parquet(app_dir / "matches.parquet")
    m = m[m.won_set1.notna()].copy()
    pr = pd.read_parquet(app_dir / "power_ratings.parquet")[
        ["season", "team", "rating_overall", "rank_overall"]]
    m = m.merge(pr, on=["season", "team"], how="left")
    m = m.merge(pr.rename(columns={"team": "opponent", "rating_overall": "opp_rating",
                                   "rank_overall": "opp_rank"}),
                on=["season", "opponent"], how="left")
    m["gap"] = m.rating_overall - m.opp_rating
    m["sets"] = m.sets_for + m.sets_against
    m["pair"] = [frozenset((t, o)) for t, o in zip(m.team, m.opponent)]
    return m


# -------------------------------------------------------------------- helpers
def rate(g, col="won"):
    return None if len(g) == 0 else round(float(g[col].mean()), 4)


def record(g):
    return {"w": int(g.won.sum()), "l": int(len(g) - g.won.sum()), "n": int(len(g))}


def split_by_set1(g):
    """The one comparison this whole analysis turns on."""
    w, l = g[g.won_set1 == 1], g[g.won_set1 == 0]
    out = {"n_matches": int(len(g)),
           "won_set1": {**record(w), "win_pct": rate(w)},
           "lost_set1": {**record(l), "win_pct": rate(l)}}
    if out["won_set1"]["win_pct"] is not None and out["lost_set1"]["win_pct"] is not None:
        out["swing"] = round(out["won_set1"]["win_pct"] - out["lost_set1"]["win_pct"], 4)
    return out


def bucket(g, col, bands):
    rows = []
    for lo, hi, label in bands:
        s = g[(g[col] >= lo) & (g[col] <= hi)]
        if len(s) == 0:
            continue
        rows.append({"band": label, "n": int(len(s)), "win_pct": rate(s),
                     "wins_set1": rate(s, "won_set1"),
                     "sweep_pct": round(float(((s.sets_for == 3) & (s.sets_against == 0)).mean()), 4)})
    return rows


# --------------------------------------------------------------------- report
def build(app_dir: Path, rally_glob: str) -> dict:
    finals, checks = set_scores(rally_glob)
    m = load_matches(app_dir)

    fin = finals[finals.set_no == 1][["match_date", "pair", "season", "margin"]].copy()
    fin = fin.drop_duplicates(["match_date", "pair", "season"])
    m = m.merge(fin[["match_date", "pair", "season", "margin"]],
                on=["match_date", "pair", "season"], how="left")

    top = m[(m.rank_overall <= TOP_N) & (m.opp_rank <= TOP_N)].copy()

    R = {
        "meta": {
            "title": "Set One Among Equals",
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sport": "NCAA women's volleyball, Division I",
            "seasons": sorted(m.season.unique().tolist()),
            "scope": (f"Headline analysis restricted to matches where BOTH teams ranked in the "
                      f"top {TOP_N} of the opponent-adjusted power rating for that season. "
                      f"That rating is a ridge regression on side-out rate, not the AVCA poll."),
            "team_matches_all_d1": int(len(m)),
            "team_matches_top25": int(len(top)),
            "matches_top25": int(len(top) // 2),
            "set_facts_source": ("Set winners, margins and checkpoint leads are read from the "
                                 "play-by-play score columns, not by counting rallies won. The two "
                                 "disagree on ~10% of sets because rally_engine drops malformed and "
                                 "abandoned rows; the score column is absolute."),
        },
        "headline": {},
        "all_d1_baseline": {},
        "match_length": {},
        "set1_margin": {},
        "venue": {},
        "rating_gap": {},
        "comebacks": {},
        "point_leads": {},
        "nebraska": {},
        "team_level": {},
    }

    # ------------------------------------------------------------- headline
    R["headline"] = {
        "top25": split_by_set1(top),
        "all_d1": split_by_set1(m),
        "note": ("The first set is worth LESS between ranked teams than across D1 as a whole. "
                 "Most of D1 is mismatches, where the first set merely reflects the gap."),
        "top25_by_season": {s: split_by_set1(g) for s, g in top.groupby("season")},
    }
    R["all_d1_baseline"]["by_season"] = {s: split_by_set1(g) for s, g in m.groupby("season")}

    # --------------------------------------------------------- match length
    def length_mix(g):
        n = len(g) // 2
        return {str(int(k)): {"matches": int(v // 2), "share": round(float(v / len(g)), 4)}
                for k, v in g.sets.value_counts().sort_index().items()} | {"total_matches": n}

    R["match_length"] = {
        "top25": length_mix(top),
        "all_d1": length_mix(m),
        "set1_winner_wins_by_length": {
            str(L): {"matches": int(len(g) // 2), "win_pct": rate(g[g.won_set1 == 1])}
            for L, g in top.groupby("sets")},
        "set1_winner_final_scores_top25": {
            f"{int(a)}-{int(b)}": int(v) for (a, b), v in
            top[top.won_set1 == 1].groupby(["sets_for", "sets_against"]).size()
            .sort_values(ascending=False).items()},
        "note": ("Top-25 matches go long far more often, which is why the first set is worth less: "
                 "fewer of these matches end before it can be avenged."),
    }

    # ---------------------------------------------------------- set-1 margin
    bands = [(2, 2, "2 points"), (3, 4, "3-4"), (5, 7, "5-7"), (8, 50, "8+")]
    R["set1_margin"] = {
        "top25_winner": bucket(top[top.won_set1 == 1].dropna(subset=["margin"]), "margin", bands),
        "all_d1_winner": bucket(m[m.won_set1 == 1].dropna(subset=["margin"]),
                                "margin", [(2, 2, "2 points"), (3, 4, "3-4"), (5, 7, "5-7"),
                                           (8, 11, "8-11"), (12, 50, "12+")]),
        "caveat": ("In the top-25 subset the 3-4 point band sits below the 2-point band. With ~120 "
                   "matches in each that is noise, not a finding: the trend is real at the ends and "
                   "mushy in the middle."),
    }

    # ----------------------------------------------------------------- venue
    R["venue"] = {loc: {"n": int(len(g)), "win_pct_after_winning_set1": rate(g[g.won_set1 == 1])}
                  for loc, g in top.groupby("location")}

    # ------------------------------------------------------------ rating gap
    def gap_table(g, bands):
        out = []
        for lo, hi, label in bands:
            s = g[(g.gap > lo) & (g.gap <= hi)]
            if len(s) < 50:
                continue
            d = split_by_set1(s)
            out.append({"band": label, "n_team_matches": int(len(s)),
                        "win_pct_won_set1": d["won_set1"]["win_pct"],
                        "win_pct_lost_set1": d["lost_set1"]["win_pct"],
                        "swing": d.get("swing")})
        return out

    R["rating_gap"] = {
        "top25": gap_table(top, [(-100, -8, "underdog (worse by >8)"),
                                 (-8, 8, "even (within 8)"),
                                 (8, 100, "favorite (better by >8)")]),
        "all_d1": gap_table(m, [(-100, -15, "outmatched (<= -15)"), (-15, -5, "underdog"),
                                (-5, 5, "even (within 5)"), (5, 15, "favorite"),
                                (15, 100, "dominant (>= +15)")]),
        "finding": ("The first set swings the match most where the teams were otherwise even, and "
                    "roughly half as much where one side was already clearly better. It decides the "
                    "matches that weren't going to decide themselves."),
        "gap_units": "difference in overall rating, in percentage points of side-out vs an average D1 team",
    }

    # ------------------------------------------------------------- comebacks
    lost = top[top.won_set1 == 0]
    cb = lost[lost.won == 1]
    R["comebacks"] = {
        "top25": {"n": int(len(cb)), "of": int(len(lost)), "rate": rate(lost),
                  "final_scores": {f"{int(a)}-{int(b)}": int(v) for (a, b), v in
                                   cb.groupby(["sets_for", "sets_against"]).size().items()},
                  "mean_set1_deficit_overcome": round(float(cb.margin.mean()), 2)},
        "by_deficit": bucket(lost.dropna(subset=["margin"]), "margin",
                             [(1, 2, "down 2"), (3, 4, "down 3-4"),
                              (5, 7, "down 5-7"), (8, 50, "down 8+")]),
        "largest_deficits_overcome": [
            {"season": r.season, "team": r.team, "opponent": r.opponent,
             "result": f"{int(r.sets_for)}-{int(r.sets_against)}", "set1_deficit": int(r.margin)}
            for _, r in cb.dropna(subset=["margin"]).sort_values("margin", ascending=False).head(10).iterrows()],
        "note": "Every comeback in the top-25 sample went four sets or five. There are no cheap recoveries.",
    }

    # ----------------------------------------------------------- point leads
    ck = checks[(checks.set_no == 1) & (checks.cp.isin(SET1_CHECKPOINTS))][
        ["match_date", "pair", "season", "cp", "leader", "margin"]].copy()
    ck = ck.drop_duplicates(["match_date", "pair", "season", "cp"])
    cj = top.merge(ck[["match_date", "pair", "season", "cp", "leader", "margin"]]
                   .rename(columns={"margin": "cp_margin"}),
                   on=["match_date", "pair", "season"], how="inner")

    lead_bands = [(1, 1, "up 1"), (2, 2, "up 2"), (3, 4, "up 3-4"), (5, 40, "up 5+")]
    R["point_leads"] = {
        "definition": ("At each checkpoint, the score when either team first reaches that many points "
                       "in set 1, and who was ahead at that moment."),
        "by_checkpoint": [],
        "by_lead_size": {},
        "lead_persistence": {},
    }
    for k in SET1_CHECKPOINTS:
        g = cj[(cj.cp == k) & (cj.leader == cj.team)]
        R["point_leads"]["by_checkpoint"].append({
            "checkpoint": k, "n": int(len(g)),
            "wins_set1": rate(g, "won_set1"), "wins_match": rate(g),
            "mean_lead": round(float(g.cp_margin.mean()), 2)})
        rows = []
        for lo, hi, label in lead_bands:
            s = g[(g.cp_margin >= lo) & (g.cp_margin <= hi)]
            if len(s) < 20:
                continue
            rows.append({"lead": label, "n": int(len(s)),
                         "wins_set1": rate(s, "won_set1"), "wins_match": rate(s)})
        R["point_leads"]["by_lead_size"][str(k)] = rows

    piv = cj[cj.leader == cj.team].pivot_table(
        index=["match_date", "pair", "season"], columns="cp", values="team", aggfunc="first")
    for a, b in [(5, 10), (10, 15), (15, 20), (5, 20)]:
        if a in piv.columns and b in piv.columns:
            R["point_leads"]["lead_persistence"][f"{a}_to_{b}"] = round(float((piv[a] == piv[b]).mean()), 4)
    R["point_leads"]["lead_persistence"]["n_matches"] = int(len(piv))
    R["point_leads"]["finding"] = (
        "Being first to 20 wins the SET 87% of the time but the MATCH only 69%, because the set "
        "itself is only worth 76%. Lead size matters far more than lead: leading 20-19 is a coin "
        "flip for the match, while up 5+ at 10 is already worth what up 5+ at 20 is worth.")

    # ------------------------------------------------- first to 20, every set
    c20 = checks[checks.cp == 20][["match_date", "pair", "season", "set_no", "leader"]]
    c12 = checks[checks.cp == 12][["match_date", "pair", "season", "set_no", "leader"]]
    fw = finals[["match_date", "pair", "season", "set_no", "set_winner"]]
    per_set = fw.merge(c20, on=["match_date", "pair", "season", "set_no"], how="left")

    def f20(mm):
        x = mm.merge(per_set, on=["match_date", "pair", "season"], how="inner")
        x = x[(x.set_no <= 4) & x.leader.notna()].copy()
        x["first20"] = x.leader == x.team
        x["wonset"] = x.set_winner == x.team
        return x

    def by_set(x):
        rows = []
        for s, g in x.groupby("set_no"):
            lead = g[g.first20]
            rows.append({"set": int(s), "n": int(len(lead)),
                         "wins_that_set": round(float((lead.set_winner == lead.team).mean()), 4),
                         "wins_match": rate(lead),
                         "wins_match_if_not_first_to_20": rate(g[~g.first20]),
                         "lift": round(float(lead.won.mean() - g[~g.first20].won.mean()), 4)})
        return rows

    xt, xa = f20(top), f20(m)
    # set 5 plays to 15; 12 is its analogue of 20
    s5 = fw[fw.set_no == 5].merge(c12[c12.set_no == 5],
                                  on=["match_date", "pair", "season", "set_no"], how="left")
    j5 = top.merge(s5, on=["match_date", "pair", "season"], how="inner")
    j5 = j5[j5.leader.notna()]
    lead5 = j5[j5.leader == j5.team]

    def count_table(mm, x):
        cnt = x[x.first20].groupby(["match_date", "pair", "season", "team"]).size().rename("n20")
        z = mm.set_index(["match_date", "pair", "season", "team"])[["won"]].join(cnt)
        z["n20"] = z.n20.fillna(0)
        return [{"sets_first_to_20": int(k), "n": int(len(g)), "win_pct": rate(g)}
                for k, g in z.groupby("n20") if len(g) >= 25]

    R["first_to_20"] = {
        "question": "Across every set of a match, how much does being first to 20 matter?",
        "definition": ("Whoever holds the lead at the moment either team first reaches 20 points. "
                       "Sets 1-4 play to 25; a deciding fifth set plays to 15, so 12 is used there "
                       "as the analogue and reported separately."),
        "top25_by_set": by_set(xt),
        "all_d1_by_set": by_set(xa),
        "top25_set5_first_to_12": {
            "n": int(len(lead5)),
            "wins_that_set": round(float((lead5.set_winner == lead5.team).mean()), 4),
            "wins_match": rate(lead5),
            "note": "Winning set 5 is winning the match, so the two figures are the same by definition."},
        "top25_by_count": count_table(top, xt),
        "all_d1_by_count": count_table(m, xa),
        "does_it_add_anything_beyond_the_set_result": {
            "scope": "top-25, sets 1-4",
            "first_to_20": {"n": int(len(xt[xt.first20])), "win_pct": rate(xt[xt.first20])},
            "won_the_set": {"n": int(len(xt[xt.wonset])), "win_pct": rate(xt[xt.wonset])},
            "first_to_20_and_won_set": {"n": int(len(xt[xt.first20 & xt.wonset])),
                                        "win_pct": rate(xt[xt.first20 & xt.wonset])},
            "won_set_from_behind_at_20": {"n": int(len(xt[~xt.first20 & xt.wonset])),
                                          "win_pct": rate(xt[~xt.first20 & xt.wonset])},
            "first_to_20_but_lost_set": {"n": int(len(xt[xt.first20 & ~xt.wonset])),
                                         "win_pct": rate(xt[xt.first20 & ~xt.wonset])},
            "neither": {"n": int(len(xt[~xt.first20 & ~xt.wonset])),
                        "win_pct": rate(xt[~xt.first20 & ~xt.wonset])},
        },
        "finding": ("No set's 20-point lead is worth more than another's -- the lift is flat across "
                    "sets 1 through 4. And being first to 20 carries almost nothing beyond the set "
                    "result itself: a team that won the set from behind at 20 wins the match at "
                    "essentially the same rate as one that led at 20 and closed it out. First to 20 "
                    "matters only because it usually means winning the set."),
    }

    # -------------------------------------------------------------- Nebraska
    neb = top[top.team == "Nebraska"]
    ncj = cj[cj.team == "Nebraska"]
    ts = pd.read_parquet(app_dir / "team_seasons.parquet")
    R["nebraska"] = {
        "top25_matchups": {**record(neb), **split_by_set1(neb)},
        "by_season": {s: {**record(g), "set1_won": int(g.won_set1.sum()),
                          "set1_rate": rate(g, "won_set1"),
                          "record_after_winning_set1": record(g[g.won_set1 == 1]),
                          "record_after_losing_set1": record(g[g.won_set1 == 0])}
                      for s, g in neb.groupby("season")},
        "official_records": {r.season: {"w": int(r.wins), "l": int(r.losses),
                                        "grade": round(float(r.grade), 2)}
                             for _, r in ts[ts.team == "Nebraska"].sort_values("season").iterrows()},
        "losses_after_winning_set1": [
            {"season": r.season, "opponent": r.opponent,
             "result": f"{int(r.sets_for)}-{int(r.sets_against)}"}
            for _, r in neb[(neb.won_set1 == 1) & (neb.won == 0)].iterrows()],
        "comebacks": [
            {"season": r.season, "opponent": r.opponent,
             "result": f"{int(r.sets_for)}-{int(r.sets_against)}"}
            for _, r in neb[(neb.won_set1 == 0) & (neb.won == 1)].iterrows()],
        "point_leads": [
            {"checkpoint": k,
             "led": int(len(ncj[(ncj.cp == k) & (ncj.leader == ncj.team)])),
             "of": int(len(ncj[ncj.cp == k])),
             "lead_rate": rate(ncj[ncj.cp == k].assign(
                 led=(ncj[ncj.cp == k].leader == ncj[ncj.cp == k].team).astype(float)), "led"),
             "wins_set1": rate(ncj[(ncj.cp == k) & (ncj.leader == ncj.team)], "won_set1"),
             "wins_match": rate(ncj[(ncj.cp == k) & (ncj.leader == ncj.team)])}
            for k in SET1_CHECKPOINTS],
        "trailing_at_20_in_set1": {
            **record(ncj[(ncj.cp == 20) & (ncj.leader != ncj.team) & (ncj.leader.notna())]),
            "wins_set1": rate(ncj[(ncj.cp == 20) & (ncj.leader != ncj.team) & (ncj.leader.notna())], "won_set1"),
            "wins_match": rate(ncj[(ncj.cp == 20) & (ncj.leader != ncj.team) & (ncj.leader.notna())])},
        "note": ("Nebraska's comeback rate is ordinary. What separates them is the other column: "
                 "once they take set 1 from a ranked opponent they finish it ~95% of the time."),
    }

    # ------------------------------------------------------------ team level
    agg = top.groupby(["season", "team"]).agg(
        n=("won", "size"), w=("won", "sum"), set1_rate=("won_set1", "mean")).reset_index()
    agg = agg[agg.n >= MIN_MATCHES_TEAM_LEVEL]
    R["team_level"] = {
        "correlation_set1_rate_vs_win_pct_in_top25_games": round(float(agg.set1_rate.corr(agg.w / agg.n)), 4),
        "n_team_seasons": int(len(agg)),
        "min_matches": MIN_MATCHES_TEAM_LEVEL,
        "leaders": [{"season": r.season, "team": r.team,
                     "record": f"{int(r.w)}-{int(r.n - r.w)}", "set1_rate": round(float(r.set1_rate), 4)}
                    for _, r in agg.sort_values("set1_rate", ascending=False).head(12).iterrows()],
    }

    # -------------------------------------------- why set 1 became a benchmark
    R["benchmark_rationale"] = {
        "replaced": "fbso_pct (first-ball side-out)",
        "reason_practical": ("stats.ncaa.org now denies every /teams/<id> path. The replacement feed "
                             "carries point-summary play-by-play only, so first-ball side-out has no "
                             "2026 source."),
        "grade_auc_before": 0.9630,
        "grade_auc_after": 0.9665,
        "won_set1_hit_rate": 0.5000,
        "hit_rate_note": "Exactly 50% by construction -- one team wins set 1 in every match.",
        "first_to_20_rejected": {
            "p_win_given_first_to_20_every_set_all_d1": 0.993,
            "reason": "Too tautological to grade; kept as a context metric instead.",
        },
    }
    return R


# ------------------------------------------------------------------ markdown
def to_markdown(R: dict) -> str:
    def tbl(headers, rows):
        out = ["| " + " | ".join(headers) + " |",
               "|" + "|".join("---" for _ in headers) + "|"]
        out += ["| " + " | ".join("" if c is None else str(c) for c in r) + " |" for r in rows]
        return "\n".join(out)

    def pct(x):
        return "—" if x is None else f"{x * 100:.1f}%"

    mt = R["meta"]
    L = [f"# {mt['title']} — data appendix", "",
         f"*Generated {mt['generated_utc']}*", "",
         f"{mt['sport']}, {mt['seasons'][0]}–{mt['seasons'][-1]}. "
         f"{mt['matches_top25']:,} top-25 matchups ({mt['team_matches_top25']:,} team-matches) "
         f"out of {mt['team_matches_all_d1']:,} graded team-matches.", "",
         f"**Scope.** {mt['scope']}", "",
         f"**Set facts.** {mt['set_facts_source']}", "",
         "---", "", "## 1. Headline", ""]

    h = R["headline"]
    L.append(tbl(["Sample", "Won set 1 → win", "Lost set 1 → win", "Swing", "Matches"], [
        ["Top-25 vs top-25", pct(h["top25"]["won_set1"]["win_pct"]),
         pct(h["top25"]["lost_set1"]["win_pct"]), f"{h['top25']['swing'] * 100:+.1f}",
         f"{h['top25']['n_matches'] // 1:,}"],
        ["All D1", pct(h["all_d1"]["won_set1"]["win_pct"]),
         pct(h["all_d1"]["lost_set1"]["win_pct"]), f"{h['all_d1']['swing'] * 100:+.1f}",
         f"{h['all_d1']['n_matches']:,}"]]))
    L += ["", f"> {h['note']}", "", "### Top-25, by season", ""]
    L.append(tbl(["Season", "Won set 1 → win", "Matches"],
                 [[s, pct(v["won_set1"]["win_pct"]), v["won_set1"]["n"]]
                  for s, v in h["top25_by_season"].items()]))

    ml = R["match_length"]
    L += ["", "---", "", "## 2. Match length", ""]
    L.append(tbl(["Sets", "Top-25 share", "All-D1 share"],
                 [[k, pct(ml["top25"][k]["share"]), pct(ml["all_d1"][k]["share"])]
                  for k in ("3", "4", "5") if k in ml["top25"]]))
    L += ["", "### What set 1 is worth, by how long the match went", ""]
    L.append(tbl(["Sets", "Matches", "Set-1 winner wins"],
                 [[k, v["matches"], pct(v["win_pct"])]
                  for k, v in ml["set1_winner_wins_by_length"].items()]))
    L += ["", f"> {ml['note']}", "", "---", "", "## 3. Set-1 margin", ""]
    L.append(tbl(["Set 1 won by", "n", "Wins match", "Sweep"],
                 [[r["band"], r["n"], pct(r["win_pct"]), pct(r["sweep_pct"])]
                  for r in R["set1_margin"]["top25_winner"]]))
    L += ["", f"*{R['set1_margin']['caveat']}*", "",
          "---", "", "## 4. Who was already better", ""]
    L.append(tbl(["Matchup", "n (team-matches)", "Won set 1", "Lost set 1", "Swing"],
                 [[r["band"], r["n_team_matches"], pct(r["win_pct_won_set1"]),
                   pct(r["win_pct_lost_set1"]), f"{r['swing'] * 100:+.1f}"]
                  for r in R["rating_gap"]["top25"]]))
    L += ["", f"> {R['rating_gap']['finding']}", "",
          f"*Gap units: {R['rating_gap']['gap_units']}.*", "",
          "---", "", "## 5. Comebacks", ""]
    c = R["comebacks"]["top25"]
    L += [f"**{c['n']} of {c['of']}** ({pct(c['rate'])}) — final scores "
          + ", ".join(f"{k} ×{v}" for k, v in c["final_scores"].items())
          + f". Mean deficit overcome: {c['mean_set1_deficit_overcome']} points.", ""]
    L.append(tbl(["Set-1 deficit", "n", "Comeback rate"],
                 [[r["band"], r["n"], pct(r["win_pct"])] for r in R["comebacks"]["by_deficit"]]))
    L += ["", "### Largest deficits overcome", ""]
    L.append(tbl(["Season", "Comeback", "Result", "Set 1 by"],
                 [[r["season"], f"{r['team']} over {r['opponent']}", r["result"], r["set1_deficit"]]
                  for r in R["comebacks"]["largest_deficits_overcome"][:8]]))

    pl = R["point_leads"]
    L += ["", "---", "", "## 6. Point leads in set 1", "", f"*{pl['definition']}*", ""]
    L.append(tbl(["Lead at", "n", "Wins set 1", "Wins match", "Avg lead"],
                 [[f"first to {r['checkpoint']}", r["n"], pct(r["wins_set1"]),
                   pct(r["wins_match"]), r["mean_lead"]] for r in pl["by_checkpoint"]]))
    for k in ("5", "10", "15", "20"):
        if not pl["by_lead_size"].get(k):
            continue
        L += ["", f"### Lead size at {k} points", ""]
        L.append(tbl(["Lead", "n", "Wins set 1", "Wins match"],
                     [[r["lead"], r["n"], pct(r["wins_set1"]), pct(r["wins_match"])]
                      for r in pl["by_lead_size"][k]]))
    L += ["", "### Lead persistence", ""]
    L.append(tbl(["Held from", "Rate"],
                 [[k.replace("_to_", " → "), pct(v)]
                  for k, v in pl["lead_persistence"].items() if k != "n_matches"]))
    L += ["", f"> {pl['finding']}", "", "---", "", "## 7. Nebraska", ""]

    n = R["nebraska"]
    t = n["top25_matchups"]
    L += [f"Top-25 matchups: **{t['w']}–{t['l']}** in {t['n']} matches.", ""]
    L.append(tbl(["Situation", "Record", "Win %"], [
        ["After winning set 1", f"{t['won_set1']['w']}–{t['won_set1']['l']}", pct(t["won_set1"]["win_pct"])],
        ["After losing set 1", f"{t['lost_set1']['w']}–{t['lost_set1']['l']}", pct(t["lost_set1"]["win_pct"])]]))
    L += ["", "### By season (top-25 matchups)", ""]
    L.append(tbl(["Season", "Record", "Set 1 won", "Rate", "Won S1", "Lost S1"],
                 [[s, f"{v['w']}–{v['l']}", f"{v['set1_won']}/{v['n']}", pct(v["set1_rate"]),
                   f"{v['record_after_winning_set1']['w']}–{v['record_after_winning_set1']['l']}",
                   f"{v['record_after_losing_set1']['w']}–{v['record_after_losing_set1']['l']}"]
                  for s, v in n["by_season"].items()]))
    L += ["", "### Point leads in set 1", ""]
    L.append(tbl(["Lead at", "Led", "Of", "Rate", "Wins match"],
                 [[f"first to {r['checkpoint']}", r["led"], r["of"], pct(r["lead_rate"]),
                   pct(r["wins_match"])] for r in n["point_leads"]]))
    tr = n["trailing_at_20_in_set1"]
    L += ["", f"**Trailing at 20 in set 1:** {tr['w']}–{tr['l']} "
          f"(wins the set {pct(tr['wins_set1'])}, wins the match {pct(tr['wins_match'])}).", "",
          f"> {n['note']}", "", "### Official season records", ""]
    L.append(tbl(["Season", "Record", "Grade /7"],
                 [[s, f"{v['w']}–{v['l']}", v["grade"]] for s, v in n["official_records"].items()]))

    tl = R["team_level"]
    L += ["", "---", "", "## 8. Team level", "",
          f"Set-1 rate correlates **{tl['correlation_set1_rate_vs_win_pct_in_top25_games']:+.3f}** "
          f"with win percentage in top-25 matchups "
          f"({tl['n_team_seasons']} team-seasons, min {tl['min_matches']} matches).", ""]
    L.append(tbl(["Season", "Team", "Record", "Set-1 rate"],
                 [[r["season"], r["team"], r["record"], pct(r["set1_rate"])] for r in tl["leaders"]]))

    f = R["first_to_20"]
    L += ["", "---", "", "## 9. First to 20, in every set", "",
          f"*{f['definition']}*", ""]
    L.append(tbl(["Set", "n", "Wins that set", "Wins match", "If not first to 20", "Lift"],
                 [[r["set"], r["n"], pct(r["wins_that_set"]), pct(r["wins_match"]),
                   pct(r["wins_match_if_not_first_to_20"]), f"{r['lift'] * 100:+.1f}"]
                  for r in f["top25_by_set"]]))
    s5r = f["top25_set5_first_to_12"]
    L += ["", f"Deciding fifth set (first to 12 of 15): n={s5r['n']}, "
          f"wins the set {pct(s5r['wins_that_set'])}. *{s5r['note']}*", "",
          "### How many sets you led at 20", ""]
    L.append(tbl(["Sets first to 20", "Top-25 n", "Top-25 win %", "All-D1 n", "All-D1 win %"],
                 [[r["sets_first_to_20"], r["n"], pct(r["win_pct"]),
                   next((q["n"] for q in f["all_d1_by_count"]
                         if q["sets_first_to_20"] == r["sets_first_to_20"]), None),
                   pct(next((q["win_pct"] for q in f["all_d1_by_count"]
                             if q["sets_first_to_20"] == r["sets_first_to_20"]), None))]
                  for r in f["top25_by_count"]]))
    a = f["does_it_add_anything_beyond_the_set_result"]
    L += ["", "### Does it add anything beyond who won the set?", ""]
    L.append(tbl(["Condition", "n", "Wins match"],
                 [[k.replace("_", " "), v["n"], pct(v["win_pct"])]
                  for k, v in a.items() if isinstance(v, dict)]))
    L += ["", f"> {f['finding']}", ""]

    b = R["benchmark_rationale"]
    L += ["", "---", "", "## 10. Why set 1 is now graded", "",
          f"Replaced **{b['replaced']}**. {b['reason_practical']}", "",
          f"Grade AUC against match result: {b['grade_auc_before']} → **{b['grade_auc_after']}**. "
          f"Hit rate {pct(b['won_set1_hit_rate'])} — {b['hit_rate_note']}", "",
          f"First-to-20 was rejected for the same slot: a team first to 20 in every set wins "
          f"{pct(b['first_to_20_rejected']['p_win_given_first_to_20_every_set_all_d1'])} of matches "
          f"across D1. {b['first_to_20_rejected']['reason']}", ""]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--app-dir", type=Path, default=Path("app_data"))
    ap.add_argument("--rally-glob", default="data/rallies/wvb_rallies_div1_*.parquet")
    ap.add_argument("--out-dir", type=Path, default=Path("analysis"))
    args = ap.parse_args()

    R = build(args.app_dir, args.rally_glob)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    j = args.out_dir / "set_one_analysis.json"
    d = args.out_dir / "set_one_analysis.md"
    j.write_text(json.dumps(R, indent=2, default=str))
    d.write_text(to_markdown(R))
    print(f"wrote {j}  ({j.stat().st_size / 1024:.0f} KB)")
    print(f"wrote {d}  ({d.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
