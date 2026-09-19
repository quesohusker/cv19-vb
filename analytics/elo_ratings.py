"""Elo ratings for NCAA women's volleyball.

WHY THIS EXISTS ALONGSIDE power_ratings.py
------------------------------------------
The ridge model in power_ratings.py fits a whole season at once, so it weights a
match in August exactly like a match in December. It cannot see a team improve.
Elo is sequential by construction -- every match moves the rating, and old results
decay on their own -- so it answers "who is good now" rather than "who was good this
season". The two disagree most about exactly the teams worth arguing over: the ones
that changed.

Elo also runs forward with no refit, so it gives an honest pre-match number for every
match ever played. That makes it the right tool for backtesting and for in-season
prediction, where the ridge model would be peeking at results it has not seen yet.

THE MODEL
---------
Standard Elo on a 400-point logistic scale:

    E_a = 1 / (1 + 10 ** (-(R_a - R_b + H) / 400))
    R_a := R_a + K * mult * (S_a - E_a)

H is the home edge in rating points, applied to the designated home team. The feed
carries no neutral-site flag, and early-season tournaments still name a host, so H is
fitted rather than assumed -- the raw 57.2% host win rate is mostly hosts being better
teams, not the gym.

MARGIN OF VICTORY
-----------------
S is the match result, 1 or 0. Margin enters through `mult`, which scales K by how
convincing the win was. Volleyball offers two margins and they are not equally good:

  sets   3-0 vs 3-2. Three levels of information, and set scores are lumpy -- a 3-2
         win can outplay a 3-0 win.
  rally  the share of all rallies the winner took. ~180 rallies a match instead of
         5 sets, which is the same reason the ridge model beats a win-loss model:
         more evidence per match, not a cleverer update rule.

`mult` uses the usual damping on the favourite's rating edge:

    mult = ln(margin + 1) * (2.2 / (0.001 * elo_diff_for_winner + 2.2))

Without the damping term, a strong team running up scores against weak opponents
inflates its own rating without bound, because each blowout is both predicted AND
rewarded. The denominator shrinks the update when the winner was already favoured.

CARRYOVER
---------
Between seasons each team regresses toward the league mean:

    R := MEAN + carryover * (R - MEAN)

Rosters turn over hard in college volleyball. carryover=1.0 says a program is exactly
what it was in May; 0.0 says every season starts from nothing. It is fitted.
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

MEAN = 1500.0
SCALE = 400.0


@dataclass(frozen=True)
class EloConfig:
    k: float = 60.0
    home_adv: float = 50.0
    carryover: float = 0.95
    mov: str = "rally"      # "none" | "sets" | "rally"


def _expected(diff: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + 10.0 ** (-diff / SCALE))


def _mov_mult(margin: float, winner_edge: float) -> float:
    """Scale K by how convincing the win was, damped by how expected it was."""
    if margin <= 0:
        return 1.0
    return float(np.log(margin + 1.0) * (2.2 / (0.001 * winner_edge + 2.2)))


def match_frame(src: pd.DataFrame) -> pd.DataFrame:
    """Collapse a two-rows-per-match table to one row per match, home side up.

    Reads either shape the project produces: data/match_metrics.parquet (home_team /
    away_team, raw rally counts) or app_data/matches.parquet (a location column and a
    precomputed rally_win_pct, and the only one of the two that carries 2026).
    """
    d = src.copy()
    if "match_date" in d.columns:                       # app_data/matches.parquet
        d = d.dropna(subset=["opponent", "won", "location", "rally_win_pct"])
        d = d[d.location == "home"]
        d = pd.DataFrame({
            "season": d.season.to_numpy(),
            "date": pd.to_datetime(d.match_date, errors="coerce").to_numpy(),
            "home": d.team.to_numpy(),
            "away": d.opponent.to_numpy(),
            "home_won": d.won.to_numpy().astype(float),
            "set_margin": (d.sets_for - d.sets_against).abs().to_numpy(),
            "rally_share": d.rally_win_pct.to_numpy().astype(float),
        })
    else:                                               # data/match_metrics.parquet
        d = d.dropna(subset=["opponent_matched", "won", "home_team",
                             "so_won", "ps_won", "recv_rallies", "serve_rallies"])
        d = d[d.team == d.home_team]
        share = (d.so_won + d.ps_won) / (d.recv_rallies + d.serve_rallies).replace(0, np.nan)
        d = pd.DataFrame({
            "season": d.season_label.to_numpy(),
            "date": pd.to_datetime(d.date.str.extract(r"(\d+/\d+/\d+)")[0],
                                   format="%m/%d/%Y", errors="coerce").to_numpy(),
            "home": d.team.to_numpy(),
            "away": d.opponent_matched.to_numpy(),
            "home_won": d.won.to_numpy().astype(float),
            "set_margin": (d.sets_for - d.sets_against).abs().to_numpy(),
            "rally_share": share.to_numpy(),
        })
    d = d[d.home != d.away].dropna(subset=["date", "rally_share"])
    return d.sort_values(["date", "home", "away"]).reset_index(drop=True)


def run(matches: pd.DataFrame, cfg: EloConfig = EloConfig()
        ) -> tuple[dict[str, float], pd.DataFrame]:
    """Walk the schedule in order. Returns final ratings and every pre-match prediction.

    Each row of the prediction frame is recorded BEFORE the match updates the ratings,
    so the whole frame is an honest out-of-sample backtest.
    """
    rating: dict[str, float] = {}
    season = None
    rows = []

    for m in matches.itertuples(index=False):
        if m.season != season:
            if season is not None and cfg.carryover < 1.0:
                for t in rating:
                    rating[t] = MEAN + cfg.carryover * (rating[t] - MEAN)
            season = m.season

        ra = rating.setdefault(m.home, MEAN)
        rb = rating.setdefault(m.away, MEAN)
        diff = ra - rb + cfg.home_adv
        exp = _expected(diff)

        if cfg.mov == "none":
            margin, mult = 0.0, 1.0
        else:
            margin = (m.set_margin if cfg.mov == "sets"
                      else abs(m.rally_share - 0.5) * 100.0)
            # the winner's rating edge, which is what gets damped
            edge = diff if m.home_won else -diff
            mult = _mov_mult(margin, edge)

        rows.append((m.season, m.date, m.home, m.away, ra, rb, exp, m.home_won))
        delta = cfg.k * mult * (m.home_won - exp)
        rating[m.home] = ra + delta
        rating[m.away] = rb - delta

    preds = pd.DataFrame(rows, columns=["season", "date", "home", "away",
                                        "elo_home", "elo_away", "p_home", "home_won"])
    return rating, preds


def score(preds: pd.DataFrame) -> dict[str, float]:
    """Accuracy and log loss on pre-match predictions. Log loss is the honest one."""
    p = preds.p_home.to_numpy().clip(1e-6, 1 - 1e-6)
    y = preds.home_won.to_numpy()
    return {
        "n": int(len(preds)),
        "accuracy": float(np.mean((p > 0.5) == (y == 1))),
        "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
        "brier": float(np.mean((p - y) ** 2)),
    }


def tune(matches: pd.DataFrame, fit_seasons: list[str], grid: dict | None = None,
         base: EloConfig = EloConfig()) -> tuple[EloConfig, pd.DataFrame]:
    """Grid search on log loss over the fitting seasons only.

    Ratings still walk from the first season in `matches` so the fitting seasons are
    not scored on cold-start ratings, but only their predictions count.
    """
    grid = grid or {"k": [10, 15, 20, 25, 30, 40],
                    "home_adv": [0, 20, 35, 50, 65],
                    "carryover": [0.0, 0.4, 0.6, 0.75, 0.9, 1.0],
                    "mov": ["none", "sets", "rally"]}
    keys = list(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        cfg = replace(base, **dict(zip(keys, combo)))
        _, preds = run(matches, cfg)
        s = score(preds[preds.season.isin(fit_seasons)])
        results.append({**dict(zip(keys, combo)), **s})
    res = pd.DataFrame(results).sort_values("log_loss").reset_index(drop=True)
    best = replace(base, **{k: res.loc[0, k] for k in keys})
    return best, res


def build(matches_parquet: Path, cfg: EloConfig = EloConfig()) -> pd.DataFrame:
    """Final Elo for every team-season, as of that season's last match."""
    matches = match_frame(pd.read_parquet(matches_parquet))
    frames = []
    for season, grp in matches.groupby("season", sort=True):
        # replay from the first season every time: a season's rating has to carry
        # everything before it, and six replays of 24k matches costs about a second.
        rating, _ = run(matches[matches.season <= season], cfg)
        played = pd.concat([grp.home, grp.away]).value_counts().rename("n_matches")
        f = pd.DataFrame({"season": season, "team": played.index,
                          "elo": [rating[t] for t in played.index],
                          "n_matches": played.to_numpy()})
        frames.append(f[f.n_matches >= 5])
    out = pd.concat(frames, ignore_index=True)
    out["rank_elo"] = out.groupby("season").elo.rank(ascending=False, method="min").astype(int)
    return out.sort_values(["season", "rank_elo"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matches", type=Path, default=Path("app_data/matches.parquet"))
    ap.add_argument("--out", type=Path, default=Path("app_data/elo_ratings.parquet"))
    ap.add_argument("--k", type=float, default=EloConfig.k)
    ap.add_argument("--home-adv", type=float, default=EloConfig.home_adv)
    ap.add_argument("--carryover", type=float, default=EloConfig.carryover)
    ap.add_argument("--mov", default=EloConfig.mov, choices=["none", "sets", "rally"])
    args = ap.parse_args()

    cfg = EloConfig(k=args.k, home_adv=args.home_adv,
                    carryover=args.carryover, mov=args.mov)
    ratings = build(args.matches, cfg)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ratings.to_parquet(args.out, compression="zstd", index=False)
    print(f"wrote {args.out}  {len(ratings):,} team-seasons   {cfg}")
    latest = ratings.season.max()
    print(f"\n{latest} top 15 by Elo:")
    print(ratings[ratings.season == latest].head(15)[
        ["rank_elo", "team", "elo", "n_matches"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
