# cv19-vb — College Volleyball Analytics

NCAA Division I women's volleyball: a data pipeline over play-by-play, an empirically
derived match grading system, opponent-adjusted power ratings, and a Streamlit app.

Sibling to [cv19](https://github.com/quesohusker/cv19) (college football), kept
separate on purpose — different data, different pipeline, different app.

## The app

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Four views: **Stat Comparison**, **The Volleyball 7**, **Power Rankings**, **How it works**.
Deploy on Streamlit Community Cloud with main file path `streamlit_app.py`.

## Two numbers, two jobs

**The Volleyball 7** grades a match — how many of seven benchmarks a team cleared.
Thresholds are empirical: each is the value that best separated winning from losing
performances across 2021–2023, constrained so 30–70% of team-matches clear it, then
validated out of sample. Season grade correlates **r = +0.960** with season win
percentage, stable across all five seasons.

| Benchmark | Phase |
|---|---|
| Side-out % ≥ 58.3% | side-out |
| First-ball side-out % ≥ 32.5% | in-system offense |
| Hitting efficiency ≥ .199 | attack |
| Point-score % ≥ 41.9% | serve phase |
| Opp hitting efficiency ≤ .199 | defense |
| Ace-to-service-error ≥ 0.53 | serve |
| Out-hit the opponent | attack vs defense |

**Power ratings** rank teams. One ridge regression per season fits
`sideout = μ + off_i − def_j` over every team-match; since point-score rate is one
minus the opponent's side-out rate, that single model covers both phases. The grade is
unadjusted and rewards a soft schedule, so it grades but never ranks.

## Layout

| path | role |
|---|---|
| `streamlit_app.py` | app entry point (root, for Streamlit Cloud) |
| `app/` | data loaders and the design system |
| `app_data/` | precomputed tables the app reads (2.4 MB, committed) |
| `analytics/` | the pipeline that produces `app_data/` |
| `data_collection/` | collectors that fetch the raw NCAA data |
| `data/` | raw play-by-play and derived tables (gitignored, ~8.8 GB) |

## Pipeline

```bash
python data_collection/collect_all.py        # fetch raw NCAA data (~8.8 GB)
python analytics/rally_engine.py data/ncaavolleyballr/data-csv/wvb_pbp_div1_2025.csv \
    --out-dir data/rallies                   # pbp -> rally table (92x smaller)
python analytics/build_match_metrics.py      # rally + box score -> match metrics
python analytics/build_app_data.py           # -> app_data/, incl. power ratings
```

Coverage: women's D1, 2021–2025, 45,288 graded team-matches.

## Reading the code

Each analysis module documents what was tested and rejected, with the numbers, so
dead ends do not get re-explored:

- `analytics/benchmarks.py` — why seven and not fourteen; why only hitting is a margin;
  why transition share was rejected
- `analytics/in_system.py` — in-system detection, and why it grades attacks well but
  cannot grade teams
- `analytics/rally_engine.py` — the pbp schema quirk that inverts a quarter of rallies
  if read naively
