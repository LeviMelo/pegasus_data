# pegasus_data: where everyday calls spend their time (2026-10-11)

**Regime.** Branch `perf2`, data home `pegasus_core_data`, with a PegaSUS study running beside it, so single timings are
loaded. The battery times each call twice in a fresh process: the first time includes the process's setup, the
second is the steady state. Profiles are py-spy raw stacks. Drivers are in the session scratchpad
(`ctl/pgd_battery.py`, `explore_eq.py`).

| call | before (first / again) | cause | change | after |
|---|---|---|---|---|
| `explore` of a dataset | 4.44 / 1.56–1.93 s | every call read all 207,000 catalog files into Python and filtered there (the SQL 51 %, a list comprehension 20 %) | the system and role filters in the SQL; the systems suggested from a `DISTINCT` only when a name is unknown | 1.61 / 0.06 s for SIM-DO and TOXG, 0.41 s for SIA-PA; identical rows, levels and suggestions on seven targets |
| `pg.query`'s split by competence | 19 % of a query | a filter per month (`2026-10-11-query-split.md`) | one sort | 1.29 → 0.72 s |
| first query of a process | 12.6 s (labelled, SIM-DO SE) | the decoders' temp pruning stat'ed every entry of the temp directory (14,929) before reading its name; YAML built object by object in each process | the name first; a parsed curation or ontology file kept as a pickle per version (path, mtime, size) for every process | 3.6–3.8 s |
| `event_types` first call | 2.21 s | YAML (as above) and module imports | the YAML cache | 0.79 s |
| `concept_index` | 1.2–1.5 s | not profiled yet | — | — |

The cost that remains in a fresh process is module imports and the deep copies `read_yaml` hands its callers (12 % of
`event_types`).
