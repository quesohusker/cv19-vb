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
none.

EVERYONE WHO SERVES IS GRADED ON SERVING, ON ACES PER SET. It is the one benchmark
every board shares -- but not everyone serves. Forty percent of middles and forty-five
percent of opposites record no ace and no service error in a whole season, because a
serving sub goes in for them every rotation, and scoring those players a zero would
rank them on their coach's substitution pattern. Three serving events is the bar for
being graded on it; below that a player carries one fewer benchmark, which the rating
already handles by averaging over the metrics she has. Aces per set is the choice on both criteria at once: it
repeats better than anything else in the serving family (.77 to .86 at half-season,
.87 to .93 over a full one), and at team level it is the serving construct that tracks
winning serve-phase rallies best (+0.34 against point-score %, +0.21 against win %,
over 1,348 team-seasons).

The balance measures lose on both. Ace-to-service-error looks respectable at .63 to
.67 for the front-row groups, but that is an artifact of guarding the divide-by-zero:
clipping errors at one orders every zero-error server by her ace count, so the ratio
is partly measuring ace volume through its own guard. Written as a proper bounded
share, aces over aces-plus-errors, the same quantity falls to .20 to .33 at
half-season -- because aces per set and service errors per set correlate between +0.80
and +0.91, so serving is nearly one axis, how hard she goes after it, and subtracting
one from the other cancels most of the signal rather than isolating quality. The
validity test says the same thing from the other side: service errors per set
correlate -0.05 with a team's point-score rate, which is to say missed serves cost
almost nothing measurable while aces are worth a good deal.

Per-attempt serving rates are not used at all, whatever their appeal, because the
source cannot support them: not one team-season in the file reports serve attempts
consistently.

LIBERO AND DS ARE ONE GROUP. Their workloads are identical -- 3.78 / 3.80 / 3.75
receptions per set for L, L/DS and DS -- and 140 of 340 teams label every back-row
player "L/DS", so splitting them would rank players by their sports information
director's habits. The dig gap between the labels (2.50 vs 1.86 per set) is a
quality difference the ranking should surface, not a role difference that
justifies separate boards.

PASSING LOAD IS A CONTROL FOR OUTSIDES, NEVER A BENCHMARK. Grading receptions per set
as a virtue -- more serve receive, better player -- looks reasonable and is wrong,
because the efficiency adjustment below already accounts for the passing load. Doing
both counts the same fact twice in the same direction. It cost Pittsburgh's Olivia
Babcock, 5.17 kills per set at .334 for the country's second-ranked team, a rank of
379th out of 1,667 in 2025: she takes no serve receive, so she was docked 28 points of
hitting efficiency for being a low passer AND scored near the bottom percentile on
passing volume, one fifth of her rating. Wisconsin's Mimi Colyer, 5.54 kills per set at
.340, came out 129th the same way. Both are terminators, and about half of teams do not
give their opposite a label of her own, so the outside board is full of them.

So volume controls and quality is graded: outsides are scored on reception ERROR RATE,
among those who take at least forty serve receives, and a player below that carries one
fewer benchmark rather than a zero, exactly as with serving. It is a weak metric, .33
at half-season and .50 over a full one, and it is still better than grading a role as
if it were an ability.

OUTSIDES ARE ADJUSTED FOR PASSING LOAD. Among high-volume outside attackers,
hitting efficiency falls from .214 to .186 as reception load rises (r = -0.22):
the outside who passes and swings gets the out-of-system ball. Raw efficiency
therefore penalises six-rotation outsides against right-side specialists who never
pass, so efficiency is scored as a residual against the league's efficiency-versus-
passing-load line. Attack volume alone does not hurt efficiency (r = +0.15) and is
not adjusted for.

ASSISTS PER SET ATTEMPT WAS TESTED AND DROPPED. It reads like the one measure of
setting QUALITY the box score offers -- what share of her sets a hitter converted --
and it validates beautifully, +0.50 against team hitting efficiency and +0.43 against
win percentage. It is a trap. Two setters on the same roster post nearly the same
assist rate (teammate correlation +0.724, the highest of anything measured in this
project), and once the team mean is removed a setter's own year-over-year signal falls
to +0.089. It correlates with winning because it IS the team: a setter on a good
offence has a high assist rate because her hitters convert, and grading her on it
credits her with their hitting. It fails the same test as charted reception quality,
by a wider margin.

