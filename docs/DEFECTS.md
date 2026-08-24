# Defect catalogue — 22 August 2026

> **Status: every defect below is FIXED**, each with a regression test.
> Measured on live DATASUS, not inferred. See the summary at the foot.

Two sources, and they complement each other rather than overlap:

- **REVIEW.md** — an external static review of `src/`. Thorough on control flow.
  It could not run anything: no `pyarrow`, no network, no test execution.
- **Runtime testing** — this session, against live DATASUS with a real catalog.
  Measures what static reading cannot, and catches defects in code written after
  the review's snapshot.

Every P0 below was **re-verified by reading the current source**, because several
commits post-date the review's snapshot and a finding could already be fixed.
File:line references are to the code as it stands now.

Each entry states what it was. Every one is now fixed — see Status at the foot.

---

## P0 — can silently return wrong or incomplete data

### P0-1 · A failed refresh falls back to the blob just judged stale
`acquire/fetcher.py:266-275` — **verified**

```python
self.fetch_many(wanted)          # return value discarded entirely
for p in wanted:
    digest = self.blobs.known_for(p)   # historical lookup, ignores this run
```

`known_for()` asks for the most recent previously successful fetch and checks
only that the file still exists on disk. It does not re-run freshness policy. So:
`_should_skip()` says stale → refresh fails → yesterday's blob is returned and
decoded as though acquisition succeeded. The code is **most willing to use stale
data exactly when its own logic said not to trust it**.

### P0-2 · Labels are not vintage-scoped, despite the docs
`api.py:653-659` — **verified**

```python
year_hint = min(years) if years else None
...
family_id=families[0]["family_id"] if len(families) == 1 else None,
year=year_hint,
```

Two failures in three lines. `load(years=range(1995, 2025))` renders **every row
with the 1995 vintage**; `years=None` renders historical rows with today's
codelist. And whenever more than one family is combined, `family_id=None` throws
away family-specific bindings, so a heterogeneous result is rendered as one
semantic context. `fetch()` does the same with `min(want_years)`.

A plausible wrong label is worse than a missing one. This is the case the whole
project exists to prevent.

### P0-3 · `load(columns=)` silently drops whole schema generations
`api.py:625-646` — **verified**

```python
errors.append(MissingColumnError(missing[0], family["family_id"], elsewhere))
continue
...
if not tables:
    if errors:
        raise errors[0]
```

`errors` is only raised when **no** family produced a table. If a later
generation has the column, the earlier generations are dropped and nothing is
said. A 1995–2025 request for a column added in 2006 returns 2006 onward and
looks like a dataset that simply starts in 2006.

The docstring at `api.py:570` promises the opposite: "A requested column that
does not exist in the target generation **raises**".

### P0-4 · `load()` has no file-axis guard
`retrieve.py:189` vs `api.py` — **verified**

`_check_axes`/`FilterHasNoAxis` appear only in `retrieve.py`. `api.py` never
references them. So `load(uf="AC")` against a national dataset filters a Hive
partition that does not exist and returns a false empty — the precise failure
`fetch()` was written to prevent. `Builder` writes non-axes as `uf=NA`/`year=0`
and `Lake.read()` applies the predicate blindly.

### P0-5 · Two incompatible dataset resolvers
`api.py:294-317` vs `retrieve.py::_families()` — **verified**

`_resolve_family()` uses exact `series = ?` SQL. `retrieve._families()` resolves
through the ontology, with a comment explaining, with measurements, why exact
matching is wrong. `load()` and `describe()` use the SQL one; `fetch()` uses the
ontology one. `DuckLake.register_all()` groups by raw `(system, series)`.

Confirmed at runtime: `load("CNES", "ST")` raised
`KeyError: no family found for system='CNES' series='ST'` on a catalog holding 35
CNES families.

For a package whose central abstraction is "one logical dataset despite unstable
filenames", there must be exactly one resolver.

### P0-6 · Partition replacement destroys before it writes
`persist/lake.py:113-118` — **verified**

```python
if replace:
    self._clear_partition(...)   # unlinks parquet AND deletes catalog rows
directory.mkdir(parents=True, exist_ok=True)
pq.write_table(table, target, ...)
```

Disk full, interrupt, or an Arrow raise between those lines leaves the partition
gone. If the write succeeds but the catalog update fails, the file exists without
metadata — and `ds.dataset()` globs the directory, so analytical state and
catalog state diverge silently.

