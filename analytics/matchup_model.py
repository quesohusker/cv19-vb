"""Matchup predictor, and the expected-wins table built on it.

THE MODEL
---------
One logistic regression with three numbers in it:

    logit P(A beats B) = home * venue + b_elo * (Elo_A - Elo_B) / 100
                                      + b_ridge * (ridge_A - ridge_B) / 10

venue is +1 when A hosts, -1 when B hosts, 0 on a neutral floor. The two ratings are
the ones the Power Rankings page already publishes, so the predictor never disagrees
with the board about who is better, only about by how much that matters.

Every number here is fitted on pre-match information only. Elo is sequential, so its
pre-match value is free. The ridge fits a whole season at once, so it is refitted
every week on the matches played before that week began, and each match is predicted
from the fit that existed before it was played. Fitting on end-of-season ratings
instead would let every prediction see its own result.

WHY BOTH RATINGS
----------------
Held out one season at a time, the blend beats either rating alone on log loss in
every season tested, and again on 2026, which no fit has seen. Elo carries last season
and weights recent form; the ridge solves the whole schedule at once. They miss in
different places, which is the whole case for combining them.

Two things were tried and left out. A weight that slides from Elo toward the ridge as
the season fills in improved four of the four fitted seasons by about .002 of log loss
and made 2026 worse, so it is not in. And SOS stays out for the reason it stays out
of the rankings.

FITTING SEASONS
---------------
Every completed season except the first. 2021 is where Elo learns: every team starts
it at 1500, so its early predictions are the home edge and nothing else. The current
season is never in the fit, so its predictions are a genuine out-of-sample test that
re-runs every time the data updates.

SCORELINES
----------
The textbook way to get 3-0 / 3-1 / 3-2 from a match probability is to assume sets are
independent coin flips. It is badly wrong: among near-even matches it predicts 26%
sweeps against 35% observed, and 37% five-setters against 28%. Matches are more
lopsided than independent sets allow, because the uncertainty in how good each team is
on the night is shared by every set. So scorelines come from what actually happened:
the six outcomes are tabulated by how big a favourite the winner was, interpolated,
then scaled so they add up to the match probability exactly.

EXPECTED WINS
-------------
A team's expected wins is the sum of its pre-match win probabilities over the matches
it has played. W - xW is how far the results ran ahead of or behind the ratings.

It is luck. Odd-numbered matches against even-numbered ones correlate at -0.04, first
half against second at -0.09, one season against the next at -0.05 to -0.13. The
spread across teams is the spread coin flips produce: z-scores with sd 0.97 against
a theoretical 1.00, and 4.1% beyond two sigma against 4.6%. That is the finding the page
is built around.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import elo_ratings as E          # noqa: E402
import power_ratings as P        # noqa: E402

ELO_UNIT = 100.0      # coefficients read "per 100 Elo points"
RIDGE_UNIT = 10.0     # and "per 10 points of ridge rating"
BURN_IN = "2021"
# favourite-probability bins for the scoreline table; narrow where the data is dense
BINS = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00]
OUTCOMES = ["fav_3_0", "fav_3_1", "fav_3_2", "dog_3_2", "dog_3_1", "dog_3_0"]


# ---------------------------------------------------------------- features
def walk_forward(tm: pd.DataFrame, cfg: E.EloConfig = E.EloConfig()) -> pd.DataFrame:
    """Pre-match Elo and ridge for every match, one row per match, home side up."""
    tm = tm.copy()
    tm["match_date"] = pd.to_datetime(tm.match_date)

    _, elo = E.run(E.match_frame(tm), cfg)
    elo["date"] = pd.to_datetime(elo.date)

    rows = []
    for season, g in tm.groupby("season"):
        g = g.dropna(subset=["sideout_pct", "opponent"])
        src = g.rename(columns={"opponent": "opponent_matched"})
        week = g.match_date.dt.to_period("W-SUN").dt.start_time
        for start in sorted(week.unique()):
            prior = src[src.match_date < start]
            # the first week of a season has nothing to fit; every team is average
            r = (P.fit_season(prior, ridge=1.0).set_index("team").rating_overall
                 if len(prior) >= 50 else pd.Series(dtype=float))
            for x in g[(week == start) & (g.location == "home")].itertuples():
                rows.append((season, x.match_date, x.team, x.opponent,
                             r.get(x.team, 0.0), r.get(x.opponent, 0.0),
                             int(x.sets_for), int(x.sets_against)))
    ridge = pd.DataFrame(rows, columns=["season", "date", "home", "away", "ridge_home",
                                        "ridge_away", "home_sets", "away_sets"])
    d = elo.merge(ridge, on=["season", "date", "home", "away"], how="inner")
    return d[["season", "date", "home", "away", "elo_home", "elo_away", "ridge_home",
              "ridge_away", "home_won", "home_sets", "away_sets"]]


def design(d: pd.DataFrame, cols: list[str]) -> np.ndarray:
    x = {"elo": (d.elo_home - d.elo_away) / ELO_UNIT,
         "ridge": (d.ridge_home - d.ridge_away) / RIDGE_UNIT}
    return np.column_stack([np.ones(len(d))] + [x[c].to_numpy() for c in cols])


# ---------------------------------------------------------------- fitting
def logit_fit(X: np.ndarray, y: np.ndarray, iters: int = 60) -> np.ndarray:
    """Plain Newton-Raphson. Three parameters and twenty thousand rows need nothing more."""
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-X @ b))
        w = p * (1.0 - p)
        step = np.linalg.solve(X.T @ (X * w[:, None]) + 1e-9 * np.eye(len(b)),
                               X.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def prob(X: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-X @ b))


def score(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"n": int(len(y)),
            "accuracy": round(float(np.mean((p > 0.5) == (y == 1))), 4),
            "log_loss": round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 4),
            "brier": round(float(np.mean((p - y) ** 2)), 4)}


SPECS = {"elo": ["elo"], "ridge": ["ridge"], "blend": ["elo", "ridge"]}


def validate(d: pd.DataFrame, fit_seasons: list[str], current: str) -> list[dict]:
    """Leave one fitting season out, then the current season against all of them."""
    out = []
    for test in fit_seasons + [current]:
        train = d[d.season.isin([s for s in fit_seasons if s != test])]
        te = d[d.season == test]
        if te.empty:
            continue
        for name, cols in SPECS.items():
            b = logit_fit(design(train, cols), train.home_won.to_numpy())
            out.append({"season": test, "spec": name, "held_out": True,
                        **score(prob(design(te, cols), b), te.home_won.to_numpy())})
    return out


def calibration(p: np.ndarray, y: np.ndarray) -> list[dict]:
    """Favourite's view: of the matches the model called at 70-80%, how many went that way."""
    fav = np.where(p >= 0.5, p, 1 - p)
    won = np.where(p >= 0.5, y, 1 - y)
    cut = pd.cut(fav, [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0], include_lowest=True)
    t = pd.DataFrame({"bin": cut, "p": fav, "won": won}).groupby("bin", observed=True)
    return [{"bin": f"{iv.left:.0%}-{iv.right:.0%}", "n": int(len(g)),
             "predicted": round(float(g.p.mean()), 4), "actual": round(float(g.won.mean()), 4)}
            for iv, g in t]


