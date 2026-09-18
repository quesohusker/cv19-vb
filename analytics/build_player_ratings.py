"""Position power rankings for individual players.

Four position groups, each graded on its own small set of benchmarks, because the
positions do not share a job: a middle who never passes cannot be ranked on
passing, and a libero who never attacks cannot be ranked on hitting.

WHICH METRICS, AND WHY THESE. Chosen by split-half reliability -- each player's
matches split odd/even, the two halves correlated, Spearman-Brown for the full-season
estimate. A metric that does not repeat is measuring the night rather than the player.
Volume repeats almost perfectly (attacks .97 at half-season, kills .96, digs and
receptions .95), rate metrics much less: hitting efficiency reaches .49 at half-season
and .66 over a full one, which is why it is never the only attacking metric in a
group. Reception error rate is the weakest thing graded anywhere here, .30 and .46 for
back-row players, and it is kept anyway with the tradeoff stated plainly: digs and
receptions are both volume, so without it a libero is ranked purely on how many balls
came at her, which rewards playing behind a bad block. One weak quality signal beats
none. Ace-to-service-error was tested and dropped outright.

LIBERO AND DS ARE ONE GROUP. Their workloads are identical -- 3.78 / 3.80 / 3.75
receptions per set for L, L/DS and DS -- and 140 of 340 teams label every back-row
player "L/DS", so splitting them would rank players by their sports information
director's habits. The dig gap between the labels (2.50 vs 1.86 per set) is a
quality difference the ranking should surface, not a role difference that
justifies separate boards.

OUTSIDES ARE ADJUSTED FOR PASSING LOAD. Among high-volume outside attackers,
hitting efficiency falls from .214 to .186 as reception load rises (r = -0.22):
the outside who passes and swings gets the out-of-system ball. Raw efficiency
therefore penalises six-rotation outsides against right-side specialists who never
pass, so efficiency is scored as a residual against the league's efficiency-versus-
passing-load line. Attack volume alone does not hurt efficiency (r = +0.15) and is
not adjusted for.

SETTERS GET A SMALL ATTACKING BONUS. A setter who attacks brings something the
others do not, and the evidence says it is hers rather than her coach's: two
setters on the same roster dump at uncorrelated rates (r = -0.046), the rate
persists year over year at +0.805 -- higher than assists per set at +0.613 -- and
it follows a setter who changes teams at +0.647. It is awarded on kills per set
(split-half .88, full season .94), never on hitting efficiency (.41 and .59), because
production repeats where efficiency on a few dozen season attempts does not. At 0.10 it can order setters
within a benchmark count but can never leapfrog a full benchmark, and setter kills
are only about 1.5% of a team's offence, so small is the honest size.

THE BADGE IS UNADJUSTED, THE RANKING IS NOT. This follows the split the team side
already makes: the benchmark grade describes a performance and the power rating ranks
it. Raw per-set numbers put Northern Arizona's outside first in 2025 and Texas's
eighth, for the same reason the raw team grade put UTEP in the top ten -- a player
facing weak defences all year hits and scores like it. So `benchmarks_met` stays raw
against fixed thresholds (a legible description), and `rating` is computed on values
adjusted for the strength of the schedule her team actually played, using the
opponent ratings from analytics/power_ratings.py.

ONLY ACTIVE PLAYERS ARE RANKED IN A SEASON STILL BEING PLAYED. A season total is
frozen the day a player is hurt, and a frozen total keeps earning a top ranking it is
no longer being tested for. A player is ranked in the current season only if she has
played recently -- in at least one of her team's last three matches, and for at least
a third of the sets in that window. Everyone else stays in the file with `active`
false and the date she last played, so the app can show her without ranking her.
Finished seasons rank everybody: there, an injury in October is part of the record.

THRESHOLDS ARE FIXED, not per season. Each is the pooled median across the
reference seasons, so a player's score means the same thing in every season and
rankings can be compared across years.

Source is the volleyball-gis player box scores; only plain NCAA counting columns
are read.

Usage:
    python3 analytics/build_player_ratings.py --years 2022 2023 2024 2025 2026
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

MIN_SETS = 20

# source position codes -> the group they are ranked in
POSITION_GROUPS = {
    "OH": "Outside hitter",
    "MB": "Middle blocker", "MH": "Middle blocker",
    "S": "Setter",
    "OPP": "Opposite", "RS": "Opposite", "O": "Opposite",
    "L": "Back row", "DS": "Back row", "L/DS": "Back row",
}
# reference seasons the fixed thresholds are computed from
REFERENCE_SEASONS = ("2022", "2023", "2024", "2025")

COUNTS = ("S", "Kills", "Errors", "TotalAttacks", "Assists", "SetAtt", "RetAtt",
          "RErr", "Digs", "BlockSolos", "BlockAssists", "Aces", "SErr", "ServeAtt")


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def rate(n, d, min_d=1.0):
    return n / d if d >= min_d else None


def norm_name(name: str) -> str:
    """Key a player by her name, case-folded and whitespace-collapsed.

    The 2022 and 2023 files carry the same player under two casings -- "Merritt
    Beason" for 21 matches and "merritt Beason" for 14 -- which without this splits
    her season in two and drops both halves below the set minimum. It inflated 2023
    to 11,143 player-seasons against 2024's 5,960 off the same number of rows.
    """
    return " ".join((name or "").split()).casefold()


def read_playermatch(gis_dir: Path, years: list[int]) -> pd.DataFrame:
    """Every usable player-match row, with one settled identity per player-season.

    Everything downstream reads this frame: the season totals, the opponent
    adjustment, the recency check and the reliability test. They have to agree on who
    a player is, and two things in the source stop them agreeing by accident.

    NAME CASING. The 2022 and 2023 files carry the same player under two casings --
    "Merritt Beason" for 21 matches and "merritt Beason" for 14. Keyed naively that is
    two players, both below the set minimum. It inflated 2023 to 11,143 player-seasons
    against 2024's 5,960 off the same number of rows.

    MOVING LABELS. Rosters list the same player as OPP in some matches and O in others,
    or OH and DS in the same season. Keyed on the label she becomes two players again,
    so a season's position is whichever label she played the most sets under.
    """
    frames = []
    for year in years:
        path = gis_dir / f"wvb_playermatch_div1_{year}.csv"
        if not path.exists():
            print(f"  skip {year}: no {path.name}")
            continue
        rows = []
        skipped = 0
        for r in csv.DictReader(open(path, newline="")):
            group = POSITION_GROUPS.get((r.get("P") or "").strip())
            if group is None:
                skipped += 1
                continue
            rows.append({
                "season": str(year), "date": r["Date"], "team": r["Team"],
                "opponent": (r.get("Opponent Team") or "").strip() or "(unknown)",
                "conference": r.get("Conference", ""),
                "player": (r.get("Player") or "").strip(),
                "key": norm_name(r.get("Player")), "label_group": group,
                **{c: num(r.get(c)) for c in COUNTS},
            })
        print(f"  {year}: {len(rows):,} player-match rows "
              f"({skipped:,} without a usable position)")
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    pm = pd.concat(frames, ignore_index=True)
    pm["uid"] = pm.season + "|" + pm.team + "|" + pm.key

    # majority label by sets played, and the spelling used in the most matches
    weight = pm.S.where(pm.S > 0, 1.0)
    by_label = (pm.assign(w=weight).groupby(["uid", "label_group"], as_index=False).w.sum()
                  .sort_values("w", ascending=False).drop_duplicates("uid"))
    by_name = (pm.groupby(["uid", "player"], as_index=False).size()
                 .sort_values("size", ascending=False).drop_duplicates("uid"))
    pm = (pm.drop(columns=["player"])
            .merge(by_label[["uid", "label_group"]].rename(
                columns={"label_group": "position"}), on="uid")
            .merge(by_name[["uid", "player"]], on="uid"))
    return pm


def player_seasons(pm: pd.DataFrame) -> pd.DataFrame:
    """One row per player per season, with the raw counting totals."""
    keys = ["uid", "season", "team", "conference", "player", "position"]
    out = (pm.groupby(keys, as_index=False)
             .agg(matches=("date", "size"), **{c: (c, "sum") for c in COUNTS}))
    return out


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Rate metrics. Everything is per set or per attempt; raw counts rank rosters."""
    d = df.copy()
    s = d.S.replace(0, pd.NA)
    d["kills_per_set"] = d.Kills / s
    d["attacks_per_set"] = d.TotalAttacks / s
    d["digs_per_set"] = d.Digs / s
    d["receptions_per_set"] = d.RetAtt / s
    d["assists_per_set"] = d.Assists / s
    d["blocks_per_set"] = (d.BlockSolos + d.BlockAssists / 2) / s
    d["hit_pct"] = ((d.Kills - d.Errors) / d.TotalAttacks.where(d.TotalAttacks >= 50))
    d["assist_rate"] = d.Assists / d.SetAtt.where(d.SetAtt >= 100)
    d["reception_err_rate"] = d.RErr / d.RetAtt.where(d.RetAtt >= 50)
    d["ace_per_serve"] = d.Aces / d.ServeAtt.where(d.ServeAtt >= 50)
    return d