---

## P0/P1 found only at runtime — the review could not see these

### R-1 · The shipped label pack costs 1.3 GB of RAM
`labelpack.py::_index()` — **measured**

```
baseline python              18 MB
after import pegasus_data    42 MB
after loading label pack   1309 MB   (9.2s, 2,238 codelists, 2,418,300 runs)
```

`_index()` materialises 2.4M runs as Python tuples in a dict. That is the ~1.3 GB
floor under **every** labelled fetch, whatever the result size — a 15,810-row
CNES-ST fetch peaks at 1,408 MB. The parquet is 19.8 MB on disk; the Python
object graph is ~66× that.

Mine, written this session, after the review's snapshot. Fix: keep it as an Arrow
table and slice by codelist, rather than exploding it into Python objects.

### R-2 · The documentation layer never loads on a fresh install
`retrieve.py::_ensure_reference_tables()` — **measured**

`pipeline.curate()` does not exist — `Pipeline` has no such method. I wrapped the
call in `try/except` and turned the `AttributeError` into a warning nobody reads:

```
could not load the shipped curation: 'Pipeline' object has no attribute 'curate'
```

Result: on a fresh root `variable_docs` and `dataset_docs` are both **0**, so
`info()` returns a dataset with no `what_one_row_is` and `describe()` has nothing
to describe — even though the YAML ships in the wheel. The real entry point is
`semantics.curation.load_curation`.

Mine, this session. The `except` that hid it is its own lesson.

### R-3 · Four of ten public functions reject `root=`

| function | `root=` | `settings=` |
|---|---|---|
| `fetch` `explore` `info` `translate` `availability` `compendium` | yes | yes |
| **`describe` `search` `export` `load`** | **no** | **no** |

`search(path, query)` takes a *filesystem path* as its first argument — an
entirely different calling convention from every neighbour. A user who has been
passing `root=` everywhere hits `TypeError` on a quarter of the surface.

### R-4 · `export()` does not match its own documentation
README documents `export(system, series, *, format=...)` with an `out=` argument.
The real signature takes `path=`. `export(out=...)` raises `TypeError`.

### R-5 · A cold fetch of 12 files costs 282s and 85 MB
**measured** — this is REVIEW's HI-14, with numbers

```
fresh:  fetch CNES-ST AC 2023     282.3s   peak_rss 1408MB   disk +85.2MB
warm:   same query                  8.4s                     disk  +0.0MB
```

12 files, **0.7 MB downloaded**. The 85 MB is the catalog: 80,515 file rows, the
whole CNES tree. The 282s is crawl + inventory + a schema census over **271
strata across all 13 CNES datasets** to serve one.

Gratuitous twice over: the package already ships `tree.parquet` with all 207,251
paths, so it crawled what it was already carrying; and it censused 13 datasets to
answer about one.

Confirmed again with a second system on the same root: `fetch("SIM-DO")` on a
catalog already holding CNES took **207s** and set `discovered=True`.

### R-6 · `translate()` ignores the shipped label pack
```
TranslationImpossible: the catalog holds no codelists, so nothing can be
labelled. `pegasus-data unpack <bundle>` fills ...
```
Raised on a root where `fetch(labels=True)` labels 115 columns successfully.
`translate()` checks the catalog dictionary and never consults the pack, so it
tells the user to go and download something they already have.

### R-7 · An unknown dataset takes 18.3s to be refused
`fetch("CNES-ZZ")` → `DatasetUnknown` after 18.3s. The name is not in the
ontology and cannot become valid; this should be immediate.

---

## Measurements, for reference

```
explore()                          0.7s     130MB
explore('CNES')                    1.2s     167MB
info('CNES.ST')                    0.7s     153MB
availability('CNES-ST')            0.2s     149MB
compendium()                       0.8s    1087MB

fetch CNES-ST AC 2023 (cold)     282.3s    1408MB   +85.2MB disk
fetch CNES-ST AC 2023 (warm)       8.4s    1327MB
fetch CNES-ST AC+AL+AM 2023       42.8s    1475MB
fetch CNES-PF AC 2023             44.8s    1499MB   241,636 rows
fetch CNES-ST all UF 2023-01     179.1s    2411MB   387,216 rows
fetch labels=False                14.7s    1500MB
fetch columns=[3 of 212]           5.7s    1375MB
```

