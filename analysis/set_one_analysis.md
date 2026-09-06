# Set One Among Equals — data appendix

*Generated 2026-09-06T23:19:40+00:00*

NCAA women's volleyball, Division I, 2021–2025. 501 top-25 matchups (1,002 team-matches) out of 44,892 graded team-matches.

**Scope.** Headline analysis restricted to matches where BOTH teams ranked in the top 25 of the opponent-adjusted power rating for that season. That rating is a ridge regression on side-out rate, not the AVCA poll.

**Set facts.** Set winners, margins and checkpoint leads are read from the play-by-play score columns, not by counting rallies won. The two disagree on ~10% of sets because rally_engine drops malformed and abandoned rows; the score column is absolute.

---

## 1. Headline

| Sample | Won set 1 → win | Lost set 1 → win | Swing | Matches |
|---|---|---|---|---|
| Top-25 vs top-25 | 75.6% | 24.3% | +51.3 | 1,002 |
| All D1 | 79.2% | 20.8% | +58.4 | 44,892 |

> The first set is worth LESS between ranked teams than across D1 as a whole. Most of D1 is mismatches, where the first set merely reflects the gap.

### Top-25, by season

| Season | Won set 1 → win | Matches |
|---|---|---|
| 2021 | 76.0% | 104 |
| 2022 | 77.3% | 88 |
| 2023 | 67.7% | 96 |
| 2024 | 84.0% | 106 |
| 2025 | 72.9% | 107 |

---

## 2. Match length

| Sets | Top-25 share | All-D1 share |
|---|---|---|
| 3 | 36.7% | 48.6% |
| 4 | 35.1% | 31.7% |
| 5 | 28.1% | 19.7% |

### What set 1 is worth, by how long the match went

| Sets | Matches | Set-1 winner wins |
|---|---|---|
| 3 | 184 | 100.0% |
| 4 | 176 | 67.6% |
| 5 | 141 | 53.9% |

> Top-25 matches go long far more often, which is why the first set is worth less: fewer of these matches end before it can be avenged.

---

## 3. Set-1 margin

| Set 1 won by | n | Wins match | Sweep |
|---|---|---|---|
| 2 points | 112 | 73.2% | 32.1% |
| 3-4 | 121 | 70.2% | 33.1% |
| 5-7 | 156 | 75.0% | 36.5% |
| 8+ | 111 | 84.7% | 45.1% |

*In the top-25 subset the 3-4 point band sits below the 2-point band. With ~120 matches in each that is noise, not a finding: the trend is real at the ends and mushy in the middle.*

---

## 4. Who was already better

| Matchup | n (team-matches) | Won set 1 | Lost set 1 | Swing |
|---|---|---|---|---|
| underdog (worse by >8) | 81 | 33.3% | 9.5% | +23.8 |
| even (within 8) | 840 | 75.2% | 24.8% | +50.5 |
| favorite (better by >8) | 81 | 90.5% | 66.7% | +23.8 |

> The first set swings the match most where the teams were otherwise even, and roughly half as much where one side was already clearly better. It decides the matches that weren't going to decide themselves.

*Gap units: difference in overall rating, in percentage points of side-out vs an average D1 team.*

---

## 5. Comebacks

**122 of 501** (24.3%) — final scores 3-1 ×57, 3-2 ×65. Mean deficit overcome: 4.68 points.

| Set-1 deficit | n | Comeback rate |
|---|---|---|
| down 2 | 113 | 26.6% |
| down 3-4 | 121 | 29.8% |
| down 5-7 | 156 | 25.0% |
| down 8+ | 111 | 15.3% |

### Largest deficits overcome

| Season | Comeback | Result | Set 1 by |
|---|---|---|---|
| 2023 | Texas over BYU | 3-1 | 12 |
| 2021 | Wisconsin over Nebraska | 3-1 | 11 |
| 2023 | Wisconsin over Florida | 3-2 | 10 |
| 2025 | Indiana over Southern California | 3-1 | 10 |
| 2024 | Florida over Missouri | 3-2 | 10 |
| 2023 | Nebraska over Penn St. | 3-2 | 10 |
| 2024 | Louisville over Florida St. | 3-2 | 9 |
| 2023 | Kentucky over Arkansas | 3-2 | 9 |

