"""QuesoHusker's Volleyball — Analysis & Benchmarks.

Read-only front end over the precomputed tables in app_data/. Mirrors the structure
and design system of the CFB app: global season + two-team selection, a stat
comparison, a benchmark scorecard, and opponent-adjusted power rankings. No game
predictions -- volleyball match outcomes are not what this project set out to forecast.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from app import data as D
from app import llm as L
from app import theme as T

st.set_page_config(page_title="QuesoHusker's Volleyball", page_icon="🏐", layout="wide")
st.markdown(T.CSS, unsafe_allow_html=True)

GRADE_MAX = len(D.graded_benchmarks())

# label, own column, opponent column (None = single row), formatter
STAT_CATALOG = [
    ("Side-out %",            "sideout_pct",     "opp_sideout_pct",     "pct1"),
    ("Point-score %",         "point_score_pct", "opp_point_score_pct", "pct1"),
    ("First-ball side-out %", "fbso_pct",        "opp_fbso_pct",        "pct1"),
    ("Transition side-out %", "trans_so_pct",    None,                  "pct1"),
    ("Hitting efficiency",    "hit_pct",         "opp_hit_pct",         "dec3"),
    ("Kill % of attacks",     "kill_pct",        "opp_kill_pct",        "pct1"),
    ("Attack error rate",     "att_err_pct",     None,                  "pct1"),
    ("Blocks per set",        "blocks_per_set",  "opp_blocks_per_set",  "dec2"),
    ("Digs per set",          "digs_per_set",    "opp_digs_per_set",    "dec1"),
    ("Ace % of serves",       "ace_pct",         "opp_ace_pct",         "pct1"),
    ("Reception error rate",  "rec_err_pct",     "opp_rec_err_pct",     "pct1"),
    ("Rally win %",           "rally_win_pct",   None,                  "pct1"),
    # set-level context: the last-match cell reads as Yes/No, the season cell as a rate
    ("Won set 1",             "won_set1",        None,                  ("yn", "pct1")),
    ("First to 20 (share of sets)", "first20_share", None,              "pct1"),
]
# rows where a LOWER value is better
LOWER_IS_BETTER = {"Attack error rate", "Reception error rate"}


def fmt(value, kind: str) -> str:
    if value is None or pd.isna(value):
        return "&mdash;"
    if kind == "yn":
        return "Yes" if value >= 0.5 else "No"
    if kind == "pct1":
        return f"{value * 100:.1f}%"
    if kind == "dec3":
        return f"{value:.3f}"
    if kind == "dec2":
        return f"{value:.2f}"
    return f"{value:.1f}"


PIN_BOARDS = ("Six-rotation hitter", "Front-row hitter")


def rating_note() -> None:
    """How the composite power rating is built, in one click.

    The board leads with a number that is not a raw rate, so the reader is owed the
    recipe without having to open the LLM panel to find it.
    """
    with st.expander("How the power rating is calculated"):
        st.markdown(
            "The rating is **a 50/50 blend of two models that disagree on purpose.**\n\n"
            "**The ridge half** fits one regression over every team-match in the season. "
            "Side-out rate is the currency &mdash; how often a team wins the rally when "
            "it is receiving &mdash; and every team's offense and every opponent's "
            "defense are solved at the same time, so strength of schedule is built in "
            "rather than added on. Its blind spot: it has no memory. Each season starts "
            "from zero, and a match in August counts exactly as much as one in December. "
            "It cannot see a team improve.\n\n"
            "**The Elo half** starts each team at 95% of where it finished last season "
            "and moves the rating after every match, by how far the result landed from "
            "what the rating predicted. Margin counts, measured as the winner's share of "
            "all rallies rather than the set score &mdash; about 180 rallies a match is a "
            "lot more evidence than 5 sets. Its blind spot: it updates one match at a "
            "time and never sees the schedule whole.\n\n"
            "**Why both.** Neither wins. Across 12,508 forecasts in 2022&ndash;2025, each "
            "made before the match it predicts, the ridge called 77.0&ndash;78.9% and Elo "
            "77.5&ndash;79.2%. But they miss *different* matches, so the blend beat both "
            "of them in all four seasons.\n\n"
            "**Why half and half.** The weight was fitted, not chosen. Trained on three "
            "seasons and tested on the fourth, it came back 52%, 49%, 50% and 49% Elo. "
            "It does drift within a season &mdash; nearer 55% Elo in September, when Elo "
            "still has last year's team and the ridge has barely any schedule, and nearer "
            "20% by December &mdash; but sliding it predicts no better than holding it "
            "flat, because by the time the ridge earns the larger share the two ratings "
            "already agree.\n\n"
            "**Read it as a ranking, not a rate.** The two halves are standardised and "
            "averaged, then stretched back to the ridge's scale so the number still looks "
            "familiar. A +27 means *as far above average as a +27 ridge rating would be*, "
            "not 27 extra side-outs per hundred. The Offense and Defense columns are the "
            "ridge's own numbers and those **are** literally side-outs per hundred: "
            "&ldquo;+6.1&rdquo; is six more per hundred receive rallies than an average "
            "team would manage against the same opponents.\n\n"
            "Ranks stay national when you filter by conference. Wins and losses are not "
            "an input to either half."
        )


def pin_split_note() -> None:
    """Why the two attacking boards are named for the job rather than the position.

    Shown only on the boards it applies to. A reader who arrives at "Six-rotation
    hitter" expecting "Outside hitter" deserves the reason in one click, without it
    sitting on top of every other board.
    """
    with st.expander("Why &ldquo;six-rotation&rdquo; and &ldquo;front-row&rdquo; "
                     "instead of outside and opposite?"):
        st.markdown(
            "Rosters list a player as OH or OPP, and we used to rank her that way. It "
            "doesn't work, for a simple reason: **the label often doesn't describe the "
            "job.**\n\n"
            "About half of teams don't give their opposite a label of her own &mdash; "
            "she just gets listed as an outside hitter. So when we checked, **43% of "
            "players called outside hitters almost never touch serve receive.** They "
            "are doing the opposite's job under the outside's name. Ranking by label "
            "meant ranking a team's paperwork, and it left the opposite board with "
            "fewer than 200 players nationally while the outside board carried 1,200.\n\n"
            "So the split is on what a player actually does, and the dividing line is "
            "serve receive:\n\n"
            "- **Six-rotation hitter** &mdash; she passes *and* attacks. She stays on "
            "for all six rotations, takes serve after serve, and still has to put balls "
            "away. Her hitting numbers carry the cost of passing first.\n"
            "- **Front-row hitter** &mdash; she attacks and blocks, and someone else "
            "passes. She gets more swings from better sets, so we expect a higher "
            "hitting percentage, and she is graded on blocking, which the six-rotation "
            "player does less of.\n\n"
            "These are genuinely different jobs, and now every player is measured "
            "against others doing hers. A terminator isn't penalised for passing she "
            "was never asked to do, and a six-rotation outside isn't compared to "
            "someone who only plays the front row.\n\n"
            "One honest caveat: **the line is a judgment call, not a natural gap in the "
            "data.** Most players are nowhere near it, but about 9% are close enough to "
            "fall either way. That is why receptions per set is shown on both boards "
            "&mdash; you can always see how close a player sits to the boundary.")


# What each board grades, and -- the part readers argue with -- which obvious
# measure was tried and thrown out. Every rejection here is a measured result, not a
# preference; the numbers are the ones the build script records.
METRIC_NOTES = {
    "Six-rotation hitter": (
        "**Graded on:** kills per set, hitting efficiency adjusted for passing load, "
        "reception error rate, digs per set, aces per set.\n\n"
        "She passes and attacks, so her hitting is measured against what her passing "
        "load predicts. An outside taking six serves a set gets the out-of-system ball "
        "more often, and raw efficiency punishes her for it.\n\n"
        "**In-system kill %.** In system means the designated setter delivered "
        "the ball; out of system the pass or dig was bad and a libero or an outside "
        "put up the second touch instead. The difference is not subtle &mdash; "
        "across 1.3 million attacks, in system produced a 36.3% kill rate at .211, "
        "out of system 30.2% at .157.\n\n"
        "It is a **control, never a benchmark.** A hitter's in-system share "
        "correlates +0.25 with her own efficiency, so a low number marks someone "
        "getting worse balls, not someone heroically terminating garbage &mdash; "
        "grading it would simply reward whoever is fed best. What it earns her is "
        "credit: a hitter at 68% in system who hits .250 did more than one at 90% "
        "who hits .250, and the board could not otherwise tell them apart. It is "
        "hers rather than her team's &mdash; teammate correlation +0.06, only 8.6% "
        "of the variance explained by the team she plays for.\n\n"
        "**Ruled out &mdash; receptions per set.** It looks like the obvious way to "
        "credit a six-rotation player, and it double-counts: the efficiency adjustment "
        "already accounts for passing load, so grading volume on top scores the same "
        "fact twice. It cost Pittsburgh's Olivia Babcock &mdash; 5.17 kills a set at "
        ".334 &mdash; a rank of 379th, because she takes no serve receive and was "
        "penalised for it twice over.\n\n"
        "**Ruled out &mdash; charted pass quality.** The source grades every pass "
        "great/good/bad, which sounds far better than counting errors. But two players "
        "on the same roster post nearly the same numbers (+0.54), higher than a "
        "player's own year-over-year, and 60% of the signal vanishes once the team "
        "effect is removed. It is largely measuring who keeps the book."),
    "Front-row hitter": (
        "**Graded on:** kills per set, hitting efficiency, blocks per set, attacks per "
        "set, aces per set.\n\n"
        "Someone else passes, so she is measured purely on terminating and blocking. "
        "Her efficiency is used raw &mdash; no passing adjustment &mdash; because she "
        "is swinging at in-system balls and should be held to that standard.\n\n"
        "**In-system kill %.** In system means the designated setter delivered "
        "the ball; out of system the pass or dig was bad and a libero or an outside "
        "put up the second touch instead. The difference is not subtle &mdash; "
        "across 1.3 million attacks, in system produced a 36.3% kill rate at .211, "
        "out of system 30.2% at .157.\n\n"
        "It is a **control, never a benchmark.** A hitter's in-system share "
        "correlates +0.25 with her own efficiency, so a low number marks someone "
        "getting worse balls, not someone heroically terminating garbage &mdash; "
        "grading it would simply reward whoever is fed best. What it earns her is "
        "credit: a hitter at 68% in system who hits .250 did more than one at 90% "
        "who hits .250, and the board could not otherwise tell them apart. It is "
        "hers rather than her team's &mdash; teammate correlation +0.06, only 8.6% "
        "of the variance explained by the team she plays for.\n\n"
        "**Ruled out &mdash; charted block quality.** The source publishes a blocking "
        "efficiency, and it does not repeat: once the team effect is removed, a "
        "player's year-over-year correlation is +0.26. Blocks per set is cruder and far "
        "more reliable."),
    "Middle blocker": (
        "**Graded on:** kills per set, hitting efficiency, blocks per set, attacks per "
        "set, aces per set.\n\n"
        "Attack volume is graded deliberately: a middle who gets set often is being "
        "trusted, and that is part of being good. A block assist counts as half a "
        "block, since two players share one.\n\n"
        "**In-system kill %.** In system means the designated setter delivered "
        "the ball; out of system the pass or dig was bad and a libero or an outside "
        "put up the second touch instead. The difference is not subtle &mdash; "
        "across 1.3 million attacks, in system produced a 36.3% kill rate at .211, "
        "out of system 30.2% at .157.\n\n"
        "It is a **control, never a benchmark.** A hitter's in-system share "
        "correlates +0.25 with her own efficiency, so a low number marks someone "
        "getting worse balls, not someone heroically terminating garbage &mdash; "
        "grading it would simply reward whoever is fed best. What it earns her is "
        "credit: a hitter at 68% in system who hits .250 did more than one at 90% "
        "who hits .250, and the board could not otherwise tell them apart. It is "
        "hers rather than her team's &mdash; teammate correlation +0.06, only 8.6% "
        "of the variance explained by the team she plays for.\n\n"
        "**Ruled out &mdash; charted block quality** (+0.26 year-over-year once the "
        "team effect is removed), and **hitting efficiency alone**. Middles post the "
        "highest efficiency of any position because they swing at the easiest balls; "
        "ranking on it alone would reward a middle who takes four safe swings a match "
        "over one carrying a real load."),
    "Setter": (
        "**Graded on:** assists per set, charted set quality, digs per set, aces per "
        "set, plus a small credit for a setter who attacks.\n\n"
        "**Set quality is the best-behaved number in this whole project.** Every set she "
        "makes is charted great / good / bad, and the rating is (2&times;great + good) "
        "&divide; total, on a 0&ndash;2 scale. It repeats at +0.78 year over year, and "
        "its teammate correlation is &minus;0.02 &mdash; knowing one setter's number "
        "tells you *nothing* about the other setter on her roster, which is exactly "
        "what you want and exactly what assist rate failed. It also tracks winning "
        "better than anything else here: +0.76 against team hitting efficiency, +0.64 "
        "against win percentage. It covers every primary setter in every season.\n\n"
        "**Bad set %** is shown beside it. A set the hitter can do little with happens "
        "3.4% of the time and repeats at +0.70 &mdash; a real mistake measure. The "
        "*charged* setting error is not: a double or a lift is called 364 times in the "
        "entire dataset against 4.75 million sets, the median setter commits none all "
        "season, and the rate barely repeats (+0.09). Scorers almost never call it.\n\n"
        "**Ruled out &mdash; assists per set attempt.** This is the one that stings, "
        "because it reads like the only measure of setting *quality* a box score "
        "offers: what share of her sets a hitter put away. It validates beautifully "
        "&mdash; +0.50 against team hitting efficiency, +0.43 against win percentage. "
        "It is a trap. Two setters on the same roster post nearly the same assist rate "
        "(+0.72, the highest correlation measured anywhere in this project), and a "
        "setter's own year-over-year signal falls to +0.09 once the team is removed. It "
        "tracks winning **because it is the team**: a setter on a good offence has a "
        "high assist rate because her hitters convert, and grading her on it credits "
        "her with their hitting.\n\n"
        "*An earlier version of this page said charted set quality was too thin to use, "
        "covering 6&ndash;7% of players. That was the wrong denominator &mdash; the "
        "source file lists everyone who ever touched a set, including hitters making an "
        "emergency one. Among actual setters it covers 68&ndash;90%, and 100% of "
        "primary setters.*\n\n"
        "Assists per set is kept alongside because it is demonstrably hers (teammate "
        "correlation &minus;0.70, since two setters split one job) and tracks winning "
        "at +0.53."),
    "Back row": (
        "**Graded on:** digs per set, charted dig quality, receptions per set, "
        "reception error rate, aces per set.\n\n"
        "Dig quality is the only charted touch metric that survived testing &mdash; "
        "teammate correlation +0.05, year-over-year +0.69 that does not move when the "
        "team effect is removed. Digs are graded off what the rally does next rather "
        "than off an opinion about the ball, which is likely why.\n\n"
        "**Why both volume and quality.** They measure different things, and the proof "
        "is blunt: among back-row players, digs per set and charted dig quality "
        "correlate **+0.001**. Knowing how many balls someone reached tells you nothing "
        "about what happened to them.\n\n"
        "**Ruled out &mdash; charted reception quality**, for the scorer bias described "
        "above. Passing is graded on charged errors instead: weaker, but at least it is "
        "the player's."),
}

ALL_BOARDS_NOTE = (
    "**Every board grades aces per set**, and it is the most reliable serving measure "
    "there is (.87 to .93 over a full season). It does not separate a good server from "
    "an aggressive one &mdash; aces and service errors per set correlate about +0.85, "
    "so serving is close to a single axis.\n\n"
    "**Ruled out &mdash; ace-to-service-error ratio.** The obvious way to reward "
    "balance, and it looked respectable at .63&ndash;.67. That number is an artifact of "
    "guarding the divide-by-zero: clipping errors at one orders every zero-error server "
    "by her ace count, so the ratio is secretly measuring volume. Written properly as a "
    "share it falls to .20&ndash;.33. Service errors, meanwhile, correlate &minus;0.05 "
    "with a team's point-score rate &mdash; missed serves cost almost nothing "
    "measurable, while aces are worth a good deal.\n\n"
    "**Players who never serve carry no serving benchmark rather than a zero.** Forty "
    "percent of middles and sixty percent of front-row hitters have a serving sub go in "
    "for them every rotation; scoring them zero would rank them on their coach's "
    "substitution pattern."
)


def metric_note(position: str | None) -> None:
    """What this board grades, and which obvious measure was tried and rejected."""
    body = METRIC_NOTES.get(position)
    label = ("What these boards measure, and what was ruled out" if body is None
             else f"What the {position.lower()} board measures, and what was ruled out")
    with st.expander(label):
        if body:
            st.markdown(body)
            st.markdown("---")
        st.markdown(ALL_BOARDS_NOTE)


def ask_panel(title: str, context: str, tables, key: str,
              glossary=None, limits=None, examples=(), limit: int | None = 300) -> None:
    """The download-and-ask panel at the foot of every page.

    Nothing is sent anywhere and no key is needed. The page packs what it is showing
    into one self-describing Markdown file and the reader takes it to whatever model
    they already use.
    """
    with st.expander("\U0001f9e0 Ask an LLM about this"):
        ex = (" \u2014 for example, " + " or ".join(f"*&ldquo;{e}&rdquo;*" for e in examples)
              if examples else "")
        st.markdown(L.HOWTO.replace("then ask it questions.",
                                    f"then ask it questions{ex}."),
                    unsafe_allow_html=True)
        md = L.build(title, context, tables, glossary, limits, limit)
        st.download_button("\u2b07  Download (.md)", md,
                           file_name=f"{L.slug(title)}.md", mime="text/markdown",
                           key=f"dl_{key}")
        st.caption(f"{len(md):,} characters \u00b7 fits in any current model's context.")


def team_picker(season: str, label: str, default: str | None, key: str) -> str:
    teams = sorted(D.team_seasons().query("season == @season").team.unique())
    idx = teams.index(default) if default in teams else 0
    return st.selectbox(label, teams, index=idx, key=key)


def season_frames(season: str, team: str, match_idx: int | None = None):
    """(season averages, one match, that match's label) for one team.

    match_idx indexes the team's schedule in date order; None means the most recent,
    which is what every view defaulted to before a match could be chosen.
    """
    tm = D.team_matches(season, team)
    if tm.empty:
        return None, None, None
    numeric = tm.select_dtypes("number").mean()
    i = -1 if match_idx is None else max(0, min(match_idx, len(tm) - 1))
    row = tm.iloc[i]
    return numeric, row, match_label(row)


def match_label(row) -> str:
    """'Sep 12 vs Wisconsin - W 3-1', short enough for a column header."""
    # built from parts rather than strftime("%b %-d"): the no-pad flag is a platform
    # extension and is not portable
    date = (f"{row.match_date:%b} {row.match_date.day}"
            if pd.notna(row.match_date) else "?")
    where = "at" if row.location == "away" else "vs"
    if pd.notna(row.get("sets_for")) and pd.notna(row.get("sets_against")):
        result = f"{'W' if row.won else 'L'} {int(row.sets_for)}-{int(row.sets_against)}"
    else:
        result = "W" if row.won else "L"
    return f"{date} {where} {row.opponent} \u00b7 {result}"


def match_picker(season: str, team: str, key: str) -> int | None:
    """Choose which of a team's matches to show. Defaults to the most recent."""
    tm = D.team_matches(season, team)
    if tm.empty:
        return None
    labels = [match_label(r) for _, r in tm.iterrows()]
    # Two matches can label identically -- same day, same opponent, same result, which
    # happens in tournaments. Selecting by label would then always return the first of
    # the pair, so number the repeats.
    seen: dict[str, int] = {}
    for i, lab in enumerate(labels):
        seen[lab] = seen.get(lab, 0) + 1
        if labels.count(lab) > 1:
            labels[i] = f"{lab}  (game {seen[lab]})"

    # most recent first: that is the match someone is usually here to look at
    order = list(range(len(labels)))[::-1]
    shown = [labels[i] for i in order]
    choice = st.selectbox(f"{team} match", shown, index=0, key=key)
    return order[shown.index(choice)]


# ---------------------------------------------------------------- comparison
def page_comparison(season: str, home: str, away: str) -> None:
    st.markdown(f'<h1 class="app">Stat <span class="accent">Comparison</span></h1>',
                unsafe_allow_html=True)
    h_avg, h_last, h_opp = season_frames(season, home)
    a_avg, a_last, a_opp = season_frames(season, away)
    if h_avg is None or a_avg is None:
        st.info("No graded matches for one of these teams in this season.")
        return

    rows = []
    for label, own, opp_col, kind in STAT_CATALOG:
        # a metric may format its match cell differently from its season cell
        last_kind, season_kind = kind if isinstance(kind, tuple) else (kind, kind)
        variants = [("off", own)] + ([("def / allowed", opp_col)] if opp_col else [])
        for suffix, col in variants:
            if col not in h_avg.index or col not in a_avg.index:
                continue
            hs, as_ = h_avg[col], a_avg[col]
            row_label = f"{label} &mdash; {suffix}" if opp_col else label
            # "better" is judged on the season column
            lower_better = (label in LOWER_IS_BETTER) ^ (suffix == "def / allowed")
            if pd.isna(hs) or pd.isna(as_):
                h_better = a_better = False
            elif lower_better:
                h_better, a_better = hs < as_, as_ < hs
            else:
                h_better, a_better = hs > as_, as_ > hs
            rows.append((row_label, fmt(h_last.get(col), last_kind),
                         fmt(hs, season_kind), h_better,
                         fmt(a_last.get(col), last_kind),
                         fmt(as_, season_kind), a_better))

    html = ['<table class="cmp"><thead>',
            f'<tr><th></th><th class="grp" colspan="2">{T.chip(home)}</th>'
            f'<th class="grp sep" colspan="2">{T.chip(away)}</th></tr>',
            f'<tr><th class="lab">Stat</th><th class="sub">Last ({h_opp})</th>'
            f'<th class="sub">Season</th><th class="sub sep">Last ({a_opp})</th>'
            f'<th class="sub">Season</th></tr></thead><tbody>']
    for label, hl, hsv, hb, al, asv, ab in rows:
        hcls = "num better" if hb else "num"
        acls = "num better" if ab else "num"
        html.append(f'<tr><td class="lab">{label}</td><td class="num">{hl}</td>'
                    f'<td class="{hcls}">{hsv}</td><td class="num sep">{al}</td>'
                    f'<td class="{acls}">{asv}</td></tr>')
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Green = better of the two on the season. '
                'Offense rows favor the higher value; allowed rows favor the lower.</p>',
                unsafe_allow_html=True)
    ask_panel(
        f"Stat Comparison \u2014 {home} vs {away}, {season}",
        "Two teams' season averages side by side. Offense rows are the team's own value; "
        "'allowed' rows are what opponents managed against them. Hitting efficiency is "
        "(kills - errors) / attempts. Side-out % is the share of receive rallies won; "
        "point-score % is the share of serve rallies won.",
        [(f"{home}", h_avg.rename("value").to_frame().reset_index(), None),
         (f"{away}", a_avg.rename("value").to_frame().reset_index(), None)],
        "cmp",
        limits=["Season averages here are unadjusted for schedule strength; the Power "
                "Rankings page carries the opponent-adjusted version.",
                "First-ball side-out is null for 2026 \u2014 the current play-by-play feed "
                "is point-summary only and cannot reconstruct it."],
        examples=["where does this team actually win?", "which gap decides the match?"])