Two things stand out. Memory never drops below ~1.1 GB once the pack is loaded
(R-1). And `columns=[3]` at 5.7s against 14.7s for the full table shows the
projection helps but does not avoid the decode — REVIEW's HI-07.

---

## Not yet verified

The review's remaining P1/P2 findings are plausible and specific but I have not
personally confirmed them: HI-02 through HI-28 except HI-14, and all of ME-01
through ME-21. Several are strongly implied by what is confirmed here — HI-18
(whole-partition materialisation) is visible at `lake.py:111`, and HI-01
(warm fetch still opens FTP) is consistent with the 8.4s warm number.

They should be verified before being fixed, not assumed.


---

## Status

All six P0s and all seven runtime defects are fixed, on `main`, with the full
suite green (714 passing).

| id | was | now |
|---|---|---|
| P0-1 | a failed refresh served yesterday's blob | `ensure()` returns only what this run resolved; `allow_stale=` is explicit and recorded |
| P0-2 | one vintage and one binding for the whole result | rendered per `(family, year)`, row-level from the lake's own partition column |
| P0-3 | whole generations dropped in silence | raises, as its docstring already promised |
| P0-4 | `load(uf=)` on a national dataset returned a false empty | one axis policy, `retrieve.axis_refusal()`, used by both paths |
| P0-5 | two dataset resolvers that disagreed | one, through the ontology |
| P0-6 | the partition was deleted before its replacement existed | staged, validated, then swapped |
| R-1 | label pack cost 1,309 MB and 9.2 s | 132 MB, sub-second, pushed into the Parquet scan |
| R-2 | curation never loaded; `info()` had nothing | 4,298 variable docs and 132 dataset docs on first use |
| R-3 | four of ten functions rejected `root=` | all ten accept `root=` and `settings=` |
| R-5 | cold fetch 282 s / 1,408 MB for 12 files | **30 s / 287 MB** |
| R-6 | `translate()` refused, citing a bundle you already have | uses the shipped pack |
| R-7 | an unknown dataset took 18.3 s to be refused | **0.8 s**, with suggestions |

Two things the fixes turned up that were worth more than the defects:

**A curated refusal was never enforced.** `sihsus/_shared.yml` marks SEXO and
COD_IDADE "DELIBERATELY UNBOUND" — SIH's own table maps `1→Masculino`,
`2→Feminino` *and* `3→Feminino`. The refusal was prose, so once bindings were
seeded the renderer labelled from exactly the contradictory table. It is now
`code_system: none`, which the renderer honours.

**Labelled counts went down, and that is the fix working.** CNES-ST reports 83
labelled rather than 115 because the curated decisions finally apply.

What the external review raised beyond these — HI-02 through HI-28 except
HI-14, and ME-01 through ME-21 — is still open and still unverified. It should
be verified before being fixed, not assumed.

---

## REVIEW.md closure

Every entry in `REVIEW.md` — CR-01..06, HI-01..28, ME-01..21, and the
"Additional design inconsistencies" section — is addressed. The commit log
carries each `HI-xx`/`ME-xx` identifier in its message; `CR-01..06` and `HI-14`
landed earlier under this file's own `P0-*`/`R-*` labels, and
`tests/test_review_closure.py` asserts their guarantees so the closure is
checked on every run rather than taken on trust.

Two entries were closed by *disagreeing* with the review, with the evidence
recorded rather than the conclusion asserted:

* **HI-23** — the review argued the DBF reader's `min(declared, available)`
  silently truncates valid trailing records when a header is stale LOW. Measured
  across 132 real DBF payloads: 116 headers agree, **16 declare more records
  than the file holds, none declares fewer**. The header errs high, so `min()`
  is what stops a read running past the end and manufacturing rows out of
  whatever follows. Reverted to `min()`, with the measurement in the code.
* **ME-17** — the archive that was reviewed carried `__pycache__` and
  `.egg-info` and lacked packaging config. The canonical repo has none of those
  problems. Running the configured checks, however, surfaced real defects
  (including `load_reference()` raising `NameError` for every caller who did not
  pass a catalog), and nothing reproduced them. CI now does.

State at closure: **837 tests passing**, ruff clean across `src/`, `tests/` and
`scripts/`, mypy at 98 findings (from 197) recorded as a ratchet in
`CONTRIBUTING.md`.

---

## Second external review closure — 2026-08-23