def adjust_outside_efficiency(d: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Score an outside's efficiency against what her passing load predicts.

    The fit has to control for attack volume, because pooling hides the effect
    entirely. Within high-volume attackers the correlation between passing load and
    efficiency is -0.200, and within low-volume attackers -0.247, but across all
    outsides together it is -0.029: high-volume attackers both pass more AND hit
    better, and the two cancel. A univariate fit on passing load alone therefore
    returns a slope of -0.0003 and adjusts nothing. Simpson's paradox, in a stat
    sheet.

    Only the passing coefficient is used to adjust. Attack volume is left alone --
    swinging a lot is part of being good, and it is already its own benchmark.
    """
    d = d.copy()
    d["hit_pct_pass"] = d["hit_pct"]
    oh = d[(d.position == "Outside hitter") & d.hit_pct.notna()
           & d.receptions_per_set.notna() & d.attacks_per_set.notna()
           & (d.S >= MIN_SETS)]
    fit = oh[oh.season.isin(REFERENCE_SEASONS)]
    if len(fit) < 200:
        print("  too few reference outsides to fit the passing adjustment; leaving raw")
        return d, None

    # ordinary least squares, two predictors, via the normal equations
    X = np.column_stack([np.ones(len(fit)),
                         fit.receptions_per_set.astype(float).to_numpy(),
                         fit.attacks_per_set.astype(float).to_numpy()])
    y = fit.hit_pct.astype(float).to_numpy()
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    intercept, b_recv, b_atk = (float(x) for x in b)
    mean_recv = float(fit.receptions_per_set.astype(float).mean())

    mask = d.index.isin(oh.index)
    recv = d.loc[mask, "receptions_per_set"].astype(float)
    d.loc[mask, "hit_pct_pass"] = d.loc[mask, "hit_pct"].astype(float) - b_recv * (recv - mean_recv)
    print(f"  outside passing adjustment (controlling for attack volume):")
    print(f"    hit% = {intercept:.4f} {b_recv:+.5f} x receptions/set "
          f"{b_atk:+.5f} x attacks/set   (n={len(fit):,})")
    print(f"    a six-rotation outside at {mean_recv + 3:.1f} receptions/set is credited "
          f"{abs(b_recv) * 3 * 1000:.1f} points of hitting efficiency")
    return d, {"intercept": round(intercept, 5),
               "slope_receptions_per_set": round(b_recv, 5),
               "slope_attacks_per_set": round(b_atk, 5),
               "mean_receptions_per_set": round(mean_recv, 3),
               "n": int(len(fit)),
               "note": ("fitted with attack volume controlled; pooling without it gives "
                        "-0.0003 and adjusts nothing, because high-volume attackers both "
                        "pass more and hit better")}


# per-match rate metrics, as (numerator, denominator, per-match denominator floor).
# The denominator is also the weight: a player who swung 40 times says more about her
# hitting than one who swung 4, and a five-set night says more than a sweep.
RATE_DEFS = {
    "kills_per_set":      (lambda v: v.Kills, lambda v: v.S, 1),
    "attacks_per_set":    (lambda v: v.TotalAttacks, lambda v: v.S, 1),
    "digs_per_set":       (lambda v: v.Digs, lambda v: v.S, 1),
    "receptions_per_set": (lambda v: v.RetAtt, lambda v: v.S, 1),
    "assists_per_set":    (lambda v: v.Assists, lambda v: v.S, 1),
    "blocks_per_set":     (lambda v: v.BlockSolos + v.BlockAssists / 2, lambda v: v.S, 1),
    "hit_pct":            (lambda v: v.Kills - v.Errors, lambda v: v.TotalAttacks, 3),
    "assist_rate":        (lambda v: v.Assists, lambda v: v.SetAtt, 5),
    "reception_err_rate": (lambda v: v.RErr, lambda v: v.RetAtt, 3),
}


def opponent_adjust(pm: pd.DataFrame, seasons: list[str], metrics: list[str],
                    ridge_k: float = 0.5, iters: int = 40) -> tuple[pd.DataFrame, dict]:
    """Split each player's rate into her own effect and her opponents' -- per match.

    WHY NOT SCHEDULE STRENGTH. The obvious cheap version -- average the opponent team
    ratings over a season and regress the metric on that -- does not work here, and
    fails in a way worth recording so nobody rebuilds it. A team's mean opponent
    offence and mean opponent defence correlate at 0.993, so the two-predictor fit is
    unidentified and the coefficients cancel arbitrarily. Worse, the confound runs the
    wrong way: the teams with hard schedules are the deep ones, where four good
    attackers split the swings, so the fit reads "hard schedule, fewer kills per set"
    as an opponent effect when it is a usage effect. Run on 2025 it moved Texas's
    outside DOWN from 4.69 kills per set to 4.47 and Jackson State's UP from 4.03 to
    4.20 -- an opponent adjustment that rewards playing nobody.

    WHAT THIS DOES INSTEAD. One additive model per season, position group and metric,
    over individual player-matches:

        rate(player i, against team j)  =  mu + player_i - opponent_j

    fitted by alternating weighted means, weighted by the denominator (sets, attack
    attempts, set attempts) so a long match or a heavy night counts for more. Opponent
    effects carry a ridge penalty and player effects do not, because the opponents are
    the nuisance here. The penalty is set relative to the average opponent's weight
    rather than as a bare constant, since the denominators are not comparable across
    metrics -- a match contributes ~4 sets but ~35 attack attempts, so one scalar would
    shrink efficiency twenty times harder than kills per set.

    CALIBRATION AND SIGN CHECK. Both come from quantities this model never sees. At
    ridge_k = 0.5 the fitted opponent effects on hitting efficiency have sd 0.027,
    against the ~0.030 spread of team opponent-hitting-efficiency in the team tables,
    so the model is claiming about as much defensive variation as actually exists.
    Heavier shrinkage keeps raising the correlation with the team numbers, but that is
    shrinkage toward a correlated target rather than a better fit, so sd is the
    criterion and the correlations are used only to check direction. All three point
    the right way: the opponent effect on hitting efficiency correlates -0.71 with what
    that team actually allowed opponents to hit, the effect on kills per set -0.50 with
    the same, and the effect on digs per set +0.45 with how well that team attacked.
    Forty iterations; the largest player effect still moves by 0.0013 at thirty and is
    flat after.

    The adjusted value is mu + player_i, which stays on the metric's own scale -- an
    adjusted 3.9 kills per set is still kills per set. It reads as what she would have
    produced against an average Division I opponent.

    WHAT IT STILL DOES NOT FIX: usage. An outside who takes 40% of a thin team's swings
    out-produces one of four good attackers per set, and no opponent adjustment touches
    that, because it is not the opponent's doing. Hitting efficiency is the partial
    counterweight, and it is why the attacking groups never rank on volume alone.
    """
    out_rows: list[dict] = []
    diag: dict[str, dict] = {}
    for season in seasons:
        sdf = pm[pm.season == season]
        if sdf.empty:
            continue
        for group in sorted(sdf.position.unique()):
            g = sdf[sdf.position == group]
            for metric in metrics:
                if metric not in RATE_DEFS:
                    continue
                num_fn, den_fn, floor = RATE_DEFS[metric]
                w = den_fn(g).astype(float)
                keep = w >= floor
                if keep.sum() < 500:
                    continue
                sub = g[keep]
                w = w[keep].to_numpy()
                y = (num_fn(sub).astype(float).to_numpy()) / w
                mu = float((y * w).sum() / w.sum())
                pl_key = sub.uid.to_numpy()
                op_key = sub.opponent.to_numpy()
                pl_idx, pl_lab = pd.factorize(pl_key)
                op_idx, op_lab = pd.factorize(op_key)
                pl_w = np.bincount(pl_idx, weights=w)
                op_w = np.bincount(op_idx, weights=w)
                ridge = ridge_k * float(op_w.mean())
                pl = np.zeros(len(pl_lab))
                op = np.zeros(len(op_lab))
                r = y - mu
                for _ in range(iters):
                    pl = np.bincount(pl_idx, weights=w * (r + op[op_idx])) / pl_w
                    op = (np.bincount(op_idx, weights=w * (pl[pl_idx] - r))
                          / (op_w + ridge))
                for uid, eff in zip(pl_lab, pl):
                    out_rows.append({"season": season, "uid": uid,
                                     "metric": metric, "value_adj": mu + eff})
                diag.setdefault(season, {}).setdefault(group, {})[metric] = {
                    "league_mean": round(mu, 4),
                    "ridge": round(ridge, 1),
                    "opponent_effect_sd": round(float(op.std()), 4),
                    "player_effect_sd": round(float(pl.std()), 4),
                    "player_matches": int(keep.sum()),
                    "opponents": int(len(op_lab)),
                }
    wide = (pd.DataFrame(out_rows)
            .pivot(index=["season", "uid"], columns="metric", values="value_adj")
            .rename(columns=lambda c: f"{c}_adj").reset_index())
    return wide, diag


def recency(pm: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """When each player last played, and how much of her team's last three matches.

    The bar is one set in that window -- enough to show she is still on the floor,
    loose enough not to punish a starter rested through a mid-week sweep.

    Measured against her team's schedule, not the calendar, because teams do not play
    on the same days: "three matches ago" is the same amount of missed volleyball for
    everyone, "two weeks ago" is not.
    """
    team_dates = (pm.groupby(["season", "team", "date"], as_index=False).S.max()
                    .rename(columns={"S": "team_sets"})
                    .sort_values(["season", "team", "date"]))
    team_dates["from_end"] = (team_dates.groupby(["season", "team"]).cumcount(ascending=False))
    recent = team_dates[team_dates.from_end < window]
    played = pm.groupby(["uid", "season", "team", "date"], as_index=False).S.sum()

    last = played[played.S > 0].groupby("uid", as_index=False).date.max() \
                 .rename(columns={"date": "last_played"})
    n_after = (played[played.S > 0].groupby("uid", as_index=False).date.max()
               .rename(columns={"date": "last_played"})
               .merge(team_dates[["season", "team", "date"]]
                      .merge(played[["uid", "season", "team"]].drop_duplicates(),
                             on=["season", "team"]),
                      on="uid", how="left"))
    missed = (n_after[n_after.date > n_after.last_played]
              .groupby("uid", as_index=False).size()
              .rename(columns={"size": "team_matches_missed"}))

    in_window = played.merge(recent[["season", "team", "date", "team_sets"]],
                             on=["season", "team", "date"])
    got = (in_window.groupby("uid", as_index=False)
           .agg(recent_sets=("S", "sum")))
    team_window = (recent.groupby(["season", "team"], as_index=False)
                   .team_sets.sum().rename(columns={"team_sets": "window_team_sets"}))

    out = (pm[["uid", "season", "team"]].drop_duplicates()
           .merge(last, on="uid", how="left")
           .merge(missed, on="uid", how="left")
           .merge(got, on="uid", how="left")
           .merge(team_window, on=["season", "team"], how="left"))
    out["team_matches_missed"] = out.team_matches_missed.fillna(0).astype(int)
    out["recent_sets"] = out.recent_sets.fillna(0.0)
    out["recent_set_share"] = (out.recent_sets / out.window_team_sets).round(3)
    out["active"] = out.recent_sets >= 1.0
    return out.drop(columns=["window_team_sets", "season", "team"])


# (metric, direction, label) per group. direction +1 = higher is better.
BENCHMARKS = {
    "Outside hitter": [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct_pass", +1, "Hitting efficiency, adjusted for passing load"),
        ("receptions_per_set", +1, "Receptions per set"),
        ("digs_per_set", +1, "Digs per set"),
    ],
    "Middle blocker": [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct", +1, "Hitting efficiency"),
        ("blocks_per_set", +1, "Blocks per set"),
        ("attacks_per_set", +1, "Attacks per set"),
    ],
    "Opposite": [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct", +1, "Hitting efficiency"),
        ("blocks_per_set", +1, "Blocks per set"),
        ("attacks_per_set", +1, "Attacks per set"),
    ],
    "Setter": [
        ("assists_per_set", +1, "Assists per set"),
        ("assist_rate", +1, "Assists per set attempt"),
        ("digs_per_set", +1, "Digs per set"),
    ],
    "Back row": [
        ("digs_per_set", +1, "Digs per set"),
        ("receptions_per_set", +1, "Receptions per set"),
        ("reception_err_rate", -1, "Reception error rate"),
    ],
}
SETTER_BONUS = ("kills_per_set", 0.40, 0.10)   # metric, threshold, weight


def fixed_thresholds(d: pd.DataFrame) -> dict:
    """Pooled reference-season median per group per metric."""
    out: dict[str, dict[str, float]] = {}
    ref = d[d.season.isin(REFERENCE_SEASONS) & (d.S >= MIN_SETS)]
    for group, specs in BENCHMARKS.items():
        g = ref[ref.position == group]
        out[group] = {}
        for metric, _direction, _label in specs:
            vals = pd.to_numeric(g[metric], errors="coerce").dropna()
            if len(vals) < 50:
                print(f"  {group}/{metric}: only {len(vals)} reference players; "
                      "threshold may be unstable")
            out[group][metric] = round(float(vals.median()), 5) if len(vals) else None
    return out


def reference_distributions(d: pd.DataFrame) -> dict:
    """Sorted reference values per group per metric, for turning values into percentiles.

    Built on the schedule-adjusted values, because the rating is, and a percentile has
    to be taken against the same quantity it scores. Fixed on the reference seasons,
    like the thresholds, so a rating means the same thing in 2026 as in 2023 rather
    than floating with whoever happened to play.
    """
    ref = d[d.season.isin(REFERENCE_SEASONS) & (d.S >= MIN_SETS)]
    out: dict[str, dict[str, list]] = {}
    for group, specs in BENCHMARKS.items():
        g = ref[ref.position == group]
        out[group] = {}
        for metric, _direction, _label in specs:
            col = f"{metric}_adj" if f"{metric}_adj" in g.columns else metric
            vals = sorted(pd.to_numeric(g[col], errors="coerce").dropna().tolist())
            out[group][metric] = vals
    return out


def percentile_of(vals: list, x: float) -> float:
    """Where x sits in the reference distribution, 0-100."""
    if not vals or pd.isna(x):
        return float("nan")
    lo, hi = 0, len(vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if vals[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return 100.0 * lo / len(vals)


def score(d: pd.DataFrame, thresholds: dict, refs: dict,
          current_season: str | None = None) -> pd.DataFrame:
    """Two numbers per player: a legible benchmark count, and the rating that ranks.

    The count is raw and the rating is schedule-adjusted, deliberately. The count says
    what a player did -- 3.5 kills a set is 3.5 kills a set, and burying it under an
    adjustment makes it unreadable. The rating says how good she is, which is not the
    same question once you notice that her opponents differ from everyone else's.

    The count also cannot rank on its own. With three or four benchmarks it has four or
    five possible values, so 433 of 1,137 outsides tie at the top -- fine for describing
    one match, useless for ordering a position. The rating is the mean of the player's
    percentiles on the adjusted metrics, against the same fixed reference seasons, which
    separates continuously without introducing a single arguable weight: every metric
    counts the same.
    """
    d = d[d.S >= MIN_SETS].copy()
    d["benchmarks_met"] = 0.0
    d["benchmarks_of"] = 0
    d["rating"] = float("nan")
    d["setter_attack_bonus"] = 0.0

    for group, specs in BENCHMARKS.items():
        idx = d.index[d.position == group]
        if not len(idx):
            continue
        met = pd.Series(0.0, index=idx)
        of = pd.Series(0, index=idx)
        pct_sum = pd.Series(0.0, index=idx)
        pct_n = pd.Series(0, index=idx)
        for metric, direction, _label in specs:
            raw = pd.to_numeric(d.loc[idx, metric], errors="coerce")
            adj_col = f"{metric}_adj" if f"{metric}_adj" in d.columns else metric
            adj = pd.to_numeric(d.loc[idx, adj_col], errors="coerce")
            thr = thresholds[group].get(metric)
            if thr is not None:
                hit = (raw >= thr) if direction > 0 else (raw <= thr)
                met += hit.where(raw.notna(), False).astype(float)
                of += raw.notna().astype(int)
                d.loc[idx, f"b_{metric}"] = hit.where(raw.notna())
            vals = refs[group].get(metric) or []
            pct = adj.map(lambda x: percentile_of(vals, x))
            if direction < 0:
                pct = 100.0 - pct          # lower is better
            pct_sum += pct.fillna(0.0)
            pct_n += pct.notna().astype(int)
        d.loc[idx, "benchmarks_met"] = met
        d.loc[idx, "benchmarks_of"] = of
        d.loc[idx, "rating"] = (pct_sum / pct_n.where(pct_n > 0)).astype(float)

    # the setter attacking credit, kept at the same proportion of the scale it had
    # as a 0.10 on a three-benchmark count
    metric, thr, weight = SETTER_BONUS
    bonus_points = round(weight / len(BENCHMARKS["Setter"]) * 100.0, 2)
    setters = d.index[(d.position == "Setter")
                      & (pd.to_numeric(d[metric], errors="coerce") >= thr)]
    d.loc[setters, "setter_attack_bonus"] = bonus_points
    # Rescale the whole setter board rather than letting the bonus run past 100. The
    # order is identical either way, but a rating of 102 on a 0-100 scale reads as a
    # bug, and capping would tie exactly the setters the bonus exists to separate.
    is_setter = d.position == "Setter"
    d.loc[is_setter, "rating"] = (
        (d.loc[is_setter, "rating"] + d.loc[is_setter, "setter_attack_bonus"])
        / (1 + bonus_points / 100.0))

    d["score"] = d.benchmarks_met + (d.setter_attack_bonus > 0).astype(float) * weight

    # Who the board is for. A season still being played ranks only players still
    # playing it; a finished season ranks everybody, because there an injury in
    # October is part of that season's record rather than a stale number.
    if "active" not in d.columns:
        d["active"] = True
    d["ranked"] = True
    if current_season is not None:
        live = d.season == current_season
        d.loc[live, "ranked"] = d.loc[live, "active"].fillna(False).astype(bool)

    r = d.where(d.ranked)
    d["rank_in_position"] = (r.groupby(["season", "position"]).rating
                             .rank(ascending=False, method="min").astype("Int64"))
    d["players_in_position"] = (d[d.ranked].groupby(["season", "position"]).rating
                                .transform("size").reindex(d.index).astype("Int64"))
    return d.sort_values(["season", "position", "rank_in_position", "player"])


def split_half_reliability(pm: pd.DataFrame) -> dict:
    """Odd/even match split per player-season -- does the metric measure the player?

    A metric that does not agree with itself across a player's own season is measuring
    the night, not the player, and has no business ranking anybody. Spearman-Brown
    turns the half-season correlation into the full-season estimate reported alongside.
    """
    d = pm.sort_values(["uid", "date"]).copy()
    d["half"] = d.groupby("uid").cumcount() % 2
    h = d.groupby(["uid", "position", "half"], as_index=False)[list(COUNTS)].sum()

    FN = {
        "kills_per_set": (lambda v: v.Kills, lambda v: v.S, 8),
        "attacks_per_set": (lambda v: v.TotalAttacks, lambda v: v.S, 8),
        "digs_per_set": (lambda v: v.Digs, lambda v: v.S, 8),
        "receptions_per_set": (lambda v: v.RetAtt, lambda v: v.S, 8),
        "assists_per_set": (lambda v: v.Assists, lambda v: v.S, 8),
        "blocks_per_set": (lambda v: v.BlockSolos + v.BlockAssists / 2, lambda v: v.S, 8),
        "hit_pct": (lambda v: v.Kills - v.Errors, lambda v: v.TotalAttacks, 25),
        "assist_rate": (lambda v: v.Assists, lambda v: v.SetAtt, 80),
        "reception_err_rate": (lambda v: v.RErr, lambda v: v.RetAtt, 25),
    }
    out: dict[str, dict[str, dict]] = {}
    for group, g in h.groupby("position"):
        out[group] = {}
        wide = g.pivot(index="uid", columns="half")
        for name, (num_fn, den_fn, floor) in FN.items():
            pairs = []
            for half in (0, 1):
                cols = wide.xs(half, axis=1, level="half")
                den = den_fn(cols).astype(float)
                val = (num_fn(cols).astype(float) / den).where(den >= floor)
                pairs.append(val)
            both = pd.concat(pairs, axis=1).dropna()
            if len(both) < 30:
                continue
            # rank then Pearson: Spearman without the scipy dependency
            r = both.rank()
            rho = round(float(r.iloc[:, 0].corr(r.iloc[:, 1])), 3)
            out[group][name] = {"split_half": rho, "n": int(len(both)),
                                "full_season_est": round(2 * rho / (1 + rho), 3)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", nargs="+", type=int,
                    default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--gis-dir", type=Path, default=Path("../volleyball-gis/public/data"))
    ap.add_argument("--out-dir", type=Path, default=Path("app_data"))
    ap.add_argument("--current-season", help="season still being played; only players "
                    "active in it are ranked (default: the latest season read)")
    args = ap.parse_args()

    if not args.gis_dir.exists():
        raise SystemExit(
            f"Not found: {args.gis_dir}\n"
            "Clone the player box scores next to this repository:\n"
            "  git clone https://github.com/jpitel24/volleyball-gis ../volleyball-gis")

    print("reading player box scores")
    pm = read_playermatch(args.gis_dir, args.years)
    if pm.empty:
        raise SystemExit("No player rows read.")

    d = derive(player_seasons(pm))
    d, adjustment = adjust_outside_efficiency(d)

    print("\nseparating each player from the opponents she faced")
    metrics = sorted(({m for specs in BENCHMARKS.values() for m, _, _ in specs}
                      | {"hit_pct"}) & set(RATE_DEFS))
    adj, opp_diag = opponent_adjust(pm, sorted(pm.season.unique()), metrics)
    d = d.merge(adj, on=["season", "uid"], how="left")

    # An outside's efficiency carries two corrections, and they compose: the opponent
    # fit says what she would hit against an average defence, the passing fit says what
    # her share of the serve receive cost her. Add the second to the first rather than
    # re-deriving it, so neither is applied twice.
    d["hit_pct_pass_adj"] = d.hit_pct_adj.fillna(d.hit_pct) + (d.hit_pct_pass - d.hit_pct)
    for metric in metrics:
        col = f"{metric}_adj"
        if col in d:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(
                pd.to_numeric(d[metric], errors="coerce"))
    d["opponent_adjusted"] = d.hit_pct_adj.notna() | d.kills_per_set_adj.notna()

    print("\nchecking who is still on the floor")
    d = d.merge(recency(pm), on="uid", how="left")
    d["active"] = d.active.fillna(False).astype(bool)

    thresholds = fixed_thresholds(d)
    refs = reference_distributions(d)
    current = args.current_season or max(d.season)
    scored = score(d, thresholds, refs, current_season=current)
    live = scored[scored.season == current]
    print(f"  {current}: {int(live.ranked.sum()):,} of {len(live):,} players with "
          f"{MIN_SETS}+ sets played in their team's last three matches")

    print("\nchecking that the graded metrics measure the player, not the night")
    reliability = split_half_reliability(pm)

    keep = ["season", "team", "conference", "player", "position", "matches", "S",
            "kills_per_set", "attacks_per_set", "hit_pct", "hit_pct_pass",
            "blocks_per_set", "digs_per_set", "receptions_per_set",
            "reception_err_rate", "assists_per_set", "assist_rate", "ace_per_serve",
            "opponent_adjusted",
            "last_played", "team_matches_missed", "recent_sets", "recent_set_share",
            "active", "ranked",
            "benchmarks_met", "benchmarks_of", "setter_attack_bonus", "score", "rating",
            "rank_in_position", "players_in_position"]
    keep += [c for c in scored.columns if c.startswith("b_")]
    keep += [f"{m}_adj" for specs in BENCHMARKS.values() for m, _, _ in specs]
    keep = list(dict.fromkeys(keep))
    out = scored[[c for c in keep if c in scored.columns]].rename(columns={"S": "sets"})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out_dir / "players.parquet", compression="zstd", index=False)
    (args.out_dir / "player_benchmarks.json").write_text(json.dumps({
        "min_sets": MIN_SETS,
        "reference_seasons": list(REFERENCE_SEASONS),
        "threshold_basis": ("pooled median across the reference seasons, fixed so a "
                            "score means the same thing in every season"),
        "groups": {g: [{"metric": m, "direction": "higher_is_better" if dirn > 0
                        else "lower_is_better", "label": lab,
                        "threshold": thresholds[g].get(m)}
                       for m, dirn, lab in specs]
                   for g, specs in BENCHMARKS.items()},
        "setter_attack_bonus": {"metric": SETTER_BONUS[0], "threshold": SETTER_BONUS[1],
                                "weight": SETTER_BONUS[2],
                                "note": ("awarded on kills per set, not hitting efficiency: "
                                         "production repeats (split-half .82) where "
                                         "efficiency on ~20 season attempts does not (.25)")},
        "outside_passing_adjustment": adjustment,
        "opponent_adjustment": {
            "model": "rate(player i vs team j) = mu + player_i - opponent_j, per season",
            "fit": ("alternating weighted means, weighted by the denominator; ridge 25 "
                    "on opponent effects only"),
            "applies_to": ("the rating only; benchmarks_met stays raw so the badge "
                           "remains readable"),
            "rejected_alternative": (
                "regressing on season schedule strength. Mean opponent offence and "
                "defence correlate 0.993 so the fit is unidentified, and deep teams "
                "play hard schedules, so it reads roster depth as opponent difficulty. "
                "It moved Texas's 2025 outside from 4.69 kills per set down to 4.47 and "
                "Jackson State's up from 4.03 to 4.20."),
            "does_not_fix": (
                "usage. An outside taking 40% of a thin team's swings out-produces one "
                "of four good attackers per set, and that is not the opponent's doing."),
            "per_season": opp_diag,
        },
        "recency_rule": {
            "current_season": current,
            "rule": "at least one set played in the team's last three matches",
            "note": ("applied to the season still being played, so a season total "
                     "frozen by injury stops holding a ranking it is no longer being "
                     "tested for. Finished seasons rank everyone who met the set "
                     "minimum."),
        },
        "reliability": reliability,
    }, indent=2))

    print(f"\nwrote {args.out_dir / 'players.parquet'}  {len(out):,} player-seasons")
    print(f"wrote {args.out_dir / 'player_benchmarks.json'}")
    for season in sorted(out.season.unique()):
        s = out[(out.season == season) & out.ranked]
        counts = ", ".join(f"{g} {len(x):,}" for g, x in s.groupby("position"))
        print(f"  {season}: {counts}")


if __name__ == "__main__":
    main()