# ---------------------------------------------------------------- benchmarks
def page_benchmarks(season: str, home: str, away: str) -> None:
    st.markdown(f'<h1 class="app">The Volleyball <span class="accent">{GRADE_MAX}</span></h1>',
                unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Seven benchmarks per match. Thresholds are the values '
                'that best separated winning from losing performances across 2021-2023, '
                'validated out of sample.</p>', unsafe_allow_html=True)

    # one picker per side: the two teams have different schedules, so a single
    # opponent list cannot serve both. Each defaults to that team's most recent match.
    c1, c2 = st.columns(2)
    with c1:
        home_idx = match_picker(season, home, "bench_match_home")
    with c2:
        away_idx = match_picker(season, away, "bench_match_away")

    # a list, not a dict keyed by team: picking the same team on both sides is legal
    frames = [season_frames(season, home, home_idx), season_frames(season, away, away_idx)]
    if any(f[0] is None for f in frames):
        st.info("No graded matches for one of these teams in this season.")
        return

    html = ['<table class="cmp"><thead>',
            f'<tr><th></th><th class="grp" colspan="2">{T.chip(home)}</th>'
            f'<th class="grp sep" colspan="2">{T.chip(away)}</th></tr>',
            f'<tr><th class="lab">Benchmark</th>'
            f'<th class="sub">{frames[0][2]}</th><th class="sub">Season</th>'
            f'<th class="sub sep">{frames[1][2]}</th>'
            f'<th class="sub">Season</th></tr></thead><tbody>']

    for b in D.graded_benchmarks():
        metric, flag = b["metric"], b["flag_column"]
        kind = "dec3" if "efficiency" in b["label"] or "margin" in metric else "pct1"
        if metric in ("ace_to_err",):
            kind = "dec2"
        if metric == "won_set1":
            kind = "yn"   # the match cell is a result, not a rate
        cells = []
        for team, (avg, last, _) in zip((home, away), frames):
            last_met = None if pd.isna(last.get(flag)) else bool(last[flag])
            cells.append(T.bench_pill(team, fmt(last.get(metric), kind), last_met))
            rate = avg.get(flag)
            cells.append(T.bench_pill(team, f"{rate * 100:.0f}%" if pd.notna(rate) else "",
                                      None if pd.isna(rate) else rate >= 0.5))
        html.append(f'<tr><td class="lab">{b["label"]}</td><td class="num">{cells[0]}</td>'
                    f'<td class="num">{cells[1]}</td><td class="num sep">{cells[2]}</td>'
                    f'<td class="num">{cells[3]}</td></tr>')

    totals = []
    for avg, last, _ in frames:
        # a benchmark with a missing input is not graded; show what it was graded out of
        of = int(last.graded_on) if pd.notna(last.get("graded_on")) else GRADE_MAX
        totals.append((f"{int(last.grade)} / {of}", f"{avg.grade:.2f} / {GRADE_MAX}"))
    html.append(f'<tr><td class="lab"><b>Met (of {GRADE_MAX})</b></td>'
                f'<td class="num"><b>{totals[0][0]}</b></td><td class="num"><b>{totals[0][1]}</b></td>'
                f'<td class="num sep"><b>{totals[1][0]}</b></td>'
                f'<td class="num"><b>{totals[1][1]}</b></td></tr></tbody></table>')
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown('<p class="sublabel">Match cells show that match&rsquo;s value; season cells '
                'show the share of the team&rsquo;s matches in which it cleared that '
                'benchmark. Pick any match above &mdash; each side defaults to its most '
                'recent.</p>', unsafe_allow_html=True)
    ask_panel(
        f"The Volleyball {GRADE_MAX} \u2014 {home} vs {away}, {season}",
        f"Every team-match is scored against {GRADE_MAX} benchmarks and the grade is how "
        "many it cleared. Thresholds are empirical: each is the value that best separated "
        "winning from losing performances across 2021-2023, constrained so 30-70% of "
        "team-matches clear it, then validated out of sample on 2024. A team's profile is "
        "the share of its matches that cleared each one.",
        [("Benchmark definitions", pd.DataFrame(D.graded_benchmarks()),
          ["label", "phase", "direction", "threshold"]),
         (f"{home} \u2014 share of matches clearing each benchmark",
          D.benchmark_profile(season, home), None),
         (f"{away} \u2014 share of matches clearing each benchmark",
          D.benchmark_profile(season, away), None)],
        "bm",
        limits=["The grade describes how a team played; it is not a forecast.",
                "It is unadjusted, so a soft schedule inflates it. Ranking uses the "
                "opponent-adjusted rating instead.",
                "Season grade correlates about 0.95 with season win %, so at season level "
                "it largely restates the standings. Its value is per-match diagnosis."],
        examples=["which benchmark is this team missing most?",
                  "what broke in the last match?"])


