"""Build a rally table from ncaa-api point-summary play-by-play.

The old stats.ncaa.org feed gave a touch-level stream -- serve, reception, set,
attack, dig, first-ball kill -- and analytics/rally_engine.py keys rallies off the
Serve rows. That feed is gone: every /teams/<id> path now returns Access Denied.
The ncaa-api mirror answers, but its play-by-play is point-summary: the event that
ended each rally, plus substitutions, and nothing between. There are no Serve rows
to key on, so this is a separate extractor rather than a tweak to that one.

RECONSTRUCTING SERVE ORDER. Under rally scoring the winner of a rally serves the
next one, so within a set only the FIRST server is unknown -- every later serve is
forced by the previous rally's winner. That single unknown per set is resolved in
order of preference:

  1. The set's opening rally ends in an ace (the server scored) or a service error
     (the server lost), which names the server outright.
  2. Otherwise, try both options for every set and keep the combination whose
     implied serve counts best match the box score's serve attempts.
  3. Failing both, assume the away team opened and alternate by set, and say so.

Validated against a real match (Utah Tech at Hawaii, 2026-09-04): reconstructed
serve counts matched the box score exactly, 74/74 and 54/54, with no ace or
service-error anchor contradicted.

WHAT THIS CANNOT PRODUCE. `first_ball` needs to know whether the receiving team
scored on its first attack, and a point-summary feed never says. It is written as
null rather than false, and `has_touch_detail` is false on every row, so
build_match_metrics.py can null out first-ball side-out and transition side-out
instead of silently reporting them as zero. `server`, `passer` and touch counts
are unavailable for the same reason.

Usage:
    python3 analytics/rally_from_ncaa_api.py 2026 \\
        --serve-attempts ../volleyball-gis/public/data/wvb_playermatch_div1_2026.csv
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# playText phrasing -> the event vocabulary rally_engine established, so the
# downstream SQL (kill points, block points, opponent error points) is unchanged
EVENT_PATTERNS = [
    (re.compile(r"\bservice ace\b", re.I), "Ace"),
    (re.compile(r"\bservice error\b", re.I), "Service error"),
    (re.compile(r"\battack error\b", re.I), "Attack error"),
    (re.compile(r"\bblock(ing)? error\b", re.I), "Block error"),
    (re.compile(r"\bbad set\b|\bset error\b", re.I), "Set error"),
    (re.compile(r"\bball handling error\b", re.I), "Ball handling error"),
    (re.compile(r"\bdig error\b", re.I), "Dig error"),
    (re.compile(r"\bkill\b", re.I), "Kill"),
    (re.compile(r"\bblock\b", re.I), "Block"),
]
BY_PLAYER = re.compile(r"\bby ([A-Z][^.(,]*?)(?:\s*\(|\.|,|$)")


def classify(text: str) -> str:
    for pat, label in EVENT_PATTERNS:
        if pat.search(text):
            return label
    return "Other"


def actor(text: str) -> str | None:
    m = BY_PLAYER.search(text or "")
    return m.group(1).strip() if m else None


def read_match(path: Path) -> dict | None:
    """One pbp file -> teams, and the rally-ending events per set, in order."""
    d = json.loads(path.read_text())
    teams = d.get("teams") or []
    if len(teams) != 2:
        return None
    home = next((t for t in teams if t.get("isHome")), None)
    away = next((t for t in teams if not t.get("isHome")), None)
    if home is None or away is None:
        return None

    # Resolve the rally winner by team ID, never by name. The names arrive from two
    # places -- the scoreboard (carried in on _away_team/_home_team) and the pbp
    # payload's own teams array -- and they are not always byte-identical: "LSU New
    # Orleans " comes back from one with a trailing space, which used to blow up the
    # serve counter with a KeyError on a name that looked correct in the message.
    away_name = (d.get("_away_team") or away.get("nameShort") or "").strip()
    home_name = (d.get("_home_team") or home.get("nameShort") or "").strip()
    if not away_name or not home_name:
        return None
    by_id = {str(home.get("teamId")): home_name, str(away.get("teamId")): away_name}

    sets: list[list[dict]] = []
    for p in d.get("periods") or []:
        rallies = []
        for ev in p.get("playbyplayStats") or []:
            tid = str(ev.get("teamId"))
            for pl in ev.get("plays") or []:
                if pl.get("homeScore") is None:
                    continue          # substitution, timeout, roster line
                winner = by_id.get(tid)
                if winner is None:
                    continue
                rallies.append({
                    "winner": winner,
                    "end_event": classify(pl.get("playText", "")),
                    "end_player": actor(pl.get("playText", "")),
                    "after_home": pl.get("homeScore"),
                    "after_away": pl.get("visitorScore"),
                })
        if rallies:
            sets.append(rallies)
    if not sets:
        return None
    return {"date": d.get("_date"), "away_team": away_name,
            "home_team": home_name, "sets": sets}


def opening_anchor(rallies: list[dict], away: str, home: str) -> str | None:
    """An opening ace or service error names the server outright."""
    first = rallies[0]
    other = away if first["winner"] == home else home
    if first["end_event"] == "Ace":
        return first["winner"]
    if first["end_event"] == "Service error":
        return other
    return None


def serve_counts(sets, openers, away, home) -> dict:
    counts = {away: 0, home: 0}
    for rallies, opener in zip(sets, openers):
        server = opener
        for r in rallies:
            counts[server] += 1
            server = r["winner"]
    return counts


def choose_openers(sets, away, home, box: dict | None) -> tuple[list[str], str, float | None]:
    """Pick the first server of each set. Returns the choice and how it was made."""
    anchors = [opening_anchor(r, away, home) for r in sets]
    free = [i for i, a in enumerate(anchors) if a is None]
    if not free:
        return anchors, "anchored", None

    if box and (box.get(away) or box.get(home)):
        best, best_err = None, None
        for combo in itertools.product((away, home), repeat=len(free)):
            trial = list(anchors)
            for i, t in zip(free, combo):
                trial[i] = t
            c = serve_counts(sets, trial, away, home)
            err = sum(abs(c[t] - box[t]) for t in (away, home) if box.get(t) is not None)
            if best_err is None or err < best_err:
                best, best_err = trial, err
        if best_err == 0:
            return best, "matched box score exactly", 0.0
        return best, "closest to box score", float(best_err)

    # nothing to go on: assume the away team opened and alternate
    out, cur = [], away
    for i, a in enumerate(anchors):
        out.append(a if a is not None else cur)
        cur = home if out[-1] == away else away
    return out, "assumed (no anchor, no box score)", None


def match_rows(m: dict, box: dict | None) -> tuple[list[dict], str, float | None]:
    away, home = m["away_team"], m["home_team"]
    openers, how, err = choose_openers(m["sets"], away, home, box)
    rows = []
    for set_idx, (rallies, opener) in enumerate(zip(m["sets"], openers), start=1):
        server = opener
        sa = sh = 0                      # score BEFORE each rally, our convention
        for rally_no, r in enumerate(rallies, start=1):
            recv = away if server == home else home
            rows.append({
                "date": m["date"], "away_team": away, "home_team": home,
                "set_no": set_idx, "rally_no": rally_no,
                "serve_team": server, "recv_team": recv, "winner": r["winner"],
                "server": None, "passer": None,
                "end_event": r["end_event"], "end_player": r["end_player"],
                "first_ball": None, "touches": None,
                "score_away": sa, "score_home": sh,
                "has_touch_detail": False,
            })
            if r["winner"] == away:
                sa += 1
            else:
                sh += 1
            server = r["winner"]
    return rows, how, err


def load_serve_attempts(path: Path | None) -> dict:
    """(date, team, opponent) -> serve attempts, summed from the player box scores.

    The opponent belongs in the key. Teams play twice on one date in tournaments,
    and keying on (date, team) alone silently sums both matches -- Utah Tech came
    out with 160 serve attempts on 2026-09-04 against a true 54, which would have
    steered the opener search badly wrong.
    """
    if not path or not path.exists():
        return {}
    out: dict[tuple[str, str, str], float] = defaultdict(float)
    for r in csv.DictReader(open(path, newline="")):
        try:
            out[(r["Date"], r["Team"], r["Opponent Team"])] += float(r.get("ServeAtt") or 0)
        except ValueError:
            continue
    return dict(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("year", type=int)
    ap.add_argument("--pbp-dir", type=Path)
    ap.add_argument("--serve-attempts", type=Path,
                    help="volleyball-gis playermatch CSV, used to disambiguate openers")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sport", default="wvb")
    ap.add_argument("--division", default="div1")
    args = ap.parse_args()

    pbp_dir = args.pbp_dir or Path(f"data/ncaa_api/pbp/{args.year}")
    files = sorted(pbp_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No pbp files in {pbp_dir}\n"
                         f"Run: python3 data_collection/fetch_ncaa_pbp.py {args.year}")
    serve_att = load_serve_attempts(args.serve_attempts)

    all_rows, how_counts, skipped = [], defaultdict(int), 0
    serve_errors: list[float] = []
    failures = []
    for f in files:
        try:
            m = read_match(f)
        except Exception as e:                                    # noqa: BLE001
            failures.append((f.name, str(e)[:70]))
            m = None
        if m is None:
            skipped += 1
            continue
        box = None
        if serve_att and m["date"]:
            iso = f"{m['date'][6:]}-{m['date'][0:2]}-{m['date'][3:5]}"   # MM/DD/YYYY -> ISO
            a, h = m["away_team"], m["home_team"]
            box = {a: serve_att.get((iso, a, h)), h: serve_att.get((iso, h, a))}
            if not any(v for v in box.values()):
                box = None
        try:
            rows, how, err = match_rows(m, box)
        except Exception as e:                                    # noqa: BLE001
            failures.append((f.name, str(e)[:70]))
            skipped += 1
            continue
        how_counts[how.split(" (")[0]] += 1
        if err:
            serve_errors.append(err)
        all_rows.extend(rows)

    if not all_rows:
        raise SystemExit("No rallies extracted.")

    def col(name):
        return pa.array([r[name] for r in all_rows])

    def dic(name):
        # an all-null column cannot be dictionary-encoded; server and passer are
        # always null here because the feed carries no touch detail
        a = col(name)
        if a.null_count == len(a):
            return pa.array([None] * len(a), pa.string())
        return a.dictionary_encode()

    table = pa.table({
        "date": col("date"),
        "away_team": dic("away_team"), "home_team": dic("home_team"),
        "set_no": pa.array([r["set_no"] for r in all_rows], pa.int8()),
        "rally_no": pa.array([r["rally_no"] for r in all_rows], pa.int16()),
        "serve_team": dic("serve_team"), "recv_team": dic("recv_team"),
        "winner": dic("winner"), "server": dic("server"), "passer": dic("passer"),
        "end_event": dic("end_event"), "end_player": dic("end_player"),
        "first_ball": pa.array([r["first_ball"] for r in all_rows], pa.bool_()),
        "touches": pa.array([r["touches"] for r in all_rows], pa.int16()),
        "score_away": pa.array([r["score_away"] for r in all_rows], pa.int16()),
        "score_home": pa.array([r["score_home"] for r in all_rows], pa.int16()),
        "has_touch_detail": pa.array([r["has_touch_detail"] for r in all_rows], pa.bool_()),
    })
    out = args.out or Path(
        f"data/rallies/{args.sport}_rallies_{args.division}_{args.year}.parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out, compression="zstd")

    matches = len({(r["date"], r["away_team"], r["home_team"]) for r in all_rows})
    print(f"wrote {out}  ({out.stat().st_size / 1e6:.1f} MB)")
    print(f"  {len(all_rows):,} rallies over {matches:,} matches "
          f"({skipped:,} files skipped)")
    if failures:
        print(f"  {len(failures)} match(es) failed to parse, e.g.:")
        for name, err in failures[:5]:
            print(f"    {name}: {err}")
    print("  first server decided by:")
    for how, n in sorted(how_counts.items(), key=lambda x: -x[1]):
        print(f"    {how:<34}{n:,}")
    if serve_errors:
        s = sorted(serve_errors)
        # the opener is one rally per set, so a mismatch of 1-2 serves is that single
        # ambiguity, not a broken reconstruction. Anything large means the box score
        # and the play-by-play disagree about the match itself.
        print(f"  where it did not match exactly, serve-count error: "
              f"median {s[len(s) // 2]:.0f}, "
              f"{sum(1 for x in s if x <= 2) / len(s) * 100:.0f}% within 2, "
              f"max {s[-1]:.0f}")
    print("  first_ball is null throughout: this feed has no touch detail, so\n"
          "  first-ball and transition side-out cannot be computed for this season.")


if __name__ == "__main__":
    main()
