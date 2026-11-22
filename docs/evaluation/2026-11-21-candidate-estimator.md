# The candidate estimator validated twice and simulated (2026-11-21)

**Regime.** Real home, commit after 779def2b; `papers/race_at_death/analysis/pair.py` (SIH-RD x SIM-DO 2016-2022,
`modelled_race.pair_candidate_counts`, `pair_truth` on the stored probabilistic runs of `sih_deaths_to_sim`, made under
an earlier text of the spec, digest 1cf164a9304d), `analysis/estimator.py` → `results/estimator.json`,
`analysis/simulate.py 200` → `results/simulation.json` (7 scenarios, about 75 min, detached; rerun 2026-11-22 after the audit). Paper 6, ADR-0233.

**Why these counts.** The estimator is known only through its agreement with linked records; a second pair with other
keys (day of death, hospital), another register (deaths, not births) and another density of chance tests it where the
first could not, and the simulation separates the estimator's error from the selection of who is found.

| check | result |
|---|---|
| refactor (`_candidates`) | `candidate_counts` 2023-2024 deaths of the 2022 cohort: 13,264 cells identical, largest difference 1e-13 |
| infants vs one-to-one link, <25,600 births/yr | mean abs. difference over 20 cells 0.005 (<400) to 0.020 (6,400-25,599); fails above (0.65) |
| admissions vs certificates, 3,766,913 units | linked 95.9%, findable (same key) 86.2%; vs findable 0.0010 mean, 0.003 max; vs all linked 0.006 |
| unfindable linked | certified White and White in hospital 0.50 against 0.63 for the findable |
| control within municipality or state | no difference beyond 0.002 (chance candidates 0.01-0.91 a unit) |
| simulation, bias (ideal, twins: real deaths) | within 0.004 below 6,400 births/yr, 0.009 at 6,400-25,599 |
| simulation, bias (sparse: a twelfth of the deaths) | 0.020 below 6,400, 0.134 above (Black row): small-row ratio bias |
| coverage (ideal, twins, sparse) | model 92-100%, counts 86-100%, chance (vs the found table) 90-100% |
| movers / unequal / selective / a2 | +0.013 vs all (-0.0003 vs found) / White:Brown ratio 0.66 → 0.72 / rows up to +0.038, coverage to 0% / up to 0.011 |

The municipality-cluster error was 1.7 to 9.9 times the counts' error for the admissions and about equal for infants:
it carries the variation of the classification between large cities, so it is not the national table's error.
