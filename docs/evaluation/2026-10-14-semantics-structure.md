# The semantics structure: one epoch, typed places, one window rule (2026-10-14)

Regime: branch `struct-semantics` (from 2e09a61), read-only on `pegasus_core_data` (a copy of its 273 MB catalog under the
scratchpad, the lake and registries through junctions) and, for the reference warehouse, on the maintainer home's lake
(10,381 tables). The base commit's source was run from a `git archive` beside the new tree, same calls, same data.
Decision: ADR-0187. Throwaway probes; the figures are what was run.

| what | before | after |
|---|---|---|
| 122 calls (labelled `query` SIM-DO 2022 and 2005 AC, SIH-RD 2022-01 AC, SINAN-LEPT 2019, SINASC-DN 2020 AC, SIA-PA 2022-01 AC; `levels`, `load_reference`; `count_events` SIM-DO, SIH-RD, SINAN-CHIK, SINAN-SDTA's grid, SIA-PA; `field_overlap`; `care_flows` SIH-RD, SIM-DO, SINAN-CHIK; `describe`, `roles`, `event_types`, `flows()`, grids, relations, the ontology, captures, treatments, 84 vintage reads of 7 codelists in the pack and the warehouse) | | tables equal (normalised), JSON equal; the three `roles` equal but for the new `place_of` key |
| 5,736 warehouse reads (1,298 tables, up to 2 systems, 4 vintages: none, 1995, 2010, 2024) | | rows identical in all; 64 differ in one thing: a read with no period of a table with no open-ended window answers its newest window and now says so (`unscoped` → `current`), silently before |
| `Ontology.load()` / `declared_fields()`, warm | 1.7 ms (190 `stat`) / 1.8 ms (parse) | 6 µs each |
| `captures` (5 codes) / `treatments` (3 codes), first call of a process, median of 3 | 0.03 s / 0.04 s | 0.03 s / 0.01 s |
| first curated read of a process | | +83 ms once (the digest of 367 files, 9.8 MB); 6 µs a call after |
| SIM-DO 2022 BR `count_events` (cold process, 4 alternations) | 2.65 s median | 2.58 s |
| three processes, one fresh catalog, `ensure_current` together | | one loads, two find it current, each reads all 4,893 variable docs |
| PegaSUS `_records` (copied) against `read_events(consolidate=False, prepare=_rid)` | SINAN-CHIK 2015 52,338 rows with `_rid`; SIA-PA 2022-01 AC 55,963; SIH-RD 2022-01 AC 3,977; SIM-DO 2022 AC 4,159 | equal on every common column (5 cases) |

Place columns: 1,067 in 166 role files now state `place_of`: subject 438, event 510, record 119. By model: stratum 139 subject;
where 354 event; dimension 199 subject; link_only 27 subject and 8 event; excluded 10 record; mark 148 event, 109 record, 73 subject.
Shared with the earlier round: SOURCE_AUTHORITY already built the SQL ranking (388662a), the curation load is one transaction
with a double-checked digest (5b8cc50), `describe` and the ledger decide the labelling table with the renderer (ADR-0179).

Not done: the normaliser's own labelling path (`normalize/engine.py`, `most_granular_codelist`: hashed by `plan_fingerprint`, ADR-0173)
and `coverage_for_field` still use `most_granular_codelist` (OQ 79's residue).