# ------------------------------------------------------------------ rankings
def page_rankings(season: str, home: str, away: str) -> None:
    st.markdown('<h1 class="app">Power <span class="accent">Rankings</span></h1>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    conf = c1.selectbox("Conference", ["All D1"] + D.conferences(season))
    min_m = c2.slider("Min matches", 5, 30, 5)

    r = D.rankings(season, None if conf == "All D1" else conf, min_m)
    if r.empty:
        st.info("No teams match that filter.")
        return
    rating_note()
    st.markdown('<p class="sublabel">The Power Ranking blends two opponent-adjusted '
                'models with each contributing equally to the ranking: a season-long ridge '
                'regression model and an Elo that carries last season and weights recent '
                'matches more. Ranks stay national when a conference is selected.</p>',
                unsafe_allow_html=True)

    html = ['<div class="scroller"><table class="grid"><thead><tr><th>Rank</th><th>Team</th><th>Record</th>'
            '<th>Conference</th><th style="text-align:right">Rating</th>'
            '<th style="text-align:right">Offense</th><th style="text-align:right">Defense</th>'
            '<th style="text-align:right">Elo</th>'
            f'<th style="text-align:right">Grade /{GRADE_MAX}</th></tr></thead><tbody>']
    for _, row in r.iterrows():
        hl = ' class="hl"' if row.team in (home, away) else ""
        rec = f"{int(row.wins)}-{int(row.losses)}" if pd.notna(row.wins) else "&mdash;"
        grade = f"{row.grade:.2f}" if pd.notna(row.grade) else "&mdash;"
        elo = f"{row.elo:,.0f}" if pd.notna(getattr(row, "elo", None)) else "&mdash;"
        html.append(
            f'<tr{hl}><td class="n">{int(row.rank_composite)}</td><td>{T.chip(row.team, ".85rem")}</td>'
            f'<td>{rec}</td><td>{row.conference or ""}</td>'
            f'<td class="n">{row.rating_composite:+.1f}</td>'
            f'<td class="n">{row.rating_off:+.1f}</td>'
            f'<td class="n">{row.rating_def:+.1f}</td>'
            f'<td class="n">{elo}</td><td class="n">{grade}</td></tr>')
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    ask_panel(
        f"Power Rankings \u2014 {season}" + ("" if conf == "All D1" else f", {conf}"),
        "Team ratings from two opponent-adjusted models, blended half and half. "
        "MODEL 1, the ridge: one regression over every team-match, with side-out rate as "
        "the currency \u2014 sideout_pct(i receiving against j) = mu + off_i - def_j. It "
        "is centred so an average D1 team is 0.0, in percentage points of side-out rate, "
        "so rating_off '+6.1' means six more side-outs per hundred receive rallies than an "
        "average team would manage against the same opponents. rating_overall = off + def. "
        "It solves the whole schedule at once but has no memory: every season starts from "
        "zero and an August match counts like a December one. "
        "MODEL 2, Elo: sequential, 400-point logistic scale, updated after every match, "
        "with margin entering through the K multiplier as the winner's share of all "
        "rallies. It carries 95% of last season forward and weights recent matches more, "
        "but updates one match at a time and never sees the schedule whole. "
        "THE BLEND: both ratings are standardised within the season, averaged 50/50, then "
        "rescaled to the ridge's spread \u2014 so rating_composite is read like "
        "rating_overall but is not literally side-outs per hundred. The 50/50 weight was "
        "fitted, not chosen: trained on three seasons and tested on the fourth it came "
        "back 52%, 49%, 50% and 49% Elo. Ranks stay national when a conference is "
        "selected, and rank_composite is what the board is sorted by.",
        [("Team ratings", r, ["rank_composite", "team", "conference", "wins", "losses",
                              "rating_composite", "rating_overall", "rank_overall",
                              "elo", "rank_elo", "rating_off", "rating_def", "grade",
                              "graded_matches"])],
        "pwr",
        glossary={"rating_composite": "the 50/50 blend the board is ranked by",
                  "rating_overall": "the ridge half alone, = off + def",
                  "elo": "the Elo half alone; league mean is 1500, sd about 365",
                  "rating_off": "side-out ability when receiving (ridge)",
                  "rating_def": "suppressing the opponent's side-out (ridge)",
                  "grade": f"mean benchmark count out of {GRADE_MAX}, unadjusted"},
        limits=["Ridge shrinks teams with short or lopsided schedules toward average.",
                "The grade column is unadjusted and will disagree with the rating for "
                "teams on very soft or very hard schedules. That disagreement is the "
                "reason both are shown.",
                "Early in a season the two halves disagree most, because Elo is still "
                "mostly last season's team while the ridge knows only this one. Fitted "
                "inside week bands the best weight runs about 55% Elo in September and "
                "21% by December, but holding the weight flat at 50/50 predicts just as "
                "well, so the board does not slide it.",
                "The composite is a rank-ordering device. Read rating_off and rating_def "
                "when you want a number that is literally side-outs per hundred."],
        examples=["who is underrated by their record?",
                  "is this conference strong on offense or defense?"])



# ----------------------------------------------------------------- players
# What each board shows beyond rank / player / team / sets / rating. The graded
# metrics come first in the order they are graded, then a little context.
PLAYER_COLUMNS = {
    "Six-rotation hitter": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                       ("Hit% adj", "hit_pct_pass", "dec3"),
                       ("Rec/set", "receptions_per_set", "dec2"),
                       ("Rec err", "reception_err_rate", "pct1"),
                       ("Digs/set", "digs_per_set", "dec2"),
                       ("In-sys%", "in_system_kill_pct", "pct1"),
                       ("Aces/set", "aces_per_set", "dec2")],
    "Middle blocker": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                       ("Blk/set", "blocks_per_set", "dec2"),
                       ("Att/set", "attacks_per_set", "dec2"),
                       ("In-sys%", "in_system_kill_pct", "pct1"),
                       ("Aces/set", "aces_per_set", "dec2")],
    "Front-row hitter": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                 ("Blk/set", "blocks_per_set", "dec2"),
                 ("Att/set", "attacks_per_set", "dec2"),
                 ("Rec/set", "receptions_per_set", "dec2"),
                 ("In-sys%", "in_system_kill_pct", "pct1"),
                 ("Aces/set", "aces_per_set", "dec2")],
    "Setter": [("Ast/set", "assists_per_set", "dec2"),
               ("Set qual", "set_rating", "dec2"),
               ("Bad set%", "set_bad_pct", "pct1"),
               ("Digs/set", "digs_per_set", "dec2"),
               ("Aces/set", "aces_per_set", "dec2"), ("K/set", "kills_per_set", "dec2")],
    "Back row": [("Digs/set", "digs_per_set", "dec2"),
                 ("Dig qual", "dig_rating", "dec2"),
                 ("Rec/set", "receptions_per_set", "dec2"),
                 ("Rec err", "reception_err_rate", "pct1"),
                 ("Aces/set", "aces_per_set", "dec2")],
}