`REVIEW.md` found a newer set of release blockers and durability/semantic
hazards. They were reproduced in the project environment and closed as follows:

| finding | resolution |
|---|---|
| projected fetch lost source context | hidden provenance survives projection until per-source rendering |
| logical source identities disagreed | one canonical `path!member` identity on local and isolated paths |
| lazy null-fill read whole schemas | each batch is projected and conformed to the exact requested schema |
| shipped label pack had no windows | rebuilt from the recovered full catalog: 3,654,320 versioned runs |
| isolated workers survived bad replies | any failed/incomplete protocol reply retires the worker process |
| parent IPC accumulated every batch | framed Arrow batches spool to disk and remain re-iterable |
| archive/DuckDB selection was late | member and column projection now reaches the physical reader |
| duplicate concurrent physical decode | digest-keyed `Future` provides single-flight decoding |
| profile/build used divergent decoders | fetch, profile, build and derived ingestion share `decode.service` |
| deterministic staging collided | every file/tree transaction has a unique target-local staging name |
| partition replacement exposed stale siblings | the complete partition directory is staged and swapped as one unit |
| schema constraints compared one way | primary, UNIQUE and foreign-key sets are compared symmetrically |
| weak municipality invalidation | the plan hashes the full municipality mapping, not its row count |
| direct population/DEMAS writes | both publish complete staged trees; failed refreshes do not publish partial output |
| ZIP-only resource quotas | ZIP, LHA, TAR, gzip, RAR and 7z share member/size/ratio ceilings |
| worker diagnostics looked like missing data | diagnostics and concrete failed requested paths are separate ledgers |
| cross-system labels were optimistic | borrowing is off by default and requires `allow_borrowed_labels=True` |
| lake lost month vintage | internal `_competencia` survives build and drives month-exact rendering |
| ranking cap chose truth | uncurated candidate sets above the cap are refused, never truncated into a choice |

This closes software defects, not the substantive uncertainty deliberately kept
in the semantic ledger. Inferred descriptions, genuinely sourceless fields and
Ministry-only denominator questions remain evidence work rather than bugs.

---

## Next-architecture closure — 2026-08-23

The architectural brief identified design gaps rather than isolated runtime
exceptions. They are closed by these enforced invariants:

| area | defect prevented | enforced resolution |
|---|---|---|
| storage | treating a 15 GB maintainer catalog as a runtime requirement | exact `dbstat` report plus versioned, budgeted compiled resources |
| representations | decoding every mirror/expansion or dropping archive members | one shared logical-publication selector; conflicts are recorded and retained |
| ontology | two datasets silently claiming one alias | duplicate system/dataset aliases raise during ontology construction |
| relations | roll-ups and attributes emitted as identity labels | typed semantic relations; only `label_of` is automatic |
| adjudication | candidate caps choosing meaning | stable evidence item, export/apply workflow, safe refusal |
| time | monthly intent silently widened to annual publication | source-resolution warning/adaptation or strict refusal; event-date filtering is out of scope |
| geography | national files producing false empty UF results | physical publication axis or refusal; record geography is never substituted |
| schema evolution | absent generations disappearing from a projection | union schema, structural nulls, report and Arrow metadata |
| crosswalk | identifier overwrite or accidental row multiplication | raw preservation, temporal windows, explicit statuses, opt-in explosion |
| resources | hidden large downloads for optional enrichment | provider estimates and preflight; explicit bounded build lifecycle |

The formal regression coverage lives in `test_query_api.py`,
`test_crosswalk.py`, `test_representation_selection.py`,
`test_semantic_relations.py` and `test_next_resources.py`.

---

## Follow-up architecture review closure — 2026-08-23

The second review of the architecture patch found completeness and semantic
integration defects that the first closure tests did not exercise.