def scorelines(d: pd.DataFrame, p: np.ndarray) -> list[dict]:
    """Share of each of the six results, by how big a favourite the winner was."""
    fav_home = p >= 0.5
    fav = np.where(fav_home, p, 1 - p)
    fs = np.where(fav_home, d.home_sets, d.away_sets)
    ds = np.where(fav_home, d.away_sets, d.home_sets)
    t = pd.DataFrame({"fav": fav, "fs": fs, "ds": ds})
    t = t[(t.fs == 3) | (t.ds == 3)]               # a handful of 2-0 records in the feed
    t["bin"] = pd.cut(t.fav, BINS, include_lowest=True)
    rows = []
    for _, g in t.groupby("bin", observed=True):
        n = len(g)
        rows.append({"p_fav": round(float(g.fav.mean()), 4), "n": n,
                     "fav_3_0": round(float(((g.fs == 3) & (g.ds == 0)).sum() / n), 4),
                     "fav_3_1": round(float(((g.fs == 3) & (g.ds == 1)).sum() / n), 4),
                     "fav_3_2": round(float(((g.fs == 3) & (g.ds == 2)).sum() / n), 4),
                     "dog_3_2": round(float(((g.ds == 3) & (g.fs == 2)).sum() / n), 4),
                     "dog_3_1": round(float(((g.ds == 3) & (g.fs == 1)).sum() / n), 4),
                     "dog_3_0": round(float(((g.ds == 3) & (g.fs == 0)).sum() / n), 4)})
    return rows


