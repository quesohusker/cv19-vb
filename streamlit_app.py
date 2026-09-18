"""QuesoHusker's Volleyball — Analysis & Benchmarks.

Read-only front end over the precomputed tables in app_data/. Mirrors the structure
and design system of the CFB app: global season + two-team selection, a stat
comparison, a benchmark scorecard, and opponent-adjusted power rankings. No game
predictions -- volleyball match outcomes are not what this project set out to forecast.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app import data as D
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


# ------------------------------------------------------------------ rankings
def page_rankings(season: str, home: str, away: str) -> None:
    st.markdown('<h1 class="app">Power <span class="accent">Rankings</span></h1>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    conf = c1.selectbox("Conference", ["All D1"] + D.conferences(season))
    min_m = c2.slider("Min matches", 5, 30, 10)

    r = D.rankings(season, None if conf == "All D1" else conf, min_m)
    if r.empty:
        st.info("No teams match that filter.")
        return
    st.markdown('<p class="sublabel">Opponent-adjusted side-out rating, in percentage points '
                'against an average D1 team. Offense is side-out ability; defense is '
                'suppressing the opponent&rsquo;s side-out. Ranks stay national when a '
                'conference is selected.</p>', unsafe_allow_html=True)

    html = ['<table class="grid"><thead><tr><th>Rank</th><th>Team</th><th>Record</th>'
            '<th>Conference</th><th style="text-align:right">Overall</th>'
            '<th style="text-align:right">Offense</th><th style="text-align:right">Defense</th>'
            f'<th style="text-align:right">Grade /{GRADE_MAX}</th></tr></thead><tbody>']
    for _, row in r.iterrows():
        hl = ' class="hl"' if row.team in (home, away) else ""
        rec = f"{int(row.wins)}-{int(row.losses)}" if pd.notna(row.wins) else "&mdash;"
        grade = f"{row.grade:.2f}" if pd.notna(row.grade) else "&mdash;"
        html.append(
            f'<tr{hl}><td class="n">{int(row.rank_overall)}</td><td>{T.chip(row.team, ".85rem")}</td>'
            f'<td>{rec}</td><td>{row.conference or ""}</td>'
            f'<td class="n">{row.rating_overall:+.1f}</td>'
            f'<td class="n">{row.rating_off:+.1f}</td>'
            f'<td class="n">{row.rating_def:+.1f}</td><td class="n">{grade}</td></tr>')
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)



# ----------------------------------------------------------------- players
# What each board shows beyond rank / player / team / sets / rating. The graded
# metrics come first in the order they are graded, then a little context.
PLAYER_COLUMNS = {
    "Outside hitter": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                       ("Hit% adj", "hit_pct_pass", "dec3"),
                       ("Rec/set", "receptions_per_set", "dec2"),
                       ("Digs/set", "digs_per_set", "dec2"),
                       ("Aces/set", "aces_per_set", "dec2")],
    "Middle blocker": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                       ("Blk/set", "blocks_per_set", "dec2"),
                       ("Att/set", "attacks_per_set", "dec2"),
                       ("Aces/set", "aces_per_set", "dec2")],
    "Opposite": [("K/set", "kills_per_set", "dec2"), ("Hit%", "hit_pct", "dec3"),
                 ("Blk/set", "blocks_per_set", "dec2"),
                 ("Att/set", "attacks_per_set", "dec2"),
                 ("Aces/set", "aces_per_set", "dec2")],
    "Setter": [("Ast/set", "assists_per_set", "dec2"), ("Ast/att", "assist_rate", "dec3"),
               ("Digs/set", "digs_per_set", "dec2"),
               ("Aces/set", "aces_per_set", "dec2"), ("K/set", "kills_per_set", "dec2")],
    "Back row": [("Digs/set", "digs_per_set", "dec2"),
                 ("Rec/set", "receptions_per_set", "dec2"),
                 ("Rec err", "reception_err_rate", "pct1"),
                 ("Aces/set", "aces_per_set", "dec2")],
}


def page_players(season: str, home: str, away: str) -> None:
    st.markdown('<h1 class="app">Position <span class="accent">Rankings</span></h1>',
                unsafe_allow_html=True)
    pb = D.player_benchmarks()
    c1, c2, c3 = st.columns([1.2, 1.2, 1])
    position = c1.selectbox("Position", D.positions(), index=D.positions().index("Outside hitter")
                            if "Outside hitter" in D.positions() else 0)
    conf = c2.selectbox("Conference", ["All D1"] + D.player_conferences(season), key="pconf")
    scope = c3.selectbox("Show", ["Top 50", "Top 100", "Selected teams only", "Everyone"])

    r = D.player_rankings(season, position,
                          None if conf == "All D1" else conf)
    if scope == "Selected teams only":
        r = r[r.team.isin([home, away])]
    elif scope == "Top 50":
        r = r.head(50)
    elif scope == "Top 100":
        r = r.head(100)
    if r.empty:
        st.info("Nobody matches that filter.")
        return

    specs = pb["groups"].get(position, [])
    graded = ", ".join(s["label"].lower() for s in specs)
    bonus = (" Setters who attack carry a small credit on kills per set."
             if position == "Setter" else "")
    st.markdown(
        f'<p class="sublabel">Rating is the mean percentile on {graded}, computed on values '
        f'adjusted for the opponents she actually faced, against fixed 2022&ndash;2025 '
        f'reference distributions &mdash; so it means the same thing in every season.{bonus} '
        f'The benchmark count beside it is deliberately <em>un</em>adjusted, the same split '
        f'the team pages make between the grade and the power rating. Minimum '
        f'{pb["min_sets"]} sets, and in {pb["recency_rule"]["current_season"]} at least one '
        f'set in the team&rsquo;s last three matches. Ranks stay national under every '
        f'filter.</p>', unsafe_allow_html=True)

    cols = PLAYER_COLUMNS.get(position, [])
    head = ("".join(f'<th style="text-align:right">{lab}</th>' for lab, _, _ in cols))
    html = ['<table class="grid"><thead><tr><th>Rank</th><th>Player</th><th>Team</th>'
            '<th>Conference</th><th style="text-align:right">Sets</th>'
            '<th style="text-align:right">Rating</th>'
            f'<th style="text-align:right">Bench</th>{head}</tr></thead><tbody>']
    for _, row in r.iterrows():
        hl = ' class="hl"' if row.team in (home, away) else ""
        rank = int(row.rank_in_position) if pd.notna(row.rank_in_position) else "&mdash;"
        bench = (f'{row.benchmarks_met:.0f}/{int(row.benchmarks_of)}'
                 if pd.notna(row.benchmarks_met) else "&mdash;")
        cells = "".join(f'<td class="n">{fmt(row.get(c), k)}</td>' for _, c, k in cols)
        html.append(
            f'<tr{hl}><td class="n">{rank}</td><td><b>{row.player}</b></td>'
            f'<td>{T.chip(row.team, ".85rem")}</td><td>{row.conference or ""}</td>'
            f'<td class="n">{row.sets:.0f}</td><td class="n">{row.rating:.1f}</td>'
            f'<td class="n">{bench}</td>{cells}</tr>')
    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)

    with st.expander("What this board does not fix"):
        oa = pb["opponent_adjustment"]
        st.markdown(f"- **Usage.** {oa['does_not_fix']}")
        st.markdown(
            "- **Position labels.** Only about half of teams give their opposite a label "
            "of her own; the rest are listed as outside hitters and are ranked there. The "
            "passing adjustment absorbs some of it, since an opposite who never passes is "
            "measured against outsides who do.")
        st.markdown(
            "- **Small samples early in a season.** The set minimum is a season-long floor, "
            "so in the first weeks a board is ordered on twenty-odd sets and will move a "
            "lot.")
        st.markdown(
            "- **Serving aggression.** Every board grades aces per set, the most reliable "
            "serving measure there is and the one that tracks winning serve rallies. It "
            "does not separate a good server from an aggressive one: aces and service "
            "errors per set correlate about +0.85, so serving is close to a single axis, "
            "and the balance measures that would separate them do not repeat well enough "
            "to grade. Players who never serve &mdash; 43% of middles and 61% of opposites, "
            "who have a serving sub go in for them &mdash; carry no serving benchmark "
            "rather than a zero, and are graded out of one fewer.")
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
