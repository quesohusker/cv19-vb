# Tournament facts kept by hand

Two files the NCAA feed cannot supply. Both are read by the Bracket tab
(`app/bracket.py`) and the simulator (`analytics/tournament_sim.py`), and both must be
committed: `publish.sh` refuses to run while anything outside `app_data/` is changed
and uncommitted.

## `auto_bids_<season>.csv`: automatic bids already won

One row per conference whose bid is decided:

```
conference,team,clinched,how,source
America East,New Hampshire,2026-11-21,conference tournament,<url>
```

- `conference` must match the app's label exactly. The 2026 labels are in
  `data_collection/conferences_2026.csv`, for example `Pac-12`, `UAC`, `Big Ten`.
- `team` must match the app's spelling: `Eastern Ky.`, not `Eastern Kentucky`.
- A row whose team or conference the data does not recognize is skipped, and the
  simulator prints a warning naming it.
- NCAA.com keeps the official list: "Tracking all 32 automatic qualifiers".

## `official_bracket_<season>.csv`: the committee's bracket

One row per team, 64 rows:

| column | meaning |
|---|---|
| `region` | region name as printed, or the 1 seed's name |
| `region_order` | 1-4 in printed order: 1 top left, 2 bottom left, 3 top right, 4 bottom right. The national semifinals are 1 v 2 and 3 v 4. |
| `line` | 1-16, top to bottom within the region. Lines 1-2 meet in the first round, and lines 1-4 form one campus pod. |
| `seed` | 1-8, or blank if unseeded |
| `team` | the app's spelling |
| `pod_host` | `Y` on the team hosting its pod's first and second rounds |
| `regional_host` | `Y` on the team hosting its region's semifinal and final. Leave it blank for a neutral site. |

Regional hosts are not set at selection. The NCAA names them by Dec. 6, 2026. In
2025 all four 1 seeds hosted. Leave the column blank, or mark the 1 seeds as a
provisional guess, and correct it once the hosts are announced.

## Selection Sunday (Nov. 29, 2026)

1. Update the data as usual.
2. Build the bracket file. Either:
   - Claude fills it from the official bracket, or
   - you start from a template of the projected field and edit it to match the
     official bracket, saving it as `tournament/official_bracket_2026.csv`.
3. Check it. It prints every first-round match with its host, or lists each problem,
   with suggested spellings for unknown teams.
4. Simulate. This writes `analysis/tournament_official_2026_summary.csv`.
5. Commit and push. The Bracket tab then opens on "Official NCAA bracket".

```
cd /Users/pauldalen/Claude/Projects/cv19-vb && git pull && ./scripts/publish.sh 2026
```

```
.venv/bin/python analytics/official_bracket.py 2026 --template
```

```
.venv/bin/python analytics/official_bracket.py 2026
```

```
.venv/bin/python analytics/tournament_sim.py --official
```

```
git add tournament analysis/tournament_official_2026_* && git commit -m "Official 2026 bracket" && git push
```

During the tournament, rerun the last two commands after each round. Matches already
played keep their real results, so the odds cover only what is left.
