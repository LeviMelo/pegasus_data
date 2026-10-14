# 2026-10-14: the linkage placebo, the verdict rule and the entity merge, measured

Regime: branch fix-linkage-population (commits b52e7a8, c6d01ca), role tables cached in `pegasus_core_data/lake/roles` and
stored reports in `lake/links`, read only; script outputs under the fixer's scratchpad (`linkage/try_placebo.py`,
`try_det.py`, `restate.py`, `try_entities.py`). What was counted and why: the placebo must find the coincidences the real
blocks create, or the false-match rate is a lower bound of unknown size (ADR-0167).

- **Placebo reach, before.** Stored reports, control candidates over (candidates minus left records), positive-scoring
  counts: sinasc_births_to_delivery_admission 0.06-0.08 (13 of 13 years), sih_neonatal 0.02-0.03 (13 of 13),
  sih_deaths_to_sim 0.39-0.47 (16 of 16); the others 0.60-1.0. The review's direct count: 2022 neonatal admissions found a
  partner-side birth on the +400 d date for 3.1% of 389,471 (+7 d 99.8%).
- **Placebo reach, after** (rotation by 182 d inside the partner's period; RR 2022 neonatal against the national SINASC
  2021-2022): block birth date + sex + residence 27,114 control against at least 27,088 expected coincidences, block birth
  date + hospital 88,949 against 89,560. On that slice no threshold meets 1% (top real score 24.0 = top control score) without
  the inherited delivery AIH: a faithful placebo says the weak model cannot clear a small slice.
- **Verdicts re-judged on the stored reports** (circular validations excluded, 30 pairs minimum): 35 of 186 change
  (neonatal 13 viable to caution, maternal deaths 3 viable to caution, dengue deaths 4 viable to not viable and 6 viable to
  caution, TOXC to SIM 2021 caution to not viable); the per-block reach test exists only for new runs.
- **Entity merge** (2022, 2,432,171 stored edges): 4.1 s against 60.7 s for the Python union-find, identical persons
  (2,409,479), kept edges (2,428,554), 96 refusals and per-spec counts; `triangles` 45 s.
- **Role table read** (RR 2022 SIH-RD from the review: 0.10 s and 30 MiB for the state against 2 s and 3.5 GiB whole);
  the DuckDB path was exercised on a synthetic lake for projection, state, side filter and the key (a new partition file of the
  year changes it, another year's does not). The fingerprint makes every stored run stale until re-run.
