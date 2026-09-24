"""Blend the ridge rating, Elo and strength of schedule into one power ranking.

WHY BLEND AT ALL
----------------
The two rating models disagree by design. The ridge fit in power_ratings.py solves
every team against every opponent at once but has no memory: each season starts from
nothing and August weighs the same as December. Elo carries the prior season and
weights recent matches more, but updates one match at a time and never sees the
schedule as a whole.

Neither dominates. Refitting the ridge weekly so both models see only what was known
before each match, across 12,508 out-of-sample forecasts in 2022-2025:

    ridge alone   77.0-78.9%        Elo alone   77.5-79.2%

Put both in one logistic fit and each keeps a large coefficient with the other
present. They are not measuring the same thing, so the blend beats either one.

WHY SCHEDULE IS IN HERE TOO, WHICH LOOKS LIKE DOUBLE COUNTING
-------------------------------------------------------------
The ridge already solves opponents simultaneously, so schedule strength ought to be
inside the rating and a separate term ought to be redundant. It is not. Added to the
composite, mean opponent rating carries z = 7.4 to 7.8 in every one of the four
seasons, and improves held-out log loss every time. The coefficient is POSITIVE: a
team that played a harder schedule wins more often than its rating says it should,
which means the rating under-credits hard schedules.

The cause is the ridge penalty. It shrinks opponent effects toward average, which
systematically understates how good strong opponents were, so their opponents get
under-credited in turn. Sweeping the penalty shows it directly -- the SOS signal that
remains after the ridge is:

    ridge lambda    0.0   0.1   0.25   0.5   1.0   2.0   5.0
    SOS z           7.4   8.7   10.5  13.0  16.9  22.1  29.7

Note it does not reach zero at lambda 0. Some of it is real: the opponent model is
additive, a full schedule graph takes weeks to connect, and neither is fixed by
turning the penalty off. That residual is what the SOS term is for.

(power_ratings.py still runs at lambda 1.0. Dropping it to about 0.25 is worth
roughly .008 of log loss on the ridge alone, but it rescales every published rating
in every season, so it is a deliberate decision rather than something to slip in
here.)

THE WEIGHTS
-----------
Fitted, not chosen. Train on three seasons, test on the fourth, every time:

    hold out 2022   elo 41%  ridge 48%  sos 11%
    hold out 2023   elo 40%  ridge 49%  sos 11%
    hold out 2024   elo 41%  ridge 48%  sos 11%
    hold out 2025   elo 40%  ridge 49%  sos 12%

So 40 / 48 / 12. A rounder 40/40/20 was tried and is worse in all four seasons, which
is the useful part: schedule earns a real share, and a small one.

THE SCALE
---------
The blend happens in z-scores, then is rescaled to the spread of rating_overall so the
composite still reads in points of side-out rate. That rescaling is a convenience, not
an identity: a composite of +26 means "as far above average as a +26 ridge rating
would be", not "26 more side-outs per hundred". The components stay in the table.

SOS itself is reported in the ridge's own units, so "+8.2" means the average team on
this schedule was 8.2 points of side-out rate above a typical D1 team.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ELO_WEIGHT = 0.40
RIDGE_WEIGHT = 0.48
SOS_WEIGHT = 0.12


def strength_of_schedule(matches: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    """Mean ridge rating of the opponents a team actually played, per season.

    Every match counts once, so playing a strong team twice counts twice. Opponents
    with no rating (non-D1, or too few matches to be rated) drop out of the mean
    rather than being scored as average, because we do not know that they are.
    """
    r = ratings.set_index(["season", "team"]).rating_overall
    m = matches.dropna(subset=["opponent"])[["season", "team", "opponent"]].copy()
    m["opp_rating"] = r.reindex(
        pd.MultiIndex.from_arrays([m.season, m.opponent])).to_numpy()
    g = m.dropna(subset=["opp_rating"]).groupby(["season", "team"]).opp_rating
    return pd.DataFrame({"sos": g.mean(), "sos_matches": g.size()}).reset_index()


def blend(ratings: pd.DataFrame, elo: pd.DataFrame, matches: pd.DataFrame,
          elo_weight: float = ELO_WEIGHT, ridge_weight: float = RIDGE_WEIGHT,
          sos_weight: float = SOS_WEIGHT) -> pd.DataFrame:
    """Add elo, sos, rating_composite and the ranks to the power ratings table."""
    drop = ("elo", "rank_elo", "sos", "sos_matches", "rank_sos",
            "rating_composite", "rank_composite")
    d = ratings.drop(columns=[c for c in drop if c in ratings.columns])
    d = d.merge(elo[["season", "team", "elo"]], on=["season", "team"], how="left")
    d = d.merge(strength_of_schedule(matches, ratings), on=["season", "team"], how="left")

    g = d.groupby("season")
    ridge_sd = g.rating_overall.transform("std")
    zr = (d.rating_overall - g.rating_overall.transform("mean")) / ridge_sd
    ze = (d.elo - g.elo.transform("mean")) / g.elo.transform("std")
    zs = (d.sos - g.sos.transform("mean")) / g.sos.transform("std")

    # A missing component falls back to the ridge z rather than to zero, which would
    # read as "exactly average" and quietly drag the team toward the middle.
    z = (elo_weight * ze.fillna(zr) + ridge_weight * zr + sos_weight * zs.fillna(zr))
    d["rating_composite"] = z * ridge_sd

    for col, name in (("rating_composite", "rank_composite"), ("elo", "rank_elo"),
                      ("sos", "rank_sos")):
        d[name] = d.groupby("season")[col].rank(ascending=False, method="min")
    d["rank_composite"] = d.rank_composite.astype(int)
    return d.sort_values(["season", "rank_composite"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ratings", type=Path, default=Path("app_data/power_ratings.parquet"))
    ap.add_argument("--elo", type=Path, default=Path("app_data/elo_ratings.parquet"))
    ap.add_argument("--matches", type=Path, default=Path("app_data/matches.parquet"))
    ap.add_argument("--elo-weight", type=float, default=ELO_WEIGHT)
    ap.add_argument("--ridge-weight", type=float, default=RIDGE_WEIGHT)
    ap.add_argument("--sos-weight", type=float, default=SOS_WEIGHT)
    args = ap.parse_args()

    ratings = pd.read_parquet(args.ratings)
    out = blend(ratings, pd.read_parquet(args.elo), pd.read_parquet(args.matches),
                args.elo_weight, args.ridge_weight, args.sos_weight)

    for col, label in (("elo", "Elo"), ("sos", "a schedule")):
        missing = out[out[col].isna()].groupby("season").size()
        if len(missing):
            print(f"  teams with no {label}, held on their ridge rating: "
                  + ", ".join(f"{s} {int(n)}" for s, n in missing.items()))

    out.to_parquet(args.ratings, compression="zstd", index=False)
    print(f"wrote {args.ratings}  {len(out):,} team-seasons   "
          f"elo {args.elo_weight:.0%} / ridge {args.ridge_weight:.0%} / "
          f"sos {args.sos_weight:.0%}")

    latest = out.season.max()
    print(f"\n{latest} top 15 by composite:")
    print(out[out.season == latest].head(15)[
        ["rank_composite", "team", "rating_composite", "rank_overall",
         "rank_elo", "sos", "rank_sos"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
