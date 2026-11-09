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
| 1 CNES | mirror pipeline removed | the 43 cube plans | byte-identical; the fields themselves in the national rerun |
| stage 4 | BR-DWGD's six annual fields as `climate:` cube views | the stored copies | 356,032 rows each, value, status, months and release equal |

**Found on the way.**
- **Duplicate SIDRA facts.** Read raw, SIDRA's fact store holds table 5938 twice (244,932 rows, 122,466 facts) and table 202
  in part (116,164 for 70,515). The cube and the old dict readers collapse them (OQ 95).
- **ANS was never landed.** `sus_dependent._unplaced` reads `lake/ANS/…`, which did not exist, so the model could not be
  rebuilt. The source is now landing (2 GB of December files).
- **Placebo reach (OQ 94).** On RR 2022 with exact birth dates, 10,442 births have 11,528 admission candidates, none a
  continuation AIH. Several true admissions per birth cannot explain the delivery link's missing half of the coincidences.