---

## 6. Point leads in set 1

*At each checkpoint, the score when either team first reaches that many points in set 1, and who was ahead at that moment.*

| Lead at | n | Wins set 1 | Wins match | Avg lead |
|---|---|---|---|---|
| first to 5 | 501 | 67.3% | 59.3% | 2.2 |
| first to 10 | 501 | 74.1% | 63.7% | 3.19 |
| first to 15 | 501 | 82.6% | 68.3% | 4.05 |
| first to 20 | 501 | 87.4% | 68.7% | 4.74 |

### Lead size at 5 points

| Lead | n | Wins set 1 | Wins match |
|---|---|---|---|
| up 1 | 169 | 58.0% | 52.7% |
| up 2 | 156 | 66.7% | 58.3% |
| up 3-4 | 157 | 76.4% | 65.6% |

### Lead size at 10 points

| Lead | n | Wins set 1 | Wins match |
|---|---|---|---|
| up 1 | 111 | 56.8% | 54.9% |
| up 2 | 92 | 62.0% | 52.2% |
| up 3-4 | 183 | 79.8% | 66.7% |
| up 5+ | 115 | 91.3% | 76.5% |

### Lead size at 15 points

| Lead | n | Wins set 1 | Wins match |
|---|---|---|---|
| up 1 | 81 | 59.3% | 56.8% |
| up 2 | 83 | 71.1% | 59.0% |
| up 3-4 | 144 | 84.7% | 67.4% |
| up 5+ | 193 | 95.9% | 77.7% |

### Lead size at 20 points

| Lead | n | Wins set 1 | Wins match |
|---|---|---|---|
| up 1 | 70 | 71.4% | 50.0% |
| up 2 | 60 | 68.3% | 60.0% |
| up 3-4 | 130 | 86.2% | 68.5% |
| up 5+ | 241 | 97.5% | 76.3% |

### Lead persistence

| Held from | Rate |
|---|---|
| 5 → 10 | 76.4% |
| 10 → 15 | 81.0% |
| 15 → 20 | 86.0% |
| 5 → 20 | 67.9% |

> Being first to 20 wins the SET 87% of the time but the MATCH only 69%, because the set itself is only worth 76%. Lead size matters far more than lead: leading 20-19 is a coin flip for the match, while up 5+ at 10 is already worth what up 5+ at 20 is worth.

---

## 7. Nebraska

Top-25 matchups: **42–14** in 56 matches.

| Situation | Record | Win % |
|---|---|---|
| After winning set 1 | 38–2 | 95.0% |
| After losing set 1 | 4–12 | 25.0% |

### By season (top-25 matchups)

| Season | Record | Set 1 won | Rate | Won S1 | Lost S1 |
|---|---|---|---|---|---|
| 2021 | 8–6 | 9/14 | 64.3% | 7–2 | 1–4 |
| 2022 | 4–5 | 4/9 | 44.4% | 4–0 | 0–5 |
| 2023 | 9–1 | 7/10 | 70.0% | 7–0 | 2–1 |
| 2024 | 12–2 | 12/14 | 85.7% | 12–0 | 0–2 |
| 2025 | 9–0 | 8/9 | 88.9% | 8–0 | 1–0 |

### Point leads in set 1

| Lead at | Led | Of | Rate | Wins match |
|---|---|---|---|---|
| first to 5 | 38 | 56 | 67.9% | 81.6% |
| first to 10 | 41 | 56 | 73.2% | 80.5% |
| first to 15 | 43 | 56 | 76.8% | 83.7% |
| first to 20 | 40 | 56 | 71.4% | 85.0% |

**Trailing at 20 in set 1:** 8–8 (wins the set 25.0%, wins the match 50.0%).