TEAM_COLUMNS = [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                ("Blk/set", "blocks_per_set", "dec2"), ("Digs/set", "digs_per_set", "dec2"),
                ("Rec/set", "receptions_per_set", "dec2"),
                ("Ast/set", "assists_per_set", "dec2"),
                ("Aces/set", "aces_per_set", "dec2")]


def sort_key(v) -> str:
    """The value a cell sorts on, kept out of the text it displays.

    A reader wants to see "53-326" and "18/49"; a sorter wants one number. Emitting
    both means the JS never parses display text, so a band, a chip or an em-dash sorts
    by what it means rather than by how it reads.
    """
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v) else str(v)


def player_table(r, cols, home: str, away: str, show_position: bool = False) -> str:
    """The ranked-player table. One renderer for the position boards and the team view."""
    head = "".join(f'<th class="srt" data-t="n" style="text-align:right">{lab}</th>'
                   for lab, _, _ in cols)
    pos_h = '<th class="srt" data-t="s">Pos</th>' if show_position else ""
    html = ['<div class="scroller"><table class="grid"><thead><tr>'
            '<th class="srt" data-t="n">Rank</th>'
            '<th class="srt" data-t="n" style="text-align:right">90% band</th>'
            '<th class="srt" data-t="n" style="text-align:right">In conf</th>'
            '<th class="srt" data-t="s">Player</th>'
            f'{pos_h}<th class="srt" data-t="s">Team</th>'
            '<th class="srt" data-t="s">Conference</th>'
            '<th class="srt" data-t="n" style="text-align:right">Sets</th>'
            '<th class="srt" data-t="n" style="text-align:right">Rating</th>'
            '<th class="srt" data-t="n" style="text-align:right">Bench</th>'
            f'{head}</tr></thead><tbody>']
    for _, row in r.iterrows():
        hl = ' class="hl"' if row.team in (home, away) else ""
        rank = int(row.rank_in_position) if pd.notna(row.rank_in_position) else "&mdash;"
        band = (f'{int(row.rank_low)}&ndash;{int(row.rank_high)}'
                if pd.notna(row.rank_low) else "&mdash;")
        cr = (f'{int(row.rank_in_conference)}/{int(row.players_in_conference)}'
              if pd.notna(row.rank_in_conference) else "&mdash;")
        bench = (f'{row.benchmarks_met:.0f}/{int(row.benchmarks_of)}'
                 if pd.notna(row.benchmarks_met) else "&mdash;")
        pos_c = (f'<td class="ph" data-s="{row.position}">{row.position}</td>'
                 if show_position else "")
        cells = "".join(
            f'<td class="n" data-s="{sort_key(row.get(c))}">{fmt(row.get(c), k)}</td>'
            for _, c, k in cols)
        html.append(
            f'<tr{hl}><td class="n" data-s="{sort_key(row.rank_in_position)}">{rank}</td>'
            f'<td class="n" data-s="{sort_key(row.rank_low)}" style="color:#9aa0a6">{band}</td>'
            f'<td class="n" data-s="{sort_key(row.rank_in_conference)}">{cr}</td>'
            f'<td data-s="{row.player}"><b>{row.player}</b></td>{pos_c}'
            f'<td data-s="{row.team}">{T.chip(row.team, ".85rem")}</td>'
            f'<td data-s="{row.conference or ""}">{row.conference or ""}</td>'
            f'<td class="n" data-s="{sort_key(row.sets)}">{row.sets:.0f}</td>'
            f'<td class="n" data-s="{sort_key(row.rating)}">{row.rating:.1f}</td>'
            f'<td class="n" data-s="{sort_key(row.benchmarks_met)}">{bench}</td>'
            f'{cells}</tr>')
    html.append("</tbody></table></div>")
    return "".join(html)