def persistence(preds: pd.DataFrame) -> dict:
    """Does beating your expected wins carry forward? The answer decides how to read it."""
    h = preds.assign(team=preds.home, p=preds.p_home, won=preds.home_won)
    a = preds.assign(team=preds.away, p=1 - preds.p_home, won=1 - preds.home_won)
    t = pd.concat([h, a])[["season", "date", "team", "p", "won"]].sort_values(
        ["season", "team", "date"])
    t["resid"] = t.won - t.p
    t["i"] = t.groupby(["season", "team"]).cumcount()
    t["n"] = t.groupby(["season", "team"]).team.transform("size")
    t = t[t.n >= 16]
    key = ["season", "team"]
    odd = t[t.i % 2 == 1].groupby(key).resid.mean()
    even = t[t.i % 2 == 0].groupby(key).resid.mean()
    first = t[t.i < t.n / 2].groupby(key).resid.mean()
    second = t[t.i >= t.n / 2].groupby(key).resid.mean()
    by = t.groupby(key).resid.mean().unstack(0)
    yy = {f"{a}-{b}": round(float(by[a].corr(by[b])), 3)
          for a, b in zip(by.columns[:-1], by.columns[1:])}
    g = t.groupby(key).agg(W=("won", "sum"), xW=("p", "sum"),
                           v=("p", lambda p: float((p * (1 - p)).sum())))
    z = (g.W - g.xW) / np.sqrt(g.v)
    return {"team_seasons": int(len(g)),
            "odd_vs_even": round(float(odd.corr(even)), 3),
            "first_vs_second_half": round(float(first.corr(second)), 3),
            "year_over_year": yy,
            "z_sd": round(float(z.std()), 3),
            "share_beyond_2sd": round(float(np.mean(np.abs(z) > 2)), 3),
            "share_beyond_2sd_if_pure_luck": 0.046,
            "median_season_sd_wins": round(float(np.sqrt(g.v).median()), 2)}


# ---------------------------------------------------------------- build
def build(matches_parquet: Path) -> tuple[dict, pd.DataFrame]:
    tm = pd.read_parquet(matches_parquet)
    d = walk_forward(tm)
    seasons = sorted(d.season.unique())
    current = seasons[-1]
    fit_seasons = [s for s in seasons if s not in (BURN_IN, current)]

    train = d[d.season.isin(fit_seasons)]
    b = logit_fit(design(train, SPECS["blend"]), train.home_won.to_numpy())
    alone = {name: logit_fit(design(train, cols), train.home_won.to_numpy()).tolist()
             for name, cols in SPECS.items() if name != "blend"}

    d["p_home"] = prob(design(d, SPECS["blend"]), b)
    train = d[d.season.isin(fit_seasons)]          # again, now that it carries p_home
    preds = d[d.season != BURN_IN].reset_index(drop=True)
    cur = d[d.season == current]

    model = {
        "coef": {"home": float(b[0]), "elo_per_100": float(b[1]),
                 "ridge_per_10": float(b[2])},
        "coef_alone": {"elo": {"home": alone["elo"][0], "elo_per_100": alone["elo"][1]},
                       "ridge": {"home": alone["ridge"][0],
                                 "ridge_per_10": alone["ridge"][1]}},
        "elo_config": {k: getattr(E.EloConfig(), k) for k in ("k", "home_adv",
                                                               "carryover", "mov")},
        "fit_seasons": fit_seasons,
        "current_season": current,
        "burn_in_season": BURN_IN,
        "validation": validate(d, fit_seasons, current),
        "calibration_current": calibration(cur.p_home.to_numpy(), cur.home_won.to_numpy()),
        "calibration_fit": calibration(train.p_home.to_numpy(), train.home_won.to_numpy()),
        "scorelines": scorelines(train, train.p_home.to_numpy()),
        "persistence": persistence(preds),
    }
    out = preds[["season", "date", "home", "away", "p_home", "home_won",
                 "home_sets", "away_sets", "elo_home", "elo_away",
                 "ridge_home", "ridge_away"]].copy()
    out["home_won"] = out.home_won.astype(int)
    return model, out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matches", type=Path, default=Path("app_data/matches.parquet"))
    ap.add_argument("--out-dir", type=Path, default=Path("app_data"))
    args = ap.parse_args()

    model, preds = build(args.matches)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "matchup_model.json").write_text(json.dumps(model, indent=2))
    preds.to_parquet(args.out_dir / "match_predictions.parquet",
                     compression="zstd", index=False)

    c = model["coef"]
    print(f"fitted on {', '.join(model['fit_seasons'])}: home {c['home']:+.3f}  "
          f"per 100 Elo {c['elo_per_100']:+.3f}  per 10 ridge {c['ridge_per_10']:+.3f}")
    v = pd.DataFrame(model["validation"])
    print("\nheld-out log loss (lower is better):")
    print(v.pivot(index="spec", columns="season", values="log_loss").to_string())
    print("\nheld-out accuracy:")
    print(v.pivot(index="spec", columns="season", values="accuracy").to_string())
    ps = model["persistence"]
    print(f"\nW - xW persistence: odd/even {ps['odd_vs_even']:+.3f}, halves "
          f"{ps['first_vs_second_half']:+.3f}, z sd {ps['z_sd']:.3f}")
    print(f"wrote matchup_model.json and match_predictions.parquet "
          f"({len(preds):,} matches, {preds.season.min()}-{preds.season.max()})")


if __name__ == "__main__":
    main()