> Nebraska's comeback rate is ordinary. What separates them is the other column: once they take set 1 from a ranked opponent they finish it ~95% of the time.

### Official season records

| Season | Record | Grade /7 |
|---|---|---|
| 2021 | 26–8 | 5.04 |
| 2022 | 26–6 | 5.07 |
| 2023 | 33–2 | 5.62 |
| 2024 | 33–3 | 5.97 |
| 2025 | 33–1 | 6.37 |

---

## 8. Team level

Set-1 rate correlates **+0.671** with win percentage in top-25 matchups (99 team-seasons, min 6 matches).

| Season | Team | Record | Set-1 rate |
|---|---|---|---|
| 2024 | Pittsburgh | 10-1 | 100.0% |
| 2025 | Pittsburgh | 8-3 | 90.9% |
| 2025 | Nebraska | 9-0 | 88.9% |
| 2024 | Nebraska | 12-2 | 85.7% |
| 2024 | Texas | 4-3 | 85.7% |
| 2022 | Arkansas | 2-4 | 83.3% |
| 2022 | Wisconsin | 8-3 | 81.8% |
| 2024 | Penn St. | 8-1 | 77.8% |
| 2023 | Louisville | 6-3 | 77.8% |
| 2025 | Texas A&M | 6-3 | 77.8% |
| 2021 | UCLA | 8-1 | 77.8% |
| 2021 | Louisville | 7-0 | 71.4% |

---

## 9. First to 20, in every set

*Whoever holds the lead at the moment either team first reaches 20 points. Sets 1-4 play to 25; a deciding fifth set plays to 15, so 12 is used there as the analogue and reported separately.*

| Set | n | Wins that set | Wins match | If not first to 20 | Lift |
|---|---|---|---|---|---|
| 1 | 501 | 87.4% | 68.7% | 31.3% | +37.3 |
| 2 | 501 | 83.4% | 66.3% | 33.7% | +32.5 |
| 3 | 501 | 87.2% | 68.7% | 31.3% | +37.3 |
| 4 | 317 | 87.4% | 71.0% | 29.0% | +42.0 |

Deciding fifth set (first to 12 of 15): n=141, wins the set 86.5%. *Winning set 5 is winning the match, so the two figures are the same by definition.*

### How many sets you led at 20

| Sets first to 20 | Top-25 n | Top-25 win % | All-D1 n | All-D1 win % |
|---|---|---|---|---|
| 0 | 137 | 1.5% | 9372 | 1.4% |
| 1 | 235 | 17.9% | 8981 | 14.6% |
| 2 | 324 | 57.1% | 10896 | 59.4% |
| 3 | 287 | 88.8% | 14619 | 92.9% |

### Does it add anything beyond who won the set?

| Condition | n | Wins match |
|---|---|---|
| first to 20 | 1820 | 68.4% |
| won the set | 1816 | 74.8% |
| first to 20 and won set | 1570 | 75.0% |
| won set from behind at 20 | 246 | 74.0% |
| first to 20 but lost set | 250 | 27.2% |
| neither | 1574 | 25.0% |

> No set's 20-point lead is worth more than another's -- the lift is flat across sets 1 through 4. And being first to 20 carries almost nothing beyond the set result itself: a team that won the set from behind at 20 wins the match at essentially the same rate as one that led at 20 and closed it out. First to 20 matters only because it usually means winning the set.


---

## 10. Why set 1 is now graded

Replaced **fbso_pct (first-ball side-out)**. stats.ncaa.org now denies every /teams/<id> path. The replacement feed carries point-summary play-by-play only, so first-ball side-out has no 2026 source.

Grade AUC against match result: 0.963 → **0.9665**. Hit rate 50.0% — Exactly 50% by construction -- one team wins set 1 in every match.

First-to-20 was rejected for the same slot: a team first to 20 in every set wins 99.3% of matches across D1. Too tautological to grade; kept as a context metric instead.