CHARTED SET QUALITY REPLACES IT, and is the best-behaved metric in this project. An
earlier pass here dismissed it as covering 6-7% of players; that was the wrong
denominator. The file lists every player who ever touched a set, including hitters
making an emergency one, and against that population 6-7% qualify. Against setters it
covers 68-90% of everyone ranked and ONE HUNDRED PERCENT of primary setters, in every
season.

It measures the setter and nothing else. Year-over-year +0.780, the highest recorded
here; teammate correlation -0.021, meaning a setter's number tells you nothing about
the other setter on her roster. Remove the team mean and it still holds +0.694, where
assist rate fell to +0.089. The scale does not drift either -- the league median runs
1.304, 1.306, 1.313, 1.317, 1.328 across 2022-2026 -- so a fixed cross-season reference
means what it says.

And it tracks winning better than anything else on the board: +0.761 against team
hitting efficiency and +0.637 against win percentage, against assists per set's +0.578
and +0.531. With a teammate correlation of zero, that link is the setter's own
contribution rather than her hitters' credited to her, which is exactly what assist
rate could not claim.

MISTAKES ARE MEASURABLE, BUT NOT THE ONES THAT GET CHARGED. A setting error -- a
double, a lift -- is called 364 times in the entire dataset against 4.75 million sets;
the median qualified setter commits none all season, and the rate repeats at +0.091.
A BAD SET, one the hitter can do little with, happens 3.4% of the time and repeats at
+0.700 with a teammate correlation of -0.029. It is already inside the rating, since a
bad set scores zero in it, and is carried separately as a displayed column.

Assists per set stays alongside: it is demonstrably hers -- teammate correlation -0.698,
since two setters split the same job -- and tracks winning at +0.53.

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
MIN_SERVE_EVENTS = 3        # aces + service errors, the evidence that she serves
PASS_SPLIT = 0.37           # percentile of each season's attackers that divides the pin boards
ATTACKER_SWINGS = 4.0       # swings per set that make a player a reference attacker
FRONT_ROW_SWINGS = 2.0      # swings per set a front-row hitter must actually take
SIX_ROT = "Six-rotation hitter"
FRONT_ROW = "Front-row hitter"
MIN_RECEPTIONS = 40         # serve receives, the evidence that she is a passer

