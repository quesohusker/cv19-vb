"""Simulate the rest of the season, the NCAA field it produces, and that tournament.

ONE RUN
-------
1. Every unplayed regular-season match is decided by a weighted coin at the matchup
   predictor's probability (Elo + ridge + home edge, app_data/matchup_model.json).
2. Elo moves after every simulated match, so a team that starts losing keeps sliding
   and the spread of outcomes widens the way a real season's does. The ridge stays at
   today's fit; refitting it 5,000 times over is not worth what it would add.
3. The field is built from that simulated season exactly as the Bracket tab builds it
   (app/bracket.py): an automatic bid to each conference's regular-season champion,
   at-large picks and an S-curve of seeds by the chosen order. Two orders are built
   every run: committee-style, by an RPI recomputed from that run's results, and power,
   by the composite rating with that run's Elo.
4. Each field is played out as a tournament, Elo still moving, with the home edge for
   the top-16 campus hosts in the first two rounds.

THE UPDATE SIZE
---------------
A real Elo update is scaled by the rally margin, which a simulated match does not have.
The margin term is replaced by its average over real matches, ln(margin + 1) ~ 1.47 in
every season checked; the damping on the favourite's edge is kept as it is.

LIMITS
------
- Conference tournaments are not modelled; the regular-season champion takes the bid.
- Results come from app_data/matches.parquet, which drops the ~6% of matches whose
  play-by-play and box score could not be joined (Louisiana's 2026 home matches among
  them). RPI and standings are computed without those matches.
- Unseeded teams are placed by rank, not geography.

Usage:
    python3 analytics/tournament_sim.py --sims 5000 --seed 2026
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analytics"))
from app import bracket as BR      # noqa: E402
from app import data as D          # noqa: E402
import elo_ratings as E            # noqa: E402
import power_ratings as P          # noqa: E402

MARGIN_TERM = 1.47       # mean ln(rally margin + 1) over 2024-2026 real matches
FALLBACK_PCT = 0.05      # rating for a team never seen, as in matchup_model.project
INDEPENDENT = "DI Independent"
ROUNDS = ["first round", "second round", "regional semifinal", "regional final",
          "national semifinal", "final", "champion"]
HOSTPOS = [next(4 * p + o for o in range(4) if (BR.REGION_SEEDS[4 * p + o] or 99) <= 4)
           for p in range(4)]


# ---------------------------------------------------------------- inputs
def inputs(season: str, matches: pd.DataFrame | None = None,
           sched: pd.DataFrame | None = None, coef: tuple | None = None) -> dict:
    """Today's inputs by default. A backtest passes the matches played by its cutoff,
    the schedule left after it, and coefficients fitted without the season it tests."""
    m = D.matches() if matches is None else matches
    cur = m[m.season == season].dropna(subset=["opponent"])
    home = cur[cur.location == "home"]
    sched = D.schedule() if sched is None else sched
    sched = sched[sched.season == season].sort_values("date")
    ts = D.team_seasons()
    ts = ts[ts.season == season]
    conf = ts[ts.conference.notna() & (ts.conference != "")].set_index("team").conference

    teams = sorted(set(home.team) | set(home.opponent) | set(sched.home) | set(sched.away))
    ix = {t: i for i, t in enumerate(teams)}

    elo_all, _ = E.run(E.match_frame(m), E.EloConfig())
    fit = P.fit_season(cur.rename(columns={"opponent": "opponent_matched"}), 1.0)
    rated = fit[fit.n_matches >= 5]
    ridge_all = fit.set_index("team").rating_overall
    d1_rated = [t for t in rated.team if t in conf.index]
    fb_elo = float(np.quantile([elo_all[t] for t in d1_rated if t in elo_all], FALLBACK_PCT))
    fb_ridge = float(rated[rated.team.isin(d1_rated)].rating_overall.quantile(FALLBACK_PCT))
    elo0 = np.array([elo_all.get(t, fb_elo) for t in teams])
    ridge = np.array([ridge_all.get(t, fb_ridge) for t in teams])

    played = pd.DataFrame({"h": home.team.map(ix).to_numpy(),
                           "a": home.opponent.map(ix).to_numpy(),
                           "hw": home.won.astype(int).to_numpy()})
    remain = pd.DataFrame({"h": sched.home.map(ix).to_numpy(),
                           "a": sched.away.map(ix).to_numpy()})
    is_d1 = np.array([t in conf.index for t in teams])
    conf_of = np.array([conf.get(t, "") for t in teams], dtype=object)
    if coef is None:
        c = D.matchup_model()["coef"]
        coef = (c["home"], c["elo_per_100"], c["ridge_per_10"])
    return {"teams": teams, "ix": ix, "elo0": elo0, "ridge": ridge, "played": played,
            "remain": remain, "is_d1": is_d1, "conf_of": conf_of,
            "rated": np.array([t in set(d1_rated) for t in teams]),
            "coef": tuple(coef),
            "cfg": E.EloConfig(), "through": cur.match_date.max(),
            "sched_last": sched.date.max()}


def win_prob(coef, elo_h, elo_a, ridge_h, ridge_a, v):
    z = coef[0] * v + coef[1] * (elo_h - elo_a) / 100.0 + coef[2] * (ridge_h - ridge_a) / 10.0
    return 1.0 / (1.0 + np.exp(-z))


def elo_step(elo, h, a, hw, cfg, home: bool):
    """One Elo update, vectorised over runs. hw is 1 where the first side won."""
    d = elo[..., h] - elo[..., a] + (cfg.home_adv if home else 0.0)
    exp = 1.0 / (1.0 + 10.0 ** (-d / 400.0))
    edge = np.where(hw > 0, d, -d)
    mult = MARGIN_TERM * (2.2 / (0.001 * edge + 2.2))
    delta = cfg.k * mult * (hw - exp)
    return delta


# ---------------------------------------------------------------- season
def simulate_season(I: dict, n: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """Outcomes of every remaining match (n x matches, 1 = home won) and final Elo."""
    elo = np.tile(I["elo0"], (n, 1))
    r = I["remain"]
    out = np.zeros((n, len(r)), dtype=np.int8)
    for k, (h, a) in enumerate(zip(r.h.to_numpy(), r.a.to_numpy())):
        p = win_prob(I["coef"], elo[:, h], elo[:, a], I["ridge"][h], I["ridge"][a], 1.0)
        hw = (rng.random(n) < p).astype(np.float64)
        delta = elo_step(elo, h, a, hw, I["cfg"], home=True)
        elo[:, h] += delta
        elo[:, a] -= delta
        out[:, k] = hw
    return out, elo


def rpi_matrix(I: dict, sim_out: np.ndarray) -> np.ndarray:
    """RPI for every team in every run: 25% WP, 50% OWP (minus games against the team),
    25% OOWP, Division I matches only. Vectorised over runs."""
    T = len(I["teams"])
    pl, rm = I["played"], I["remain"]
    gx = np.concatenate([pl.h.to_numpy(), rm.h.to_numpy()])
    gy = np.concatenate([pl.a.to_numpy(), rm.a.to_numpy()])
    n = sim_out.shape[0]
    O = np.concatenate([np.tile(pl.hw.to_numpy(), (n, 1)), sim_out], axis=1).astype(np.float32)
    keep = I["is_d1"][gx] & I["is_d1"][gy]
    gx, gy, O = gx[keep], gy[keep], O[:, keep]
    Ng = len(gx)
    Ax = np.zeros((Ng, T), np.float32); Ax[np.arange(Ng), gx] = 1
    Ay = np.zeros((Ng, T), np.float32); Ay[np.arange(Ng), gy] = 1
    W = O @ Ax + (1 - O) @ Ay                                  # n x T wins
    G = Ax.sum(0) + Ay.sum(0)                                  # games, same every run
    # head to head inside each unordered pair, to strip it from the opponent's record
    lo, hi = np.minimum(gx, gy), np.maximum(gx, gy)
    pair_id, pair_of = np.unique(lo * T + hi, return_inverse=True)
    Q = len(pair_id)
    lo_is_x = (gx == lo).astype(np.float32)
    Pq = np.zeros((Ng, Q), np.float32); Pq[np.arange(Ng), pair_of] = 1
    lo_wins = (O * lo_is_x + (1 - O) * (1 - lo_is_x)) @ Pq     # n x Q
    pq_games = Pq.sum(0)
    # team-game rows: (team t, opponent o, pair q)
    rt = np.concatenate([gx, gy]); ro = np.concatenate([gy, gx])
    rq = np.concatenate([pair_of, pair_of])
    t_is_lo = rt == np.minimum(rt, ro)
    o_wins_vs_t = np.where(t_is_lo[None, :], pq_games[rq][None, :] - lo_wins[:, rq], lo_wins[:, rq])
    num = W[:, ro] - o_wins_vs_t
    den = G[ro] - pq_games[rq]
    owp_row = np.where(den > 0, num / np.maximum(den, 1), np.nan)
    R = np.zeros((len(rt), T), np.float32); R[np.arange(len(rt)), rt] = 1
    cnt = R.sum(0)
    owp = np.nan_to_num(owp_row) @ R / np.maximum((~np.isnan(owp_row)) @ R, 1)
    oowp = owp[:, ro] @ R / np.maximum(cnt, 1)
    wp = W / np.maximum(G, 1)
    rpi = 0.25 * wp + 0.50 * owp + 0.25 * oowp
    rpi[:, G == 0] = np.nan
    return rpi


def conference_champions(I: dict, sim_out: np.ndarray, elo_end: np.ndarray) -> np.ndarray:
    """Regular-season champion per conference per run (team index), ties to higher Elo."""
    pl, rm = I["played"], I["remain"]
    conf = I["conf_of"]
    gx = np.concatenate([pl.h.to_numpy(), rm.h.to_numpy()])
    gy = np.concatenate([pl.a.to_numpy(), rm.a.to_numpy()])
    n = sim_out.shape[0]
    O = np.concatenate([np.tile(pl.hw.to_numpy(), (n, 1)), sim_out], axis=1).astype(np.float32)
    same = (conf[gx] == conf[gy]) & (conf[gx] != "")
    gx, gy, O = gx[same], gy[same], O[:, same]
    T = len(I["teams"])
    W = np.zeros((n, T), np.float32); G = np.zeros(T, np.float32)
    np.add.at(W.T, gx, O.T); np.add.at(W.T, gy, (1 - O).T)
    np.add.at(G, gx, 1); np.add.at(G, gy, 1)
    pct = W / np.maximum(G, 1)
    # independents (2023: Chicago St.) share a label, not a league, and get no bid
    confs = sorted({c for c in conf if c and c != INDEPENDENT
                    and ((conf == c) & (G > 0)).any()})
    champs = np.zeros((n, len(confs)), dtype=np.int32)
    for k, c in enumerate(confs):
        members = np.where((conf == c) & (G > 0))[0]
        score = pct[:, members] * 1e4 + elo_end[:, members] / 1e4   # Elo only breaks ties
        champs[:, k] = members[np.argmax(score, axis=1)]
    return champs


# ---------------------------------------------------------------- tournament
def play_bracket(I, slots: list[int], elo: np.ndarray, rng) -> dict[int, int]:
    """One tournament on one field. Returns team -> furthest round (1-7, 7 = champion)."""
    coef, ridge, cfg = I["coef"], I["ridge"], I["cfg"]
    elo = elo.copy()
    reached = {t: 1 for t in slots}
    alive = list(slots)
    for r in range(1, 7):
        nxt = []
        for j in range(len(alive) // 2):
            a, b = alive[2 * j], alive[2 * j + 1]
            host = None
            if r <= 2:
                pod = j // 2 if r == 1 else j
                host = slots[16 * (pod // 4) + HOSTPOS[pod % 4]]
            v = 1.0 if host == a else -1.0 if host == b else 0.0
            p = win_prob(coef, elo[a], elo[b], ridge[a], ridge[b], v)
            aw = 1.0 if rng.random() < p else 0.0
            # Elo's own update, from a's side; the home edge goes to whichever side hosts
            d = elo[a] - elo[b] + cfg.home_adv * v
            exp = 1.0 / (1.0 + 10.0 ** (-d / 400.0))
            mult = MARGIN_TERM * (2.2 / (0.001 * (d if aw else -d) + 2.2))
            delta = cfg.k * mult * (aw - exp)
            elo[a] += delta; elo[b] -= delta
            w = a if aw else b
            nxt.append(w)
            reached[w] = r + 1
        if r == 4:                                      # national semis: 1 v 4, 2 v 3
            nxt = [nxt[0], nxt[3], nxt[1], nxt[2]]
        alive = nxt
    return reached


def run(season: str, sims: int, seed: int, chunk: int = 1000,
        I: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """I: prepared inputs (see inputs()), for a backtest; default is today's."""
    rng = np.random.default_rng(seed)
    I = I or inputs(season)
    teams, is_d1 = I["teams"], I["is_d1"]
    d1_idx = np.where(is_d1)[0]
    rows = []
    t0 = time.time()
    for start in range(0, sims, chunk):
        n = min(chunk, sims - start)
        out, elo_end = simulate_season(I, n, rng)
        rpi = rpi_matrix(I, out)
        champs = conference_champions(I, out, elo_end)
        # composite: half Elo, half ridge, in z-scores over rated D1 teams
        rated = np.where(I["rated"])[0]
        ze = (elo_end[:, rated] - elo_end[:, rated].mean(1, keepdims=True)) / elo_end[:, rated].std(1, keepdims=True)
        rr = I["ridge"][rated]
        zr = (rr - rr.mean()) / rr.std()
        comp = np.full((n, len(teams)), -np.inf)
        comp[:, rated] = 0.5 * ze + 0.5 * zr
        for s in range(n):
            auto = set(champs[s].tolist())
            for basis, score in (("committee", rpi[s]), ("power", comp[s])):
                sc = np.where(is_d1, np.nan_to_num(score, nan=-np.inf), -np.inf)
                order = [int(t) for t in np.argsort(-sc) if is_d1[t] and np.isfinite(sc[t])]
                at_large = [t for t in order if t not in auto][:BR.FIELD - len(auto)]
                inn = set(at_large) | auto
                field = [t for t in order if t in inn]
                slots = BR.place(field)
                reached = play_bracket(I, slots, elo_end[s], rng)
                for pos, t in enumerate(slots):
                    rows.append((start + s, basis, t, field.index(t) + 1, pos // 16 + 1,
                                 BR.REGION_SEEDS[pos % 16] or 0, t in auto, reached[t],
                                 pos))
        print(f"  {start + n:,} runs  ({time.time() - t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows, columns=["sim", "basis", "team", "overall", "region", "seed",
                                     "auto", "reached", "slot"])
    df["team"] = [teams[t] for t in df.team]
    meta = {"season": season, "sims": sims, "seed": seed,
            "through": str(I["through"].date()), "schedule_to": str(I["sched_last"].date()),
            "remaining_matches": int(len(I["remain"]))}
    return df, meta


