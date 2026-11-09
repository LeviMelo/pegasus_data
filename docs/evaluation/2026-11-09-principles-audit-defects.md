# The principles audit's defects: each change against the outputs it replaced

Regime: `master` from 9958a80 to c392890, 2026-11-09, data home `C:\Users\Galaxy\pegasus_core_data` (read; the
collected vital-event files were rewritten). Each change was proved by snapshotting real outputs (pickled function results
on real data), switching, and comparing; the scripts and pickles are in the session scratchpad. Defects 6, 7, 8 and 10
were done by agents in worktrees and merged after their own before/after checks (their commits say what).

**Counted, and why it matters.** A defect is closed by replacing a special case with the general rule. The risk is a
changed number, so each change is judged by whether every output it touches is equal, value for value, on real records.

| defect | change | compared on | result |
|---|---|---|---|
| 4 ages (ADR-0218) | five forms, unit tables as data | SIM-DO AC 2022, SIH-RD AC 2022-01, SINAN-DENG 2022 (1,405,095), CIH-CR, CIHA, SRAG 2022 (566,133) | every value equal, nulls included |
| 2 one column (ADR-0219) | linkage reads `compare:` from roles files | `load_roles()` | 10 datasets, every `Role` equal; SIASUS-PS record `care` (was `care_episode`) |
| 2 | intake `role:` → `description:` (477) | served descriptions | 1,080 before and after |
| 3 population account | inputs declared, sex from its label | the 48 collected files; `load_events` (unit, entity), `national_events`, `events_uf`, `mortality_rates` | equal; sex codes: 1→M, 2→F, SINASC 2014 M/F, 0/9/I unknown |
| 3 lake paths | SIDRA as cubes, censuses via `load_population` | `lag_series`, `static_covariates`, `member_inputs`, `census_old`, `census_uf`, `load_contagem`, `member_totals` | equal arrays |
| 9 recipes | 54 SINAN recipes → one template | all 60 `AggregateSpec`s | every field equal; 19 descriptions name the agravo instead of its code |
| 1 CNES | mirror pipeline removed | the 43 cube plans; the fields nationally (frozen checkout 90717dd) | plans byte-identical; all 43 fields equal every year |
| all views | 91 cube-served fields against their stored copies, national, year by year | the copies | all equal (SNGPC's 56 M-row sales included); the copies removed (843 MiB) |
| stage 4 | BR-DWGD's six annual fields as `climate:` cube views | the stored copies | 356,032 rows each, value, status, months and release equal |
| stage 5 | aggregate recipes built from records cubes | the old build's cells, AC 2022 (SINAN Zika BR 2022) | SIH 20,730, SINASC 11,707, CNES-ST 3,241 cells equal; SIM 13 and Zika 56 records no municipality places were cells (state "ignored" codes), now unplaced; Brasília's region codes place in Brasília |
| cubes | sums read by the one number reader, null where no part holds a number | CNES hours (2015, 2020), SISAGUA sums (2022) | equal |
| registers | S2iD landed, `disasters` a view of its records | the copy | 76,190 rows equal |
| margins | INEP landed, `inep_enrolments` one cube per column | the copy | 334,200 cells equal; 2023 total 47,304,632 |
| time roles | a time role takes the intake's declared period kind (INEP's `NU_ANO_CENSO` is a year, not a date) | INEP | the cube had read no period |
| state places | SIES read at state level (`code_system: uf`) | the copies | 91,549 and 46,365 rows equal |
| place roles | a role's place level from its codelist or the intake's declaration, never assumed a municipality | the bindings of all 187 roles files | 3 changed: SIES's secretariat and SINAN's `notification.state` are states (were bound as municipalities); PNI's facility municipality declared `MUNICBR` |
| cubes | a row count that keeps the unplaced in the manifest | SIM-DO AC 2022 | 4,159 records: 4,146 placed, 13 unplaced (the manifest had said 0) |

**Found on the way.**
- **Duplicate SIDRA facts, by design.** Read raw, SIDRA's fact store holds table 5938 twice (244,932 rows, 122,466 facts)
  and table 202 in part (116,164 for 70,515). It is written one part per request, and requests overlap (a field wants the
  Total cells, a census series the cells below them); `sidra.store.load_facts` keeps each observation's latest copy. Only
  readers of the parts' paths double-counted, and the study modules that did are moved onto `cube()`.
- **ANS was never landed.** `sus_dependent._unplaced` reads `lake/ANS/…`, which did not exist, so the model could not be
  rebuilt. The source is now landing (2 GB of December files).
- **Placebo reach (OQ 97, resolved).** The delivery link's placebo turned each date half a year round the partner's
  whole range; national SIH 2022 holds admissions from 2008 (11.7 of 12.5 million in 2022), so births of the second half
  of 2022 landed in 2008, where nothing is, and the block's placebo held 25,234 candidates against at least 51,402
  coincidences. Several true admissions per birth were measured and ruled out first (RR 2022, exact birth dates: 11,528
  candidates for 10,442 births, no continuation AIH). Rotated inside the range both sides hold (`placebo.shared_range`),
  it holds 53,519, and the link is viable on RR 2022 (probabilistic 8,392 pairs at 0.77%, deterministic 8,865 at 1.9%).
- **The linkage scenario passes** (`scripts/live.py linkage`, fresh home, 2026-11-09, `data/probes/live/20261109-092800`):
  all six runs viable but SIH deaths → SIM deterministic, `use with caution` by its no-hospital pass (76 pairs, 13 in
  the control, 17.11%); the probabilistic run of the same link is viable (1,208 pairs, 0.41%).
