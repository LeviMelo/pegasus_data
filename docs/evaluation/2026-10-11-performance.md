# pegasus_data: where everyday calls spend their time (2026-10-11)

**Regime.** Branch `perf2`, data home `pegasus_core_data`, with a PegaSUS study running beside it, so single timings are
loaded. The battery times each call twice in a fresh process: the first time includes the process's setup, the
second is the steady state. Profiles are py-spy raw stacks. Drivers are in the session scratchpad
(`ctl/pgd_battery.py`, `explore_eq.py`).

| call | before (first / again) | cause | change | after |
|---|---|---|---|---|
| `explore` of a dataset | 4.44 / 1.56–1.93 s | every call read all 207,000 catalog files into Python and filtered there (the SQL 51 %, a list comprehension 20 %) | the system and role filters in the SQL; the systems suggested from a `DISTINCT` only when a name is unknown | 1.61 / 0.06 s for SIM-DO and TOXG, 0.41 s for SIA-PA; identical rows, levels and suggestions on seven targets |
| `pg.query`'s split by competence | 19 % of a query | a filter per month (`2026-10-11-query-split.md`); then the sort's take copied the whole table (a third of a warm query) | a competence's rows are runs in the lake (a file is a month; a national read, 27 states, a few hundred runs): each value's runs concatenated as zero-copy slices, no sort | a warm SIH year 3.4–4.8 → 1.9–2.2 s, the same output hash |
| first query of a process | 12.6 s (labelled, SIM-DO SE) | the decoders' temp pruning stat'ed every entry of the temp directory (14,929) before reading its name; YAML built object by object in each process | the name first; a parsed curation or ontology file kept as a pickle per version (path, mtime, size) for every process | 3.6–3.8 s |
| `event_types` first call | 2.21 s | YAML (as above) and module imports | the YAML cache | 0.79 s |
| A labelled query (SINASC SP 2019, 583,191 births, warm) | 7.2 s | every provenance column was weighed against the codelists (`_row`'s 583,191 distinct values); the anomaly list rendered row by row (1,658 distinct cells) | `_`-columns pass through unweighed; each distinct cell rendered once (nulls an entry of their own), the rows taking theirs | 2.0 s; the same output hash on SINASC SP and SIM SE; labels, codes and misses equal on all 2,849,146 national anomaly cells |
| CLI start (`--help`, `explore`, `events`, `roles`) | 1.4–1.8 s; importing the CLI 1.43 s | pandas, 0.6 s: pyarrow imports it at the first `pa.array` (two module constants in `normalize.geo`) and when `pyarrow.dataset` loads (module-level in the API, the lake and the reference layer) | the UF table built on first use; `pyarrow.dataset` a module imported on its first attribute read (`_lazy.LazyModule`) | importing the CLI 0.70 s; commands 1.0–1.3 s; every output hash unchanged |
| `concept_index` (warm) | 0.59–0.96 s | Python passes over SIGTAP's 82,000 compatibility pairs and the condition codes, and every ICD-10 and SIGTAP label folded again on each call | prefixes filtered in Arrow; the folded labels once per structure and process | 0.03–0.06 s; identical conditions, procedures and labels for toxoplasmosis, dengue and microcephaly |
| A role table (SIH-RD SP 2019, 2,606,482 admissions, 18 columns) | 79.4 s; its query 31–48 s labelled against 4–9 s as codes | every column labelled, while `_normalise` reads the labels of five (sex, places, facilities, label roles): the diagnoses and procedures were weighed against ICD-10 and SIGTAP for nothing | `render` passes through `query` to `load` and `fetch`; a column rendered `"code"` chooses no codelist; a role table asks codes of the columns no role reads labels of | 46.2 s; the table equal column by column |
| Lake build, one large partition (SIA AM SP 2025: 12 files, 16.4 M rows, 742 MB) | 343.6 s | Parquet writing 30 %, record keys 21 %, decompression 14 % (native); per 1.5 M rows the writer takes 5.2 s now, 6.2 s with 256K row groups (6 % smaller), 5.7 s through DuckDB; the keys 3.9 s in batches or in one query, identical | none: the per-row costs are real work. Left: decoding a large partition's files in parallel, which the builder's cross-file deduplication constrains | — |

The cost that remains in a fresh process is module imports and the deep copies `read_yaml` hands its callers (12 % of
`event_types`).

**Also changed.** A stored link run's report now carries its wall time (`seconds`). PegaSUS prices the runs a study
would compute by it. The decoder pool's size is a setting (`decode_workers`, `PEGASUS_DECODE_WORKERS`), by default
the machine's decode slots: unchanged on this machine (4). The pool size has not yet been measured on a per-state
year: SINASC 2019 is two national files and measured nothing, and the run on SIM-DO was stopped when free memory reached
0.1 GB beside the study. The national role tables are keyed on the code that renders them, so this branch's merge
rebuilds each one the next time a link needs it.

**A named row filter (later the same day).** `query(rows={column: prefixes})` and `load(rows=)` keep only the records
whose columns start with the codes, pushed into the lake's scan before anything is rendered. A year read from files is
filtered on arrival. Period and geography still never filter records; this is a filter the caller names. Checked on
SIH-RD 2016 with B58, P37.1 and O98.6: 2,205 records, identical to filtering after a full read of 11,527,712. Fixed on
the way: `Lake.read` let a state filter replace the caller's predicate.

**Persons of a cohort.** `build_entities(seeds=(dataset, role, ids))` merges only the link-graph components holding the
seeds, after the draw, so each edge keeps its draw from the whole set. On SINAN-TOXC 2022, 4,583 notifications, against
the 5 links among TOXC, SIH and SIM, the cohort's persons with an SIH record are identical: 652 undrawn, 617 and 626 in
draws 0 and 3. It takes 3.8–5.8 s against 12.6–13.4 s. `triangles(exclude=)` came the same day.