| defect | resolution | regression evidence |
|---|---|---|
| one lake partition selected lake for every requested year | exact logical-publication coverage per year; non-overlapping hybrid plans | `test_partial_year_lake_coverage_routes_whole_year_to_fetch`, `test_complete_and_missing_years_form_a_hybrid_without_overlap` |
| fact fields were treated as retrieval axes | analytical switches removed; source capability resource contains publication coordinates only | `test_legacy_analytical_axes_are_not_in_the_public_contract` |
| one current dimension table applied to longitudinal rows | packed relation selected per row competence/year | `test_dimension_uses_each_rows_semantic_vintage` |
| representation conflicts could duplicate facts | conflicts and same-format collisions refuse analytical selection | `test_representation_selection.py` |
| crosswalk/registry packs expanded wholesale into Python | predicate-pushed identifier/validity slices | `test_columnar_slice_filters_identifiers_and_validity_before_materialising` |
| high-level labels used a denylist | only effective `label_of` relations are admitted; unknowns open adjudication | query and semantic-relation suites |
| applied relations were invisible to dimensions/new connections | one committed adjudication transaction and unified resolver | `test_adjudicated_dimension_is_effective_immediately` |
| mixed annual/monthly resolution collapsed to one boolean | per-year resolution retained in `RetrievalPlan` | query planner suite |
| annual publication was filtered by event date | enclosing annual source is returned with warning; no fact-row date predicate exists | `test_annual_publication_adapts_without_filtering_event_dates` |
| optional-resource coverage used one intersecting row/min-max | exact requested years and source identities; explicit covered-year metadata | `test_next_resources.py` |
| overlap audit grouped only identical windows | interval-overlap metrics in both directions | `test_crosswalk_audit.py` |

The review's `MUNIC_MOV` and numeric-UF examples were symptoms of the undeclared
source/analysis boundary, not additional column aliases to add to another guess
list. Their meanings remain documented, but the high-level planner does not
filter either field.

---

## Source-contract replacement review closure — 2026-08-23

The continuously replaced review explicitly narrowed Pegasus-Data to source
access and additive semantic serving. The prior row-axis implementation is
superseded by these verified closures:

| defect | resolution | regression evidence |
|---|---|---|
| `period`/`geography` filtered ordinary fact fields | removed `time_by`, `geography_by`, `unresolved_time` and all event/residence row predicates | `test_annual_publication_adapts_without_filtering_event_dates`, `test_municipality_is_not_fabricated_from_a_fact_column` |
| `_competencia` could be overwritten by event dates | query path treats it only as immutable publication provenance | source-contract query tests |
| archive path falsely proved every member complete | lake provenance records `path!member`; completeness key includes family/logical/member | `test_archive_member_is_part_of_local_completeness` |
| representation decisions were family-local | fetch/build reconcile globally; singleton calls honor open conflicts | `test_cross_family_schema_contradiction_is_detected_globally`, `test_open_conflict_also_refuses_a_singleton_candidate` |
| unknown semantic vintage used current mapping | temporal derivation is null unless explicitly time-invariant | `test_unknown_required_dimension_vintage_is_null` |
| relation validity/specificity was non-temporal | `valid_from`/`valid_to` plus deterministic local/curated/legacy and dataset/system precedence | semantic relation adversarial tests |
| CNES-name row windows were mistaken for source completeness | compiler requires explicit covered years from verified complete source snapshots | `test_name_build_refuses_to_infer_coverage_from_record_windows` |
| resource freshness was required to equal the wheel snapshot | schema ABI, manifest identity and checksum remain strict while compatible newer content is accepted | `test_optional_resource_accepts_independently_newer_content_version` |
| CNES lookup inherited fact UF | registry scan is driven by CNES identifiers and validity years only | `test_cnes_registry_enrichment_does_not_inherit_fact_geography` |
| hand-maintained capability duplication | `source_publication` curation compiles the compact runtime JSON; semantic axes remain descriptive | `test_query_capabilities_are_compiled_from_curation` |
| omitted period could launch historical acquisition | executor refuses non-local unbounded work without `allow_unbounded=True` | `test_unbounded_source_acquisition_requires_explicit_opt_in` |
| catalog key overwrote historical adjudications in one semantic slot | stable temporal `relation_id`, local/curated authority and lossless migration retain adjacent assertions; overlaps fail | temporal persistence and migration tests |
| annual vintage collapsed to unknown or direct enrichment chose December | source-vintage intervals require one relation/mapping across the full year | annual dimension and year-only crosswalk tests |
| mixed annual/monthly execution retained arbitrary null competence | per-source resolution distinguishes annual enclosure from broken monthly provenance; month pushdown stays per year | mixed-resolution query tests |
| duplicate source capability declarations silently used the last file | capability compilation fails on duplicate dataset declarations | `test_capability_compiler_rejects_duplicate_source_declarations` |

Planning remains metadata-only; requested-slice decoding and explicit bounded
resource builds are the first operations allowed to inspect relevant rows.