SORT_JS = """
<script>
// Click a header to sort. Lives in a component iframe because st.markdown strips
// <script>; the trade is that this table cannot see the page's CSS, so the theme is
// inlined above. Rows carry data-s, so nothing here parses display text.
document.querySelectorAll('table.grid th.srt').forEach(function (th, i) {
  th.addEventListener('click', function () {
    var table = th.closest('table');
    var body = table.tBodies[0];
    var numeric = th.dataset.t === 'n';
    var wasAsc = th.classList.contains('asc');
    // Rank-like columns read best smallest-first; everything else biggest-first.
    var asc = th.classList.contains('asc') || th.classList.contains('desc')
        ? !wasAsc : (numeric ? i < 3 : true);
    table.querySelectorAll('th.srt').forEach(function (o) {
      o.classList.remove('asc', 'desc');
    });
    th.classList.add(asc ? 'asc' : 'desc');
    var rows = Array.prototype.slice.call(body.rows);
    rows.sort(function (a, b) {
      var x = a.cells[i] ? a.cells[i].dataset.s : '';
      var y = b.cells[i] ? b.cells[i].dataset.s : '';
      // A blank is "not measured", never "worst" -- it sits at the bottom either way.
      if (x === '' && y === '') return 0;
      if (x === '') return 1;
      if (y === '') return -1;
      var c = numeric ? (parseFloat(x) - parseFloat(y))
                      : x.localeCompare(y, undefined, {sensitivity: 'base'});
      return asc ? c : -c;
    });
    rows.forEach(function (r) { body.appendChild(r); });
  });
});
</script>
"""


