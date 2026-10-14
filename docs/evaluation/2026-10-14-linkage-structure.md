# One placebo, one report, content-keyed role tables: behaviour preserved on real calls (2026-10-14)

Regime: branch `struct-linkage` (from 2e09a61), a scratch lake of junctions onto `pegasus_core_data` for the reads (role tables of SIH-RD and
SIM-DO 2022 linked in, runs and parameters copied), scratch catalog copy; PEGASUS_LAKE_DIR/CATALOG_DIR set so no write reaches the root (see the
incident below). Base = the same code at 2e09a61, run from a copy of `src/`. Scripts: `scratchpad/s_linkage/snap.py`, `ent.py`, `ctrl.py`. Decision:
ADR-0186.

| call (2022) | base | after | time, min of 3 base / after |
|---|---|---|---|
| `role_table` SIM-DO RR, SIH-RD AL (death admissions), SINASC-DN RR, SIM-DO 2021-22 RR+AC, SIH-RD BR (2 roles, 12.5 M rows) | 3,246 / 6,875 / 13,091 / 17,207 / 12,520,914 rows | equal tables (rows, columns, values) | 3.5/4.0, 0.2/0.2, 0.5/0.6, -, 3.4/4.3 s |
| deterministic `sih_deaths_to_sim` RR (right BR) and AL | 1,195 / 5,832 pairs | equal pairs; report equal | 7.0 / 7.7 s |
| deterministic `sim_infant_deaths_to_sinasc` RR | 136 pairs | equal; control reach 0.9919 to 1.0 | 1.8 / 1.6 s |
| deterministic `sinan_toxc_to_sim` BR, `sinan_toxg_to_sinasc` BR, `sinan_dengue_deaths_to_sim` BR | 25 / 0 / 0 pairs | equal; dengue control pairs 164 to 165 (chance 37.27 to 37.5%), control reach 0.9915 to 0.9972 | - |
| probabilistic `sih_deaths_to_sim` RR (national reference) and `sim_infant_deaths_to_sinasc` RR | 1,212 / 140 pairs | equal pairs, bits, thresholds; anchors' chance pairs 107 to 105 (the control now wraps) | 14.9 / 11.3 s |
| `build_entities` + `triangles` over the 2022 runs | 4,830,215 nodes, 2,405,604 persons, 8 specs | equal partition, kept/refused/by_spec, triangles | 17 s + 64 s / 19 s + 73 s (one run each) |
| `discover_links` SIH-RD to SIM-DO RR (133 keys), SINASC-DN to SIM-DO RR (158) | real counts | real counts equal; placebo counts differ by -3.5 to +4 (mutual) and up to +30 / +70 (right meets); top 5 keys in the same order, top 20 the same set | 5.9 / 4.8 s |

Times are wall seconds on a machine shared with other jobs; the spread between repetitions (3.5 to 9.2 s for the first call) is larger than any
difference between base and after.

**What changed in a report, and why.** Only where the placebo now reaches the end of the partner's range: the records whose moved date used to leave it
(dengue's last week of December, the infant deaths' last days) now wrap to the start of the range and meet it. Pairs, verdicts and thresholds did not move in any case measured.

**The displacement** (`ctrl.py`, control pairs at 7 / 28 / 182 days, deterministic passes, 2022): SIH deaths RR pass 2: 13 / 9 / 16; SIH deaths AL
pass 1: 4 / 3 / 0, pass 2: 81 / 84 / 72, pass 3: 4 / 5 / 2; infant deaths RR main pass: 1 / 4 / 0; dengue BR: 165 / 199 / 174; toxoplasmosis (TOXC) BR
pass 1: 2 / 1 / 2. Many pairs: the three agree within Poisson noise. Strong passes: the longer move counts fewer, so a week is the more
conservative control for an equality join; counts of 0 to 5 do not settle it.

**Lines.** Code lines (no blanks, comments or docstrings) of the nine files touched (`linkage/engine`, `probabilistic`, `roles`, `store`, `entities`,
`discover`, `identity`, the new `placebo`, and `geography`): 2,726 before, 2,721 after; `placebo.py` is 69 of them. The gain is single definitions
(one placebo, one result class and verdict call, one stacking of role-table parts, one numbering of the link graph, one pack path), not fewer lines.

**Incident.** The first run of the "after" code on the real data passed `root="C:/Users/Galaxy/pegasus_core_data"` to `link()`, which overrides the
environment's lake and catalog placements (an explicit root decides them). Its role-table reads went to the real root and, the role-table key having
changed, `_national_year` built the 2022 nation of SIH-RD and SIM-DO, SIM-DO 2023, SINAN-TOXC and TOXG 2022 and SINASC-DN 2022-2023 into
`lake/roles/` and removed the other keys of those years (a rebuild of a cached table is byte-identical: sha256 equal for SIH-RD and SIM-DO 2022).
Nothing else in the lake changed after 18:10 (`links` and the other directories were listed); the catalog was not opened for writing by this
code (a lake-backed query does not call `ensure_current`), but its file time at 18:19 cannot be attributed. The old names of the four tables that
the main checkout's code still looks for are in the handoff; the three others were stale before and are rebuilt on use. From then on every run set
`PEGASUS_LAKE_DIR` to a scratch lake (junctions to the real data directories, `roles` and `links` its own) and passed no `root=`.