# source position codes -> the group they are ranked in
POSITION_GROUPS = {
    # Every pin label lands in one bucket here and is split by what she actually did.
    # See split_pins().
    "OH": "Pin", "OPP": "Pin", "RS": "Pin", "O": "Pin",
    "MB": "Middle blocker", "MH": "Middle blocker",
    "S": "Setter",
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
    # Pick the display spelling by how it is written, then by how often. The 2022 and
    # 2023 files carry more rows under "julia Bergmann" than "Julia Bergmann", so
    # frequency alone puts a lower-case first name at the top of a published board.
    by_name = pm.groupby(["uid", "player"], as_index=False).size()
    by_name["titled"] = by_name.player.map(
        lambda n: all(w[:1].isupper() for w in n.split() if w))
    by_name = (by_name.sort_values(["titled", "size"], ascending=[False, False])
                      .drop_duplicates("uid"))
    pm = (pm.drop(columns=["player"])
            .merge(by_label[["uid", "label_group"]].rename(
                columns={"label_group": "position"}), on="uid")
            .merge(by_name[["uid", "player"]], on="uid"))
    return pm


def split_pins(pm: pd.DataFrame) -> pd.DataFrame:
    """Divide the pin hitters by what they did, not by what the roster called them.

    THE LABEL DOES NOT SURVIVE CONTACT WITH THE DATA. Among players taking four or more
    swings a set, 43% of those listed "OH" take under half a reception per set -- they
    are doing the opposite's job under the outside's name, because only about half of
    teams give their opposite a label of her own. Ranking on the label therefore ranks
    a coach's paperwork. Split on serve receive instead and the two groups separate
    about twice as sharply: the gap in digs per set goes from 0.75 to 1.35, attacks per
    set from 0.86 to 1.93.

    THE LINE IS CHOSEN, NOT FOUND, and that is worth stating plainly. The distribution
    is a spike at zero, a large mass above four, and a flat plateau between -- not two
    clean humps. The thinnest band moves every season (1.75, 2.25, 1.00, 3.00, 2.50
    across 2022-2026), so there is no natural boundary to snap to. About 8.7% of
    attackers sit within half a reception of the line and could defensibly fall either
    way; everyone else is unambiguous. Receptions per set is shown on both boards so a
    reader can see how close to the line any player sits.

    THE THRESHOLD IS A PERCENTILE, NOT A FIXED RATE, because serve receive is not
    recorded the same way every season. The league total barely moves -- about 728,000
    receptions a year -- but how widely it is attributed does: 18.9% of players with
    twenty or more sets recorded no reception at all in 2022, 22.3% in 2024, and only
    5.9% in 2025. Same volleyball, spread over more names. A fixed rate of 1.5 would
    therefore put the same player on different boards in different seasons, and would
    also tilt the fixed 2022-2025 reference distributions that every rating is scored
    against. So the cut is taken at the 37th percentile of each season's ATTACKERS --
    players swinging four or more times a set, whose receptions are recorded
    consistently -- and the resulting rate is then applied to every pin hitter that
    season. 37% is where 1.5 receptions per set sat on average, so the line means what
    it did before while no longer drifting with the scorer's habits.

    The names describe the job rather than the roster. A front-row-only outside belongs
    with the opposites because that was her season, and calling that group "Opposite"
    would be the same kind of lie the labels already tell.
    """
    pm = pm.copy()
    tot = pm.groupby("uid").agg(S=("S", "sum"), rec=("RetAtt", "sum"),
                                atk=("TotalAttacks", "sum"))
    tot = tot[tot.S > 0]
    tot["rps"] = tot.rec / tot.S
    tot["aps"] = tot.atk / tot.S
    season = pm.groupby("uid").season.first()
    pin_uids = set(pm.loc[pm.position == "Pin", "uid"])
    tot = tot[tot.index.isin(pin_uids)].join(season)

    six: set[str] = set()
    dropped: set[str] = set()
    for yr, g in tot.groupby("season"):
        ref = g[(g.aps >= ATTACKER_SWINGS) & (g.S >= MIN_SETS)]
        if len(ref) < 100:
            thr = 1.5
            print(f"  {yr}: too few reference attackers; falling back to {thr} rec/set")
        else:
            thr = float(ref.rps.quantile(PASS_SPLIT))
        passes = g.index[g.rps >= thr]
        six.update(passes)
        # A front-row hitter's whole claim on that board is that she attacks without
        # passing, so she has to attack. Without this floor the board fills with
        # reserves: "no reception recorded" and "does not pass" are the same row in the
        # box score, and in 2022-2024 the recording was sparse enough that the median
        # front-row hitter had 0.4 kills a set -- a benchwarmer -- against 1.6 in 2025.
        # Pooling those into one reference would score every player against a
        # population that changed underneath them. At two swings a set the median holds
        # between 1.63 and 1.73 across 2022-2025. The six-rotation board needs no such
        # floor: passing four balls a set is itself proof of a real role.
        sits = g.index[(g.rps < thr) & (g.aps < FRONT_ROW_SWINGS)]
        dropped.update(sits)
        print(f"  {yr}: split at {thr:.2f} rec/set ({PASS_SPLIT:.0%} of {len(ref):,} "
              f"attackers) -> {len(passes):,} six-rotation, "
              f"{len(g) - len(passes) - len(sits):,} front-row, "
              f"{len(sits):,} too few swings to rank")
    is_pin = pm.position == "Pin"
    pm.loc[is_pin & pm.uid.isin(six), "position"] = SIX_ROT
    pm.loc[is_pin & ~pm.uid.isin(six), "position"] = FRONT_ROW
    pm = pm[~pm.uid.isin(dropped)].copy()
    return pm


def player_seasons(pm: pd.DataFrame) -> pd.DataFrame:
    """One row per player per season, with the raw counting totals."""
    keys = ["uid", "season", "team", "conference", "player", "position"]
    out = (pm.groupby(keys, as_index=False)
             .agg(matches=("date", "size"), **{c: (c, "sum") for c in COUNTS}))
    return out


def touch_quality(gis_dir: Path, years: list[int], kind: str = "dig") -> pd.DataFrame:
    """Per-touch quality grades, charted from play-by-play, on the classic 0-2 scale.

    The source publishes great/good/bad counts per player per season for reception,
    serve, dig, block and set. Only DIG survives testing, and the test that kills the
    others is worth stating because it is not the obvious one.

    THE TEST. A quality grade is a human judgement, and statisticians differ in how
    generously they award "great". That contamination shows up as a teammate
    correlation -- how much knowing one player's number tells you about the player
    beside her. Charted reception quality has a teammate correlation of +0.535, double
    any box-score metric (box-score reception error rate is +0.26, hitting efficiency
    +0.32) and HIGHER than its own year-over-year of +0.486. A number more predictable
    from your teammate than from your own past season is measuring the team, or the
    person keeping the book, and not you. Strip the team mean and reception quality's
    year-over-year collapses from +0.462 to +0.180: about sixty percent of it was never
    the player. Block quality fails the same way (+0.259 centred) and so does serve
    quality (+0.206).

    Dig quality passes cleanly and is the one addition made here: teammate +0.050 raw,
    and year-over-year of +0.686 that does not move when the team effect is removed.
    Digs are graded off what the rally does next rather than off an opinion about the
    ball, which is likely why. It is graded only where most of a position is covered --
    back row and setter, 60% to 83% of ranked players -- and never for middles or
    opposites, where coverage runs 1% to 39%.
    """
    rows = []
    for year in years:
        f = gis_dir / f"wvb_{kind}_quality_{year}.json"
        if not f.exists():
            continue
        for key, v in json.loads(f.read_text()).items():
            if not v.get("qualified") or not v.get("total"):
                continue
            name = key.split("|")[0]
            row = {"season": str(year), "team": v.get("school", ""), "_key": name,
                   f"{kind}_rating": (2 * v["great"] + v["good"]) / v["total"],
                   f"{kind}_touches": v["total"]}
            if "bad" in v:
                row[f"{kind}_bad_pct"] = v["bad"] / v["total"]
            rows.append(row)
    if not rows:
        print(f"  no {kind}-quality files found; skipping")
        return pd.DataFrame(columns=["season", "team", "_key", f"{kind}_rating"])
    out = pd.DataFrame(rows)
    print(f"  {kind} quality: {len(out):,} qualified player-seasons")
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
    d["reception_err_rate"] = d.RErr / d.RetAtt.where(d.RetAtt >= MIN_RECEPTIONS)
    # Serving is graded only for players who serve. Forty percent of middles and
    # forty-five percent of opposites record no ace and no service error all season --
    # they are replaced by a serving sub every rotation -- and scoring them a zero
    # would rank them on their coach's substitution pattern. With serve attempts
    # unusable (see below), an ace or an error is the only evidence in the file that a
    # player served at all, so three of them is the bar. Everyone below it carries no
    # serving benchmark and is graded out of one fewer.
    d["serve_events"] = d.Aces + d.SErr
    serves = d.serve_events >= MIN_SERVE_EVENTS
    d["serves"] = serves
    d["aces_per_set"] = (d.Aces / s).where(serves)
    d["serve_err_per_set"] = (d.SErr / s).where(serves)
    # ServeAtt deliberately unused: no team in the source reports it consistently --
    # every one of the 1,400-odd team-seasons logs it on between 5% and 95% of rows --
    # so any per-attempt serving rate is division by a number that is missing at
    # unknown times. Per-set serving needs no such denominator.
    return d


def adjust_for_in_system(d: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, dict | None]:
    """Score a hitter's efficiency against the quality of ball she was actually given.

    In system means the designated setter delivered it. Out of system, the pass or dig
    was bad and a libero or an outside put up the second touch instead. The difference
    is large and league-wide: across 1.3 million 2024 attacks, in system produced a
    36.3% kill rate at .211, out of system 30.2% at .157.

    THIS SUPERSEDES THE PASSING-LOAD ADJUSTMENT, which was a proxy for exactly this and
    is kept only as a fallback. Passing load asks "how often is she likely to be
    hitting a ball she just passed"; in-system share measures which ball she actually
    got. When both are available the direct measurement wins.

    It is used as a CONTROL, never graded. A hitter's in-system share correlates +0.251
    with her own efficiency, so a low share marks someone getting worse balls, not
    someone heroically terminating garbage -- grading it would reward whoever is fed
    best. What it earns her is credit: a hitter at 68% in system hitting .250 did more
    than one at 90% hitting .250, and without this the boards cannot tell them apart.

    It is hers, not her team's: teammate correlation +0.056, only 8.6% of the variance
    explained by the team she plays for, and a split-half of 0.680 within a season
    (0.810 over a full one).

    COVERAGE GATES IT. The adjustment is applied only when every ranked season has it,
    because the reference distributions pool 2022-2025 and scoring the current season
    on a different quantity than the reference was built from is the one mistake that
    quietly corrupts every rating. Until the pipeline has parsed the current season's
    play-by-play, everything falls back to the passing-load proxy.
    """
    d = d.copy()
    d["in_system_kill_pct"] = pd.NA
    if not path.exists():
        print(f"  no {path}; using the passing-load proxy")
        return d, None
    isk = pd.read_parquet(path)
    isk = isk[isk.kills_charted >= 30]
    # Collapse before joining. Two players on one roster can normalise to the same
    # name, and a left merge on a duplicated key silently multiplies rows -- which
    # then breaks every later .loc that assumes one row per player.
    isk = (isk.sort_values("kills_charted", ascending=False)
              .drop_duplicates(["season", "team", "_key"]))
    lookup = isk.set_index(["season", "team", "_key"]).in_system_kill_pct
    idx = pd.MultiIndex.from_arrays([d.season, d.team, d._key])
    d["in_system_kill_pct"] = lookup.reindex(idx).to_numpy()

    ranked = d[d.S >= MIN_SETS]
    cover = ranked.groupby("season").in_system_kill_pct.apply(lambda c: c.notna().mean())
    print("  in-system coverage of ranked players by season: "
          + ", ".join(f"{k} {v:.0%}" for k, v in cover.items()))
    thin = [k for k, v in cover.items() if v < 0.40]
    if thin:
        print(f"  {', '.join(thin)} below 40% -- falling back to the passing-load proxy "
              f"everywhere, so every season is scored on the same quantity")
        return d, {"applied": False, "thin_seasons": thin,
                   "coverage": {k: round(float(v), 3) for k, v in cover.items()}}
    return d, {"applied": True,
               "coverage": {k: round(float(v), 3) for k, v in cover.items()}}


def adjust_outside_efficiency(d: pd.DataFrame, in_system: dict | None = None
                              ) -> tuple[pd.DataFrame, dict | None]:
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
    if in_system and in_system.get("applied"):
        # The direct measurement is available for every ranked season, so use it and
        # leave the proxy alone. Fitted across all attacking boards, not just the
        # six-rotation one: a middle fed out of system is hitting a bad ball too.
        # (numpy is imported at module scope; a local import here would shadow it and
        #  break the fallback path below, which is exactly what it did once.)
        att = d[(d.S >= MIN_SETS) & d.hit_pct.notna()
                & d.in_system_kill_pct.notna()
                & d.position.isin((SIX_ROT, FRONT_ROW, "Middle blocker"))]
        fit = att[att.season.isin(REFERENCE_SEASONS)]
        if len(fit) >= 200:
            x = fit.in_system_kill_pct.astype(float).to_numpy()
            X = np.column_stack([np.ones(len(fit)), x])
            y = fit.hit_pct.astype(float).to_numpy()
            b0, b_sys = (float(v) for v in np.linalg.lstsq(X, y, rcond=None)[0])
            mean_sys = float(x.mean())
            rows = d.index.isin(att.index)
            d.loc[rows, "hit_pct_pass"] = (
                d.loc[rows, "hit_pct"].astype(float)
                - b_sys * (d.loc[rows, "in_system_kill_pct"].astype(float) - mean_sys))
            print(f"  in-system efficiency adjustment: hit% = {b0:.4f} "
                  f"{b_sys:+.5f} x in-system kill share   (n={len(fit):,})")
            print(f"    a hitter at {mean_sys - 0.15:.2f} in-system, against a league "
                  f"mean of {mean_sys:.2f}, is credited "
                  f"{abs(b_sys) * 0.15 * 1000:.0f} points of efficiency")
            return d, {"basis": "in-system kill share", "slope": round(b_sys, 5),
                       "mean_in_system": round(mean_sys, 4), "n": int(len(fit)),
                       "applies_to": [SIX_ROT, FRONT_ROW, "Middle blocker"],
                       "note": ("supersedes the passing-load proxy: this measures which "
                                "ball she actually got rather than guessing from how "
                                "much she passed")}
    oh = d[(d.position == SIX_ROT) & d.hit_pct.notna()
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
    "aces_per_set":       (lambda v: v.Aces, lambda v: v.S, 1),
    "serve_err_per_set":  (lambda v: v.SErr, lambda v: v.S, 1),
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
    SIX_ROT: [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct_pass", +1, "Hitting efficiency, adjusted for passing load"),
        ("reception_err_rate", -1, "Reception error rate"),
        ("digs_per_set", +1, "Digs per set"),
        ("aces_per_set", +1, "Aces per set"),
    ],
    "Middle blocker": [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct", +1, "Hitting efficiency"),
        ("blocks_per_set", +1, "Blocks per set"),
        ("attacks_per_set", +1, "Attacks per set"),
        ("aces_per_set", +1, "Aces per set"),
    ],
    FRONT_ROW: [
        ("kills_per_set", +1, "Kills per set"),
        ("hit_pct", +1, "Hitting efficiency"),
        ("blocks_per_set", +1, "Blocks per set"),
        ("attacks_per_set", +1, "Attacks per set"),
        ("aces_per_set", +1, "Aces per set"),
    ],
    "Setter": [
        ("assists_per_set", +1, "Assists per set"),
        ("set_rating", +1, "Set quality (charted, 0-2)"),
        ("digs_per_set", +1, "Digs per set"),
        ("aces_per_set", +1, "Aces per set"),
    ],
    "Back row": [
        ("digs_per_set", +1, "Digs per set"),
        ("dig_rating", +1, "Dig quality (charted, 0-2)"),
        ("receptions_per_set", +1, "Receptions per set"),
        ("reception_err_rate", -1, "Reception error rate"),
        ("aces_per_set", +1, "Aces per set"),
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
    # The same rank taken inside a conference. Computed here rather than in the app so
    # that it is over every eligible player in that conference, not over whichever rows
    # a filter happens to be showing -- the mistake that would make a conference view
    # renumber itself 1..n every time somebody narrowed it further.
    conf = d.conference.replace("", pd.NA)
    key = [d.season, d.position, conf]
    d["rank_in_conference"] = (r.where(conf.notna()).groupby(key).rating
                               .rank(ascending=False, method="min").astype("Int64"))
    d["players_in_conference"] = (d[d.ranked & conf.notna()].groupby(
        [d.season[d.ranked & conf.notna()], d.position[d.ranked & conf.notna()],
         conf[d.ranked & conf.notna()]]).rating
        .transform("size").reindex(d.index).astype("Int64"))
    return d.sort_values(["season", "position", "rank_in_position", "player"])


def rating_uncertainty(pm: pd.DataFrame, d: pd.DataFrame, thresholds: dict,
                       refs: dict) -> pd.DataFrame:
    """How much of each rating is signal and how much is the sample -- measured, not assumed.

    A rank out of 1,133 looks precise and is not. Split every player's matches odd/even,
    score each half exactly as the season is scored, and the spread between the halves is
    a direct read on how much the number moves for a player who did not change. A full
    season carries twice the data, so its standard error is half the standard deviation
    of that half-to-half difference. The estimate is pooled within buckets of sets played,
    because the noise depends on how much she played and almost nothing else.

    Published as a rank band, not an error bar, because a band is what a reader needs:
    "somewhere between 118th and 634th" is honest about three weeks of volleyball in a
    way that "256th" is not.
    """
    half = pm.sort_values(["uid", "date"]).copy()
    half["h"] = half.groupby("uid").cumcount() % 2
    agg = half.groupby(["uid", "position", "h"], as_index=False)[list(COUNTS)].sum()
    agg = derive(agg.rename(columns={"S": "S"}))
    agg["hit_pct_pass"] = agg["hit_pct"]          # no passing fit at half-season
    scored = {}
    for hv in (0, 1):
        g = agg[agg.h == hv].set_index("uid")
        out = {}
        for group, specs in BENCHMARKS.items():
            sub = g[g.position == group]
            if sub.empty:
                continue
            tot = pd.Series(0.0, index=sub.index); n = pd.Series(0, index=sub.index)
            for metric, direction, _lab in specs:
                if metric not in sub.columns:
                    continue
                v = pd.to_numeric(sub[metric], errors="coerce")
                vals = refs[group].get(metric) or []
                pc = v.map(lambda x: percentile_of(vals, x))
                if direction < 0:
                    pc = 100.0 - pc
                tot += pc.fillna(0.0); n += pc.notna().astype(int)
            out.update((tot / n.where(n > 0)).dropna().to_dict())
        scored[hv] = out
    both = pd.DataFrame({"a": pd.Series(scored[0]), "b": pd.Series(scored[1])}).dropna()
    both["diff"] = both.a - both.b
    sets = d.set_index("uid").S
    both["sets"] = sets.reindex(both.index)
    both = both.dropna(subset=["sets"])
    both["bucket"] = pd.cut(both.sets, [0, 30, 45, 60, 80, 100, 130, 1e9])
    se = (both.groupby("bucket", observed=True)["diff"].std() / 2.0).rename("rating_se")
    print("  rating standard error by sets played (from each player's own two halves):")
    for b, v in se.items():
        print(f"    {str(b):>16}  +/- {v:.1f} rating points  (n={int((both.bucket==b).sum()):,})")
    out = d[["uid", "S"]].copy()
    out["bucket"] = pd.cut(out.S, [0, 30, 45, 60, 80, 100, 130, 1e9])
    out = out.merge(se.reset_index(), on="bucket", how="left")
    return out[["uid", "rating_se"]]


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
        "aces_per_set": (lambda v: v.Aces, lambda v: v.S, 8),
        "serve_err_per_set": (lambda v: v.SErr, lambda v: v.S, 8),
        "ace_share": (lambda v: v.Aces, lambda v: v.Aces + v.SErr, 10),
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
    ap.add_argument("--in-system", type=Path,
                    default=Path("data/in_system_kills.parquet"))
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

    pm = split_pins(pm)
    d = derive(player_seasons(pm))
    d["_key"] = d.player.map(norm_name)
    print("\nreading in-system kill share")
    d, in_system = adjust_for_in_system(d, args.in_system)
    d, adjustment = adjust_outside_efficiency(d, in_system)

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
    for col in ("aces_per_set_adj", "serve_err_per_set_adj"):
        if col in d:
            d[col] = d[col].where(d.serves)
    d["opponent_adjusted"] = d.hit_pct_adj.notna() | d.kills_per_set_adj.notna()

    print("\nreading charted touch quality")
    for kind in ("dig", "set"):
        q = touch_quality(args.gis_dir, args.years, kind)
        if not q.empty:
            d = d.merge(q, on=["season", "team", "_key"], how="left")
        if f"{kind}_rating" not in d:
            d[f"{kind}_rating"] = pd.NA
    # only where most of the position is covered; elsewhere it would rank the 1% of
    # middles who happen to be charted against each other
    d.loc[d.position != "Back row", "dig_rating"] = pd.NA
    d.loc[d.position != "Setter", "set_rating"] = pd.NA

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

    print("\nmeasuring how much each rating is worth to one decimal place")
    unc = rating_uncertainty(pm, scored, thresholds, refs)
    scored = scored.merge(unc, on="uid", how="left")
    # turn the error bar into a rank band, which is what a reader can act on
    scored["rank_low"] = pd.NA
    scored["rank_high"] = pd.NA
    for (_sea, _pos), g in scored[scored.ranked].groupby(["season", "position"]):
        r = g.rating.to_numpy()
        se = g.rating_se.fillna(g.rating_se.median()).to_numpy()
        hi = r + 1.645 * se
        lo = r - 1.645 * se
        scored.loc[g.index, "rank_low"] = [int((r > x).sum()) + 1 for x in hi]
        scored.loc[g.index, "rank_high"] = [int((r > x).sum()) + 1 for x in lo]
    scored["rank_low"] = scored.rank_low.astype("Int64")
    scored["rank_high"] = scored.rank_high.astype("Int64")

    print("\nchecking that the graded metrics measure the player, not the night")
    reliability = split_half_reliability(pm)

    keep = ["season", "team", "conference", "player", "position", "matches", "S",
            "kills_per_set", "attacks_per_set", "hit_pct", "hit_pct_pass",
            "blocks_per_set", "digs_per_set", "receptions_per_set",
            "reception_err_rate", "assists_per_set", "assist_rate",
            "aces_per_set", "serve_err_per_set", "dig_rating", "dig_touches",
            "set_rating", "set_touches", "set_bad_pct",
            "in_system_kill_pct",
            "opponent_adjusted",
            "last_played", "team_matches_missed", "recent_sets", "recent_set_share",
            "active", "ranked",
            "benchmarks_met", "benchmarks_of", "setter_attack_bonus", "score", "rating",
            "rank_in_position", "rank_low", "rank_high", "rating_se",
            "players_in_position", "rank_in_conference", "players_in_conference"]
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
        "in_system": in_system,
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
        "rank_band": {
            "method": ("each player's matches split odd/even and scored twice; the "
                       "standard deviation of the half-to-half difference, halved for the "
                       "full sample and pooled by sets played, is the standard error"),
            "interval": "90% (1.645 standard errors either side of the rating)",
            "note": ("a rank out of a thousand looks precise and is not. Publish the "
                     "band, not the rank, whenever the band is wide."),
        },
        "reliability": reliability,
    }, indent=2))

    # the match-by-match lines behind every season row. A season rating is an average,
    # and an average hides a slump; this is what lets the app show one.
    ranked_uids = set(scored[scored.S >= MIN_SETS].uid)
    log = pm[pm.uid.isin(ranked_uids)][
        ["season", "date", "uid", "team", "player", "position", "opponent", "S", "Kills",
         "Errors", "TotalAttacks", "Assists", "Digs", "RetAtt", "RErr", "BlockSolos",
         "BlockAssists", "Aces", "SErr"]].sort_values(["uid", "date"])
    log.to_parquet(args.out_dir / "player_matches.parquet", compression="zstd", index=False)
    print(f"wrote {args.out_dir / 'player_matches.parquet'}  {len(log):,} player-matches")

    print(f"\nwrote {args.out_dir / 'players.parquet'}  {len(out):,} player-seasons")
    print(f"wrote {args.out_dir / 'player_benchmarks.json'}")
    for season in sorted(out.season.unique()):
        s = out[(out.season == season) & out.ranked]
        counts = ", ".join(f"{g} {len(x):,}" for g, x in s.groupby("position"))
        print(f"  {season}: {counts}")


if __name__ == "__main__":
    main()