ROW_PX = 45          # a row carrying a team chip, measured in the rendered component
HEAD_PX = 32
VISIBLE_ROWS = 25    # show the whole table up to here, then scroll inside the frame


def sortable(html: str, rows: int) -> None:
    """Render a grid table as a component so its headers can be clicked to sort.

    The frame is sized to the table: a short board shows whole with no scrollbar of its
    own, and anything longer than VISIBLE_ROWS scrolls inside the frame under its sticky
    header rather than stretching the page to two thousand rows. The row height is
    measured rather than guessed -- 45px with a team chip in the cell -- and rounded up,
    because being a few pixels generous costs a sliver of whitespace while being a few
    pixels short clips the last row behind the frame edge.
    """
    shown = min(max(rows, 1), VISIBLE_ROWS)
    inner = HEAD_PX + shown * ROW_PX + 4
    components.html(
        T.CSS
        + f'<style>body{{margin:0;background:{T.BG};color:{T.TEXT};font-family:{T.FONT}}}'
          f'.scroller{{max-height:{inner}px}}</style>'
        + html + SORT_JS,
        height=inner + 2, scrolling=False)


def page_players(season: str, home: str, away: str) -> None:
    st.markdown('<h1 class="app">Position <span class="accent">Rankings</span></h1>',
                unsafe_allow_html=True)
    pb = D.player_benchmarks()
    positions = [D.ALL_POSITIONS] + D.positions()
    c1, c2, c3 = st.columns([1.3, 1.2, 1.2])
    position = c1.selectbox("Position", positions,
                            index=positions.index("Outside hitter")
                            if "Outside hitter" in positions else 0)
    conf = c2.selectbox("Conference", ["All D1"] + D.player_conferences(season), key="pconf")
    every = position == D.ALL_POSITIONS
    scope_opts = (["Selected teams only", "One team", "Top 25 per position", "Everyone"]
                  if every else
                  ["Top 50", "Top 100", "Selected teams only", "Everyone"])
    scope = c3.selectbox("Show", scope_opts, key="pscope")

    conference = None if conf == "All D1" else conf
    if every:
        team = None
        if scope == "One team":
            teams = D.player_teams(season)
            team = st.selectbox("Team", teams,
                                index=teams.index(home) if home in teams else 0, key="pteam")
        r = D.all_positions(season, conference, team)
        if scope == "Selected teams only":
            r = r[r.team.isin([home, away])]
        elif scope == "Top 25 per position":
            r = r.groupby("position", group_keys=False).head(25)
        cols, show_pos = TEAM_COLUMNS, True
        metric_note(None)
        pin_split_note()
        who = team or (f"{home} and {away}" if scope == "Selected teams only" else "D1")
        st.markdown(
            f'<p class="sublabel">Every ranked {who} player in {season}, all five '
            f'positions. Rank and rating are national and <em>within her own position</em> '
            f'&mdash; the boards grade different jobs, so a setter&rsquo;s 92 and a '
            f'middle&rsquo;s 92 are not the same 92, and the rows are not a pecking order. '
            f'&ldquo;In conf&rdquo; is the same rank taken inside her conference. Minimum '
            f'{pb["min_sets"]} sets, and in {pb["recency_rule"]["current_season"]} at '
            f'least one set in the team&rsquo;s last three matches.</p>',
            unsafe_allow_html=True)
    else:
        r = D.player_rankings(season, position, conference)
        if scope == "Selected teams only":
            r = r[r.team.isin([home, away])]
        elif scope == "Top 50":
            r = r.head(50)
        elif scope == "Top 100":
            r = r.head(100)
        cols, show_pos = PLAYER_COLUMNS.get(position, []), False
        metric_note(position)
        if position in PIN_BOARDS:
            pin_split_note()
        graded = ", ".join(x["label"].lower() for x in pb["groups"].get(position, []))
        bonus = (" Setters who attack carry a small credit on kills per set."
                 if position == "Setter" else "")
        st.markdown(
            f'<p class="sublabel">Rating is the mean percentile on {graded}, computed on '
            f'values adjusted for the opponents she actually faced, against fixed '
            f'2022&ndash;2025 reference distributions &mdash; so it means the same thing in '
            f'every season.{bonus} The benchmark count beside it is deliberately '
            f'<em>un</em>adjusted, the same split the team pages make between the grade and '
            f'the power rating. Minimum {pb["min_sets"]} sets, and in '
            f'{pb["recency_rule"]["current_season"]} at least one set in the team&rsquo;s '
            f'last three matches. Ranks stay national under every filter.</p>',
            unsafe_allow_html=True)
    if r.empty:
        st.info("Nobody matches that filter.")
        return

    # How wide the bands run tells the reader, before they read a single name, whether
    # these are ranks or merely an ordering of overlapping guesses.
    width = ((r.rank_high - r.rank_low) / r.players_in_position).median()
    if pd.notna(width) and width >= 0.30:
        st.warning(
            f"**{season} is still being played.** The 90% band on a rank currently spans "
            f"about {width:.0%} of a position, against roughly 18% for a finished season. "
            f"The ordering is real but individual places are not yet separable &mdash; two "
            f"players twenty apart are not distinguishable. Bands are shown beside every "
            f"rank.")

    sortable(player_table(r, cols, home, away, show_position=show_pos), len(r))
    st.markdown('<p class="tiny" style="color:#6f7681">The band is where this player '
                'plausibly sits, at 90% confidence. It is measured, not assumed: every '
                'player&rsquo;s season is split odd/even and scored twice, and the spread '
                'between her own two halves is the error bar. A dash means the stat is not '
                'part of that position&rsquo;s job, or she has too few attempts to be '
                'graded on it.</p>', unsafe_allow_html=True)

    # ---- one player's season, match by match
    names = r.player.tolist()
    default = next((i for i, n in enumerate(names) if r.team.iloc[i] in (home, away)), 0)
    pick = st.selectbox("Match log", names, index=default, key="plog")
    prow = r[r.player == pick].iloc[0]
    log = D.player_log(season, prow.team, pick)
    if log.empty:
        return
    col, kind = {"Six-rotation hitter": ("hit_pct", "dec3"),
                 "Middle blocker": ("hit_pct", "dec3"),
                 "Front-row hitter": ("hit_pct", "dec3"),
                 "Setter": ("assists_per_set", "dec2"),
                 "Back row": ("digs_per_set", "dec2")}[prow.position]
    recent = log.tail(3)[col].mean()
    season_val = pd.to_numeric(prow.get(col), errors="coerce")
    arrow = ""
    if pd.notna(recent) and pd.notna(season_val):
        delta = recent - season_val
        word = "above" if delta > 0 else "below"
        arrow = (f" &middot; last three matches {fmt(recent, kind)}, "
                 f"{fmt(abs(delta), kind)} {word} her season {fmt(season_val, kind)}")
    st.markdown(
        f'<p class="sublabel"><b>{pick}</b>, {prow.team} &mdash; {prow.position}, rank '
        f'{int(prow.rank_in_position)} of {int(prow.players_in_position):,}, band '
        f'{int(prow.rank_low)}&ndash;{int(prow.rank_high)}{arrow}</p>',
        unsafe_allow_html=True)
    lh = ['<div class="scroller"><table class="grid"><thead><tr><th>Date</th>'
          '<th>Opponent</th><th style="text-align:right">Sets</th>'
          '<th style="text-align:right">K</th><th style="text-align:right">E</th>'
          '<th style="text-align:right">TA</th><th style="text-align:right">Hit%</th>'
          '<th style="text-align:right">Digs</th><th style="text-align:right">Rec</th>'
          '<th style="text-align:right">RErr</th><th style="text-align:right">Ast</th>'
          '<th style="text-align:right">Blk</th><th style="text-align:right">Aces</th>'
          '</tr></thead><tbody>']
    for _, x in log.iterrows():
        lh.append(
            f'<tr><td>{x.date}</td><td>{x.opponent}</td>'
            f'<td class="n">{x.S:.0f}</td><td class="n">{x.Kills:.0f}</td>'
            f'<td class="n">{x.Errors:.0f}</td><td class="n">{x.TotalAttacks:.0f}</td>'
            f'<td class="n">{fmt(x.hit_pct, "dec3")}</td>'
            f'<td class="n">{x.Digs:.0f}</td><td class="n">{x.RetAtt:.0f}</td>'
            f'<td class="n">{x.RErr:.0f}</td><td class="n">{x.Assists:.0f}</td>'
            f'<td class="n">{x.BlockSolos + x.BlockAssists / 2:.1f}</td>'
            f'<td class="n">{x.Aces:.0f}</td></tr>')
    lh.append("</tbody></table></div>")
    st.markdown("".join(lh), unsafe_allow_html=True)
    st.markdown('<p class="tiny" style="color:#6f7681">A season rating is an average. '
                'This is what it averaged.</p>', unsafe_allow_html=True)

    ctx_cols = ["rank_in_position", "players_in_position", "rank_low", "rank_high",
                "rank_in_conference", "players_in_conference", "player", "team",
                "conference", "position", "sets", "rating", "benchmarks_met",
                "benchmarks_of"] + [c for _, c, _ in cols]
    graded_defs = "\n".join(
        f"- **{g}**: " + "; ".join(f'{x["label"]} (median threshold {x["threshold"]}, '
                                   f'{x["direction"]})' for x in v)
        for g, v in pb["groups"].items())
    ask_panel(
        f"Position Rankings \u2014 {position or 'all positions'}, {season}",
        "Each position is graded on its own small set of benchmarks, because the "
        "positions do not share a job. Two numbers per player, deliberately different:\n\n"
        "- `benchmarks_met` is RAW, against fixed 2022-2025 medians. It describes what she "
        "did and stays readable.\n"
        "- `rating` is 0-100: the mean of her percentiles on the same metrics after an "
        "opponent adjustment, against the same fixed reference seasons. It is what "
        "ranks.\n\n"
        "The opponent adjustment is fitted per match, not per season: "
        "rate(player i vs team j) = mu + player_i - opponent_j, by alternating weighted "
        "means with a ridge penalty on the opponent effects only.\n\n"
        "`rank_low`..`rank_high` is a 90% confidence band on the rank. It is measured, not "
        "assumed: every player's matches are split odd/even and scored twice, and the "
        "spread between her own two halves is the standard error. **Players whose bands "
        "overlap heavily are not distinguishable and should not be ranked against each "
        "other.**\n\n"
        f"What each position is graded on:\n{graded_defs}\n\n"
        f"Minimum {pb['min_sets']} sets. In {pb['recency_rule']['current_season']}, which "
        "is still being played, a player is ranked only if she played at least one set in "
        "her team's last three matches.",
        [("Board", r, ctx_cols),
         (f"Match log \u2014 {pick} ({prow.team})", log,
          ["date", "opponent", "S", "Kills", "Errors", "TotalAttacks", "hit_pct", "Digs",
           "RetAtt", "RErr", "Assists", "Aces"])],
        "plr",
        glossary={
            "rating": "0-100, mean percentile on this position's benchmarks, opponent-adjusted",
            "benchmarks_met": "how many benchmarks she cleared, unadjusted",
            "rank_in_conference": "the same rank taken inside her conference",
            "hit_pct_pass": "hitting efficiency adjusted for her serve-receive load",
            "dig_rating": "charted dig quality, (2*great + good) / total, back row only",
            "sets": "sets played, the sample everything here rests on"},
        limits=[
            pb["opponent_adjustment"]["does_not_fix"],
            "About half of teams do not give their opposite a distinct label, so the "
            "outside board contains many true opposites.",
            "Charted reception, serve and block quality were tested and rejected as "
            "scorer-contaminated: charted pass quality correlates +0.54 between teammates, "
            "higher than its own year-over-year, and 60% of its signal disappears once the "
            "team effect is removed. Only dig quality survived, and only for back row.",
            "Every board grades aces per set, which measures serving aggression as much as "
            "serving quality: aces and service errors per set correlate about +0.85.",
            "Players who never serve carry no serving benchmark rather than a zero, and "
            "are graded out of one fewer.",
            "Early in a season the bands are wide. Read them before comparing two players.",
        ],
        examples=["why is this player ranked where she is?",
                  "which of these players are actually distinguishable?"])

    with st.expander("What this board does not fix"):
        oa = pb["opponent_adjustment"]
        st.markdown(f"- **Usage.** {oa['does_not_fix']}")
        st.markdown(
            "- **Boards are split by what a player did, not what the roster called her.** "
            "43% of players listed as outside hitters take under half a reception per "
            "set &mdash; only about half of teams give their opposite a label of her own "
            "&mdash; so ranking on the label ranked a coach's paperwork. The split is "
            "serve receive, taken at the 37th percentile of each season's attackers, "
            "and the line is chosen rather than found: the distribution has no clean "
            "gap, and about 9% of attackers sit close enough to fall either way. "
            "Receptions per set is shown on both boards so you can see who is near it.")
        st.markdown(
            "- **Small samples early in a season.** The set minimum is a season-long floor, "
            "so in the first weeks a board is ordered on twenty-odd sets and will move a "
            "lot. The rank band is the measurement of exactly that; at 23 sets it spans "
            "hundreds of places.")
        st.markdown(
            "- **Serving aggression.** Every board grades aces per set, the most reliable "
            "serving measure there is and the one that tracks winning serve rallies. It "
            "does not separate a good server from an aggressive one: aces and service "
            "errors per set correlate about +0.85, so serving is close to a single axis, "
            "and the balance measures that would separate them do not repeat well enough "
            "to grade. Players who never serve &mdash; 43% of middles and 61% of opposites, "
            "who have a serving sub go in for them &mdash; carry no serving benchmark "
            "rather than a zero, and are graded out of one fewer.")
        st.markdown(
            "- **Charted touch quality, mostly unusable.** The source charts reception, "
            "serve, dig, block and set quality from play-by-play. Only digs survive "
            "testing, and only for back-row players. The rest are contaminated by who "
            "keeps the book: charted reception quality correlates +0.54 between teammates "
            "&mdash; double any box-score metric, and higher than its own year-over-year "
            "&mdash; and 60% of its apparent signal disappears once the team effect is "
            "removed. Passing is still graded on charged errors, which is weak but is at "
            "least the player&rsquo;s.")
        st.caption("Opponent model: " + oa["model"])


