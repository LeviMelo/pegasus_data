# 2026-11-21: the architecture review, each change against what it replaced

**Regime.** Branch `read-pipeline` from master 97f9b6d, merged to master on completion; the data home
`C:\Users\Galaxy\pegasus_core_data` for the lake reads, a fresh home per live run; Windows 11, the `pegasus` env.
Decisions: ADR-0222 to ADR-0225.

## What was measured, and why it is the thing that matters

A refactor of the read path can change a label, a filter or a refusal without failing anything. So the unit is the
result a caller gets: the table, column by column, and the report.

| change | scenario or script | what was counted | result |
|---|---|---|---|
| one read request, one finishing stage (ADR-0222) | `scripts/read_equivalence.py record` on 97f9b6d and after, `compare` | 30 real reads: 16 of the lake (SIH-RD, SIM-DO, SINASC-DN, SINAN-DENG; rows, conditions, provenance, a dimension, three years), 10 of published files (SIH-RD, CNES-ST, SIA-PA with an enrichment, SIH-SP through the AIH, SINAN-TUBE, a lake and fetch hybrid), 4 refusals; each table as a digest per column (type, nulls, content), each report whole | 29 equal; 1 deliberate: `fetch(columns=)` no longer returns the derived `MUNIC_RES_municipio` it was not asked for, as `load` already did |
| label fallback warnings | the same 30 reads, in one process and one by one | warnings naming a month the read did not ask | 33 before (a 2009 fetch said "no codelist window covers 202301" when a 2023 read came first in the process), 0 after; every warning about a month read is kept; tables equal |
| declared shapes (ADR-0223) | `scripts/validate_curation.py --schema`; five typos planted in a copy | files passing; typos refused | 338 of 338 pass; 5 of 5 refused by name; twenty `intake.yml` descriptions that YAML had cut at a comma found and quoted |
| kept artefacts (ADR-0224) | `cube("records:SIH-RD/hospitalisation", place="uf", periods=[2023], geography="AC")` before and after; a build and a write made to fail | table equality, the second call, files left | equal (134 rows); hit in 0.09 s; one file, no temp; a failure leaves the previous version only |
| layers (ADR-0225) | `scripts/layers.py` | internal imports against the declared order | 2,058 internal imports: 0 module-level upward; 34 function-level upward in 20 module pairs (41 in 23 before `intake.yml`'s declarations moved to the meaning layer); function-level imports 1,167 to 979 after 152 were hoisted, start-up unchanged (import of `query` 1.29 s, of `cube` 0.50 s, `--help` 1.9 s, best of four, before and after) |
| studies/ | every `build:` of `products.yml` resolved; `model-build --help`; the modules imported | functions found | all resolve |
| long functions | `scripts/codehealth.py`; the read reads above after each split | functions over 200 lines | 16 to 3 (`labelpack.build_label_pack`, `Builder._materialise_partition`, `Builder.build`: verified only by builds of hours, left). Each split compared on outputs: the 30 reads after each read-path split; 26 cube calls (25 identical, 1 equal but for row order, which the unchanged code also varies between runs), 24 `aggregate` calls with their reports, 7 capability documents, 15 routes and 26 HTTP responses byte for byte, 12 `describe` calls, 2 workbooks cell by cell, 2 compendia table by table; the builder's and the reader's file selection on six requests (SIH-RD 2016's 324 duplicate editions dropped, SIA-PA's parts, SIM-DO's national file read once), identical |
| types | `mypy src/pegasus_data` | errors | 256 in 54 files to 0, blocking in CI. Three were defects (a roles pattern matched against `None`; `extract --years ""` a TypeError, now a refusal); one severe: `population_account.vital_events` subscripted an imported function and raised on every call since 5fbfe1d (2026-11-09), so the population account could not be built. Fixed: deaths of 2022 1,544,266 (the SIM-DO total STATUS records), births 2,561,922 with 64 in no municipality, none before 1994 |
| live use | `scripts/live.py --run review-a` (14 scenarios, fresh home, the real server) and `--run review-final` on the final commit | rows and labelled columns against the last run of each scenario (2026-09-30 to 2026-11-08) | 14 of 14 pass in both runs, the second on 71db42d (after it only a CLI refusal and documents changed). Rows equal the last run of each scenario (SIH-RD 14,340; SIM-DO 23,122; SINASC 45,742; CNES-ST 3,996; SIA-PA 95,414; SINAN dengue 1,405,095; tuberculosis 103,382; SIH 2016 4,081 from the newest edition); labelled columns equal or more (CNES-ST 120 to 128, SIA-PA 43 to 45, tuberculosis 57 to 59: curation since October); SIH-SP's sex and age through the AIH equal on 46,933 rows |

## Read

- The read path was two pipelines with one renderer; it is one request, two file-opening sources and one finishing
  stage, and the comparison that proves it is now a script (RUNBOOK).
- The import graph was not tangled: placed module by module, one module-level import went upward. The order was real
  and unwritten; it is written and checked.
- The schema check found a defect no test or run had: descriptions silently truncated by YAML.
- Not done, with reasons: modules were not moved into a folder per layer (PegaSUS and 221 records name them);
  `read_events`/`count_events` stay in `semantics/event_types.py` (PegaSUS imports them there); the public surface
  (121 names) is unchanged for the same reason; the dated comments in code stay (they are the reasons the code is as
  it is, and the project's convention).
