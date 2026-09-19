"""Blend the ridge power rating and Elo into one composite power ranking.

WHY BLEND AT ALL
----------------
The two models disagree by design. The ridge fit in power_ratings.py solves every
team against every opponent at once but has no memory: each season starts from
nothing and August weighs the same as December. Elo carries the prior season and
weights recent matches more, but updates one match at a time and never sees the
schedule as a whole.

Neither dominates. Refitting the ridge weekly so both models see only what was known
before each match, across 12,508 out-of-sample forecasts in 2022-2025:

    ridge alone   77.0-78.9%        Elo alone   77.5-79.2%

Put both in one logistic fit and each keeps a large coefficient with the other
present (Elo z=4.2-6.1, ridge z=4.3-6.4). They are not measuring the same thing, so
the blend beats either one.

THE WEIGHT
----------
Fitted, not chosen. Train on three seasons, test on the fourth, every time:

    hold out 2022  ->  52% Elo        hold out 2024  ->  50% Elo
    hold out 2023  ->  49% Elo        hold out 2025  ->  49% Elo

So: half and half, on ratings standardised within the season.

The weight does drift through a season -- fitted inside week bands it runs 55% Elo in
weeks 3-5 and 21% by week 12, which is what you would expect as the ridge accumulates
a full schedule and Elo's carried prior goes stale. It is not worth modelling. Fitting
that slide on three seasons and testing it on the fourth moves log loss by less than
0.0005 either way, because by the time the ridge earns the larger share the two
ratings agree anyway. A flat 50/50 matched the fitted weight in all four seasons.

THE SCALE
---------
The blend happens in z-scores, then is rescaled to the spread of rating_overall so the
composite still reads in points of side-out rate. That rescaling is a convenience, not
an identity: a composite of +26 means "as far above average as a +26 ridge rating
would be", not "26 more side-outs per hundred". The components stay in the table.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ELO_WEIGHT = 0.50


def blend(ratings: pd.DataFrame, elo: pd.DataFrame,
          elo_weight: float = ELO_WEIGHT) -> pd.DataFrame:
    """Add elo, rating_composite and rank_composite to the power ratings table."""
    d = ratings.drop(columns=[c for c in ("elo", "rank_elo", "rating_composite",
                                          "rank_composite") if c in ratings.columns])
    d = d.merge(elo[["season", "team", "elo"]], on=["season", "team"], how="left")

    g = d.groupby("season")
    ridge_sd = g.rating_overall.transform("std")
    zr = (d.rating_overall - g.rating_overall.transform("mean")) / ridge_sd
    ze = (d.elo - g.elo.transform("mean")) / g.elo.transform("std")
    z = elo_weight * ze + (1 - elo_weight) * zr
    # A team with no Elo (fewer than five matches when Elo was built) keeps its ridge
    # rating rather than dropping off the board.
    d["rating_composite"] = z.fillna(zr) * ridge_sd

    d["rank_composite"] = d.groupby("season").rating_composite.rank(
        ascending=False, method="min").astype(int)
    d["rank_elo"] = d.groupby("season").elo.rank(ascending=False, method="min")
    return d.sort_values(["season", "rank_composite"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ratings", type=Path, default=Path("app_data/power_ratings.parquet"))
    ap.add_argument("--elo", type=Path, default=Path("app_data/elo_ratings.parquet"))
    ap.add_argument("--elo-weight", type=float, default=ELO_WEIGHT)
    args = ap.parse_args()

    ratings = pd.read_parquet(args.ratings)
    elo = pd.read_parquet(args.elo)
    out = blend(ratings, elo, args.elo_weight)

    missing = out.elo.isna().groupby(out.season).sum()
    if missing.any():
        print("  teams with no Elo, kept on their ridge rating: "
              + ", ".join(f"{s} {int(n)}" for s, n in missing.items() if n))

    out.to_parquet(args.ratings, compression="zstd", index=False)
    print(f"wrote {args.ratings}  {len(out):,} team-seasons   "
          f"elo weight {args.elo_weight:.0%}")

    latest = out.season.max()
    top = out[out.season == latest].head(15)
    print(f"\n{latest} top 15 by composite:")
    print(top[["rank_composite", "team", "rating_composite", "rank_overall",
               "rank_elo"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