# ---------------------------------------------------------------------- about
def page_about() -> None:
    meta = D.meta()
    st.markdown('<h1 class="app">How it <span class="accent">works</span></h1>',
                unsafe_allow_html=True)
    st.markdown(
        f"Each match is scored against **{GRADE_MAX} benchmarks**; the grade is how many were "
        "cleared. Thresholds are empirical, not chosen by feel: each is the value that best "
        "separated winning from losing performances across 2021-2023, constrained so that "
        "30-70% of team-matches clear it, then validated out of sample on 2024.")
    st.dataframe(pd.DataFrame(D.graded_benchmarks())[["label", "phase", "direction", "threshold"]]
                 .rename(columns={"label": "Benchmark", "phase": "Phase",
                                  "direction": "Direction", "threshold": "Threshold"}),
                 width='stretch', hide_index=True)

    st.subheader("Grade tracks season success")
    st.dataframe(pd.DataFrame([{"Season": k, "r (grade vs win%)": v}
                               for k, v in meta["grade_vs_win_pct_by_season"].items()]),
                 width='stretch', hide_index=True)
    st.markdown('<p class="sublabel">The grade is a description of how a team played, not a '
                'forecast of the next match. Ranking is done by the opponent-adjusted rating '
                'instead, because the grade is unadjusted and rewards a soft schedule.</p>',
                unsafe_allow_html=True)

    st.subheader("Context metrics — shown, never scored")
    st.markdown('<p class="sublabel">Real stats that fail as benchmarks: either algebraically '
                'redundant with a graded one, or too weak to carry equal weight in a count.</p>',
                unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(D.context_benchmarks())[["label", "phase"]]
                 .rename(columns={"label": "Metric", "phase": "Phase"}),
                 width='stretch', hide_index=True)

    st.subheader("Caveats")
    for c in meta["caveats"]:
        st.markdown(f"- {c}")
    st.caption(f"Built {meta['built_at']} · {meta['source']}")
    ask_panel(
        "How it works \u2014 methodology",
        f"The {GRADE_MAX} graded benchmarks, the context metrics shown but never scored, "
        "and the project's own caveats. Seven rather than fourteen because volleyball will "
        "not carry fourteen independent measurements: every rally is won by exactly one "
        "team and is either a side-out or a point-score, so most 'different' volleyball "
        "stats are components of the same two numbers. Two of the original fourteen were "
        "algebraic identities rather than correlations \u2014 hitting efficiency IS kill "
        "rate minus attack-error rate \u2014 and three more had infinite variance "
        "inflation.",
        [("Graded benchmarks", pd.DataFrame(D.graded_benchmarks()), None),
         ("Context metrics, shown but never scored",
          pd.DataFrame(D.context_benchmarks()), None),
         ("Grade vs win % by season",
          pd.DataFrame([{"season": k, "r": v}
                        for k, v in meta["grade_vs_win_pct_by_season"].items()]), None)],
        "abt",
        limits=meta["caveats"],
        examples=["why seven benchmarks?", "what is deliberately not measured?"])


# ------------------------------------------------------------------- shell
st.sidebar.markdown("### 🏐 QuesoHusker's Volleyball")
season = st.sidebar.selectbox("Season", D.seasons())
home = team_picker(season, "Team", "Nebraska", "home")
away = team_picker(season, "Opponent", "Wisconsin", "away")
st.sidebar.caption(f"NCAA women's D1 · {min(D.seasons())}-{max(D.seasons())} · "
                   f"{D.meta()['team_match_rows']:,} graded team-matches")

tabs = st.tabs(["Stat Comparison", f"The Volleyball {GRADE_MAX}", "Power Rankings",
                "Position Rankings", "How it works"])
with tabs[0]:
    page_comparison(season, home, away)
with tabs[1]:
    page_benchmarks(season, home, away)
with tabs[2]:
    page_rankings(season, home, away)
with tabs[3]:
    page_players(season, home, away)
with tabs[4]:
    page_about()