def summarise(df: pd.DataFrame, sims: int) -> pd.DataFrame:
    g = df.groupby(["basis", "team"])
    out = pd.DataFrame({
        "p_field": g.size() / sims,
        "p_auto": g.auto.sum() / sims,
        "mean_overall": g.overall.mean(),
        "p_host": g.seed.apply(lambda s: ((s >= 1) & (s <= 4)).sum()) / sims,
        "p_1seed": g.seed.apply(lambda s: (s == 1).sum()) / sims,
    })
    for k, name in enumerate(ROUNDS[1:], start=2):
        out[f"p_{name.replace(' ', '_')}"] = g.reached.apply(lambda r, k=k: (r >= k).sum()) / sims
    return out.reset_index().sort_values(["basis", "p_champion"], ascending=[True, False])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--season", default=None)
    ap.add_argument("--sims", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out-dir", type=Path, default=Path("analysis"))
    args = ap.parse_args()
    season = args.season or D.matchup_model()["current_season"]
    df, meta = run(season, args.sims, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    df.astype({"sim": "int32", "overall": "int16", "region": "int8", "seed": "int8",
               "reached": "int8", "slot": "int8"}).to_parquet(
        args.out_dir / f"tournament_sim_{season}_runs.parquet", compression="zstd", index=False)
    summ = summarise(df, args.sims)
    summ.to_csv(args.out_dir / f"tournament_sim_{season}_summary.csv", index=False)
    pd.Series(meta).to_json(args.out_dir / f"tournament_sim_{season}_meta.json", indent=1)
    print(meta)
    print(summ[summ.basis == "committee"].head(12).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
