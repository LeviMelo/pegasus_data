# Engineering Review of `pegasus-data`

**Reviewed artifact:** `src(1).zip` supplied on 22 August 2026  
**Package metadata:** `pegasus-data` 0.1.0  
**Primary focus:** public Python API, especially `fetch()`, plus acquisition/cache correctness, decoding, normalization, rendering, Parquet persistence, DuckDB access, exports, concurrency, and testability.

## Executive assessment

This codebase has a strong conceptual architecture and an unusually good understanding of the epistemic hazards of DATASUS: content-addressed raw storage, explicit provenance, schema families, ontology-based dataset resolution, codelist provenance, validity windows, no-guessing policies, `FilterHasNoAxis`, Parquet partitioning, and a deliberate distinction between raw codes and rendered semantics are all sound ideas. The code also contains many comments that accurately identify the classes of failures that matter in health-data engineering.

The principal problem is that the **implementation of the hot paths has not yet caught up with those architectural intentions**. In several places, the source comments state the correct invariant and the runtime path violates it. This is most consequential in `fetch()`, `load()`, semantic rendering, cache validation, and persistence. There are also substantial avoidable I/O and memory costs that can make `fetch()` feel dramatically slower than the amount of requested data would suggest.

I would not treat the current public API as fully safe for longitudinal epidemiological analysis until the P0 correctness defects below are fixed. In particular, multi-year label rendering, missing-column behavior across schema generations, file-axis filtering in `load()`, stale-cache fallback after a failed refresh, and non-atomic lake replacement can produce results that are plausible rather than obviously broken. That is exactly the failure mode this project otherwise tries very hard to prevent.

The performance situation is more encouraging: most of the large costs are architectural plumbing problems with identifiable fixes. The package already has the right primitives for several of them—such as a content-addressed blob store, `BlobStore.materialize()`, Parquet, Arrow batches, and an explicit file-level parallelism principle—but those primitives are not consistently used in the hot path.

## Review scope and limitations

The supplied archive contains `src/`, `tests/`, and `scripts/`, but it is not a complete repository checkout: there is no `pyproject.toml`, `setup.cfg`, CI configuration, Git history, or top-level project documentation in the archive. It also contains generated `__pycache__` directories and `pegasus_data.egg-info`, so this appears to be a source/package snapshot rather than the canonical repository.

I inspected all major subsystems and traced the public retrieval paths end-to-end. The source tree contains **80 Python modules and approximately 28,552 lines of Python source**. The supplied tests contain **661 `test_*` functions**. `python -m compileall` succeeds for `src/pegasus_data`, `tests`, and `scripts`, so I found no syntax-level failures.

I could not execute the full test suite because the review environment does not have `pyarrow` installed and has no network access with which to install the package dependencies. With `PYTHONPATH=src`, pytest stops during collection with `ModuleNotFoundError: No module named 'pyarrow'`. Therefore, findings below are based on static control-flow and data-flow inspection rather than fabricated runtime timings. Findings labelled as correctness defects follow directly from the code path; performance magnitudes still need benchmarking on representative DATASUS files.

The project's own `scripts/codehealth.py` reports 80 modules and 904 functions. It identifies seven modules over its long-module threshold (`cli`, `compendium`, `docsgen`, `pipeline`, `semantics.dictionary`, `verify`, and `view`). The most complex public/hot-path functions include `view.render_table` (cyclomatic complexity 80, 292 lines, 13 parameters), `api.describe` (complexity 44, 213 lines), `build.Builder.build` (complexity 38), `api.load` (complexity 31, 16 parameters), `retrieve._read_families` (complexity 28), and `acquire.fetcher.Fetcher.fetch_many` (complexity 27). Those figures are consistent with the correctness drift documented below.

## Severity scale

**Critical (P0)** means the defect can silently return wrong/incomplete data, use stale data after deciding it is stale, or destroy previously valid derived data. These should block declaring the public API stable for research use.

**High (P1)** means the defect can cause major latency, memory/disk amplification, unreliable acquisition, resource leakage, or semantic behavior likely to become incorrect under common workloads.

**Medium (P2)** means the defect is an API inconsistency, maintainability problem, edge-case correctness risk, observability problem, or optimization that is material but not usually catastrophic.

## P0 — critical correctness and data-integrity findings

### CR-01 — A failed refresh can silently fall back to a blob already judged stale

**Location:** `src/pegasus_data/acquire/fetcher.py`, especially `_should_skip()`, `_fetch_one()`, and `ensure()`; `src/pegasus_data/acquire/cache.py::known_for()`; `src/pegasus_data/catalog/store.py::latest_blob_for()`.

This is the most serious `fetch()` cache defect I found.

`_should_skip(path)` is meant to decide whether an existing blob is safe to reuse. If its checks fail, `_fetch_one()` attempts a network refresh. That is correct. However, `ensure()` discards the `FetchStats` returned by `fetch_many()` and then does this for every requested path:

```python
self.fetch_many(wanted)
for p in wanted:
    digest = self.blobs.known_for(p)
    if digest:
        out[p] = digest
```

`BlobStore.known_for()` asks `Catalog.latest_blob_for(source_path)` for the most recent previously successful fetch and checks only whether that blob still exists on disk. It does **not** re-run the freshness policy.

Consequently, this sequence is possible:

1. Path `P` was downloaded yesterday as blob `X`.
2. Today's catalog listing shows evidence that `P` changed, so `_should_skip(P)` correctly returns `None`.
3. The refresh of `P` fails because DATASUS is unavailable or the transfer errors.
4. `ensure()` then calls `known_for(P)` and obtains yesterday's blob `X`.
5. `fetch()` decodes `X` as though acquisition succeeded.

The implementation therefore becomes most willing to use stale data exactly when its own freshness logic said the data should not be trusted.

**Required fix:** `ensure()` must be driven by the `FetchResult` objects from the current acquisition decision, not by an unconditional historical `known_for()` lookup afterward. A path should be returned only if the current run produced either (a) a verified cache hit under `_should_skip()` or (b) a successful new fetch. If refresh fails after a cache miss/stale determination, the stale digest may be exposed only under an explicit opt-in such as `allow_stale=True`, with provenance stating that it is stale.

**Required test:** catalog an old blob, change the current file metadata so `_should_skip()` rejects it, force the FTP refresh to fail, and assert that `ensure()` does not return the old digest.

### CR-02 — The claimed version-scoped renderer is not actually scoped per row, year, or schema generation

**Location:** `src/pegasus_data/api.py::load()` around the `year_hint`; `src/pegasus_data/retrieve.py::fetch()` around the `render_table()` call; `src/pegasus_data/view.py::render_table()`; `src/pegasus_data/persist/reference.py::read_reference_table()`.

The documentation repeatedly states that historical rows are labelled with the reference-table vintage applicable to those rows. The public APIs do not currently do that.

`load()` concatenates all selected family/generation tables and then computes:

```python
year_hint = min(years) if years else None
```

It passes that **single year** to `render_table()` for the entire result. `fetch()` does the same with `min(want_years)`. `render_table()` itself accepts only one `year` argument, and every `_lookup_map()` / contradiction lookup uses that one value.

Therefore:

```python
load("SIHSUS", "RD", years=range(1995, 2025))
```

can render every row with the 1995 reference vintage. Conversely, if `years=None`, `read_reference_table()` deliberately selects the current/latest vintage, so historical rows read without an explicit year filter can be rendered using today's codelist.

There is a second generation-scope problem in the same design. When more than one family is combined, both `fetch()` and `load()` call `render_table(..., family_id=None)`. `_bindings()` then sees only system-wide bindings (`family_id=''`) and does not use any family-specific binding that may encode a schema-generation-specific classification decision. A heterogeneous result is therefore rendered as one semantic context.

A third granularity problem is that reference selection accepts a `year` but not a row-level competência/date. `read_reference_table()` considers a validity window to overlap a calendar year if `lo <= year*100 + 12` and `year*100 <= hi`. If a code table changes during a year, a calendar-year hint is insufficient to choose a unique row-appropriate vintage.

This is not a cosmetic issue. Classification vintages and code meanings are exactly the cases in which a plausible wrong label is more dangerous than an obvious missing label.

**Required fix:** render before heterogeneous partitions are concatenated, or partition the Arrow table by the semantic keys required for rendering—at minimum `(family/schema generation, year or competência)`—and render each partition with the appropriate bindings and validity window before recombining. Ideally the renderer should receive a row-level temporal field or a precomputed vintage discriminator rather than a scalar `year` hint.

**Required tests:** create two codelist vintages where the same code has different labels, combine rows from both years, and assert that each row gets its own vintage. Repeat with `years=None`. Add a two-family test where the correct binding is family-specific.

### CR-03 — `load(columns=...)` silently removes whole schema generations when a requested field is absent

**Location:** `src/pegasus_data/api.py::load()`, approximately the family loop around lines 602–649 in the supplied source.

The `load()` docstring explicitly says that a requested column missing from the target generation raises `MissingColumnError`. The implementation does something more dangerous when the request spans multiple generations.

For each family, it checks whether every requested column exists. If a field is absent, it appends a `MissingColumnError` to `errors` and then executes `continue`, skipping that family's rows. But `errors` is raised only if **no** family produced a table. If at least one later generation has the column, `load()` returns only those later-generation rows and silently omits all rows from generations without the field.

Example:

```text
1995–2005 family: 1,000,000 rows, does not have X
2006–2025 family: 3,000,000 rows, has X

load(..., years=1995:2025, columns=["X"])
```

can return 3,000,000 rows with no exception, making it appear that the requested longitudinal dataset naturally begins in 2006 rather than that the API discarded the earlier million rows.

The existing tests appear to cover the easier case where **no** generation has the requested field; they do not cover “some generations have it, some do not.”

**Required fix:** establish one explicit public policy and apply it consistently. The safest default is to raise if any selected generation lacks an explicitly requested field, with the missing intervals/families in the exception. A secondary opt-in mode could preserve all rows and null-fill structural absence, but it must mark that nullness as structural rather than observational.

### CR-04 — `load()` lacks `fetch()`'s file-axis safety check and can return a false empty answer

**Location:** `src/pegasus_data/retrieve.py::_check_axes()` versus `src/pegasus_data/api.py::load()` and `src/pegasus_data/persist/lake.py::read()`.

`fetch()` contains one of the strongest safety ideas in the project: `FilterHasNoAxis`. It refuses `uf=` or `year=` filters when a dataset's publication files are not physically split on that axis, because matching filenames/partitions on a nonexistent file axis would yield an empty result that looks like “zero events.”

`load()` does not perform this check. `Builder` writes unknown/non-file axes as partition values such as `uf=NA` and `year=0`. `Lake.read()` then blindly applies Hive partition predicates to `uf` and `year`.

For a national dataset whose state exists only as a **column inside the rows**, this request:

```python
load(system, series, uf="AC")
```

can filter the lake on `uf=AC`, match no physical partition, and raise “no lake data”/return no rows even though Acre records are present inside a national partition. That is exactly the false-empty failure `fetch()` was specifically written to prevent.

**Required fix:** centralize axis validation and use it from both `fetch()` and `load()`. If a user wants a row-level state filter on a national file, expose a distinct row-filter mechanism or document that the caller must filter a returned column. Do not overload the same `uf=` argument to mean a file axis sometimes and a row predicate at other times.

### CR-05 — Dataset/family resolution is split between two incompatible implementations

**Location:** `src/pegasus_data/retrieve.py::_families()`; `src/pegasus_data/api.py::_resolve_family()`; `src/pegasus_data/persist/duck.py::register_all()`; indirectly `describe()`.

`retrieve._families()` contains a detailed comment explaining that exact `series = ?` matching is empirically wrong. It gives measured examples: SIA-PA appears across hundreds of filename-derived series spellings, and exact matching previously found only a tiny fraction. The function therefore resolves families through the declared ontology.

`api._resolve_family()` nevertheless uses exact SQL matching on `families.series`. `load()` and `describe()` use that resolver. `DuckLake.register_all()` likewise groups families by raw `(system, series)` strings.

The result is a public API split-brain:

- `fetch("SIA-PA", ...)` may correctly aggregate all ontology-bound PA families.
- `load("SIA", "PA", ...)` may load only families whose raw `series` happens to equal `PA`.
- the DuckDB dataset view may fragment one logical dataset into many raw-series views.
- `describe()` can describe a subset inconsistent with `fetch()`.

A package whose central abstraction is “logical dataset despite unstable publication filenames” should have exactly one dataset resolver.

**Required fix:** make ontology-aware dataset resolution a shared service used by `fetch`, `load`, `describe`, `Catalog.coverage`, `DuckLake.register_all`, exports, and any CLI command that accepts a logical dataset. The raw filename-derived series should remain provenance, not public identity.

### CR-06 — Replacing a Parquet partition is destructive before the replacement is safely written

**Location:** `src/pegasus_data/persist/lake.py::write_batches()` and `_clear_partition()`.

`Lake.write_batches(replace=True)` first calls `_clear_partition()`, which deletes the existing Parquet files and their catalog rows. Only afterward does it create the new directory and call `pq.write_table()`.

If the new write fails because the disk fills, the process is interrupted, Arrow raises, or the machine loses power, the previously valid partition has already been deleted. If the Parquet write succeeds but the subsequent catalog update fails, the file remains on disk without matching metadata; `ds.dataset()` reads files from disk directly, so catalog state and analytical state diverge.

**Required fix:** use staged/transactional replacement. Write the new partition to a sibling temporary directory or temporary file, fsync/validate it, prepare the catalog change, and then atomically rename/swap the staged partition into place. Keep the old partition until the new artifact is complete. Add crash-recovery logic for abandoned staging files.

## P1 — high-priority `fetch()` performance and reliability findings

### HI-01 — A completely warm-cache `fetch()` still opens FTP connections before checking the cache

**Location:** `src/pegasus_data/acquire/fetcher.py::fetch_many()` and `fetch_one()`.

Every fetch worker constructs an `FtpClient` and calls `client.connect()` before it retrieves a path from the queue and before `_fetch_one()` calls `_should_skip()`. Therefore an all-cache-hit request can still open up to eight FTP sessions that perform no useful work.

This makes local reuse dependent on DATASUS availability and latency. If DATASUS is unreachable, a request whose complete source bytes already exist on the SSD can wait for network connection failure before using them.

**Fix:** classify verifiable cache hits before creating workers. Start FTP clients only for the unresolved misses. `fetch_one()` should also check `_should_skip()` before connecting.

### HI-02 — One worker's FTP connection failure can drain and fail the entire shared queue

**Location:** `src/pegasus_data/acquire/fetcher.py::fetch_many()`, worker connection exception path.

If a worker fails `client.connect()`, it enters a loop that drains `work.get_nowait()` and marks every path it sees as failed. With several workers, this means one worker can fail quickly, empty the global queue, and deprive other workers that successfully connected of work.

The comment says draining is needed because `fetch_many` waits on `work.join()`, but the implementation no longer uses an unbounded `work.join()`; it polls completion. The comment and control flow have diverged.

This makes connection concurrency reduce robustness: one transient connection failure can turn a batch that seven healthy workers could have completed into an all-path failure.

**Fix:** a worker that cannot establish its connection should record the worker-level error and exit. The scheduler should track live workers and fail outstanding paths only if no workers remain or per-path retries are exhausted. Better still, connect lazily per worker and permit reconnection rather than treating initial connection establishment as a batch-wide condition.

### HI-03 — Cache freshness cannot implement its own documented mtime policy

**Location:** `acquire/fetcher.py::_should_skip()`; `catalog/schema.sql::fetches`; `catalog/store.py::record_fetch()`.

The fetcher docstring says a file is skipped only when the listing's size/modified timestamp still matches what the catalog recorded **when that blob was fetched**. The `fetches` table does not store the remote size/mtime observed at fetch time. `_should_skip()` joins the historical fetch row to the **current** `files` row, compares current listed size to stored byte size, and merely checks whether a current mtime exists. It cannot compare “then mtime” with “now mtime” because the former does not exist.

A republished file whose byte count stays unchanged can therefore be skipped despite changed contents.

There is a secondary issue in `Catalog.upsert_files()`: missing new `size` or `modified` values are merged with `COALESCE(excluded..., files...)`, preserving an old signal. A listing that no longer supplies mtime can thus leave a historical mtime looking current.

**Fix:** persist `remote_size_at_fetch`, `remote_modified_at_fetch`, and ideally the listing/change-signal method in the fetch record. Compare them against the current observation. Where the remote server provides no trustworthy change signal, re-fetch and let SHA-256 settle identity as the architecture already intends.

### HI-04 — Transfer “resume” is documented but not implemented

**Location:** `src/pegasus_data/acquire/fetcher.py` module docstring; `src/pegasus_data/discovery/ftp_client.py::retrieve()`.

The acquisition module advertises “retry, resume,” and `retrieve()` says it retries and resumes where supported. The actual transfer always starts with:

```python
self.ftp.transfercmd(f"RETR {path}")
```

into a new empty `BytesIO`. No REST/restart offset is passed. A failure at 95% restarts from byte zero.

**Fix:** stream into a durable `.part` file, retain the number of verified bytes, issue `REST <offset>`/the corresponding `ftplib` restart parameter when supported, and append. Before resuming, validate remote size/mtime so a changed file is not spliced onto an old partial file.

### HI-05 — Full FTP files are buffered in RAM before being hashed and written to disk

**Location:** `discovery/ftp_client.py::retrieve()`; `acquire/fetcher.py::_fetch_one()`; `acquire/cache.py::put_bytes()`.

`retrieve()` accumulates every chunk in `io.BytesIO`, calls `getvalue()` to create a complete `bytes` object, and returns it. `_fetch_one()` then passes that full object to `BlobStore.put_bytes()`, which hashes it and writes it to a temporary file before renaming.

With eight concurrent downloads, peak RAM can include several complete DBC files simultaneously, even though no analytical operation needs all of those compressed bytes in memory.

**Fix:** make acquisition file-stream based. Stream socket chunks into a `.part` file while incrementally updating SHA-256, then atomically move the completed file into the content-addressed store. This also enables real resume and more accurate network-byte accounting.

### HI-06 — Cached DBC decoding performs avoidable whole-file RAM and disk copies

**Location:** `retrieve._decode_one()` / `build.Builder.build()`; `acquire/cache.py`; `decode/registry.py`; `decode/dbc.py`.

The current cached DBC path is effectively:

```text
content-addressed blob on disk
→ Path.read_bytes() (whole compressed file into RAM)
→ ReaderRegistry.open_bytes()
→ read_dbc_bytes()
→ write whole DBC to a temporary file
→ datasus_dbc decompression to temporary DBF
→ read whole DBF back into RAM
→ parse Arrow batches
```

This is especially unnecessary because `BlobStore.materialize()` already exists specifically to provide path-only readers with a hardlink to a cached blob, and `decode/dbc.py` itself says callers working from the blob store should hand the decoder a materialized path.

**Fix:** add a real path-based `ReaderRegistry.open_path()` that does not immediately call `read_bytes()`, and route DBC/blob decoding through the CAS path or a hardlink. Then read the inflated DBF from a file/mmap/batch reader rather than requiring another full `bytes` copy.

### HI-07 — `fetch(columns=...)` pays almost the full cost of every unrequested column

**Location:** `retrieve.fetch()` and `_read_families()`; `decode/dbf.py`; `normalize/engine.py`.

Column selection happens only after `_read_families()` has downloaded/reused, decoded, normalized, provenance-augmented, and concatenated the full table. `read_dbf_bytes()` constructs an Arrow array for every DBF field, and normalization visits every field. Only then does `fetch()` call `table.select()`.

DBC's compressed record stream must be decompressed from the beginning, so compression itself cannot be column-pruned. Everything **after** decompression can be. A two-column SIH request should not construct, normalize, and later discard roughly a hundred other Arrow columns.

**Fix:** compute a projection dependency closure at API entry: requested output columns + columns required to normalize/render/derive them + provenance fields explicitly requested. Pass that field set through ReaderRegistry/DBF parsing and NormalizePlan so unneeded Arrow arrays are never built.

### HI-08 — File-level DBC decoding is serialized despite the module explicitly recommending cross-file parallelism

**Location:** `retrieve._read_families()` and `build.Builder.build()`; comment in `decode/dbc.py`.

`decode/dbc.py` correctly states: “parallelise across files, never within one.” `_read_families()` nevertheless loops through selected files one at a time. `run_with_timeout()` creates a thread for a single call and immediately joins it; it is a watchdog, not a work pool.

For a normal state-year SIH pull, twelve independent monthly DBCs are therefore decoded sequentially.

**Fix:** use a bounded file-level executor with a memory budget. Two to four concurrent DBC decodes will usually be a safer starting point than matching CPU count because each decode can transiently be large. Preserve deterministic output order separately from execution order.

### HI-09 — Archive sources can be decoded repeatedly once per selected member

**Location:** `retrieve._read_families()` / `_decode_one()` and `build.Builder.build()`.

The acquisition path deduplicates source paths, but the decode loop is over `(family, path, member)` records. `_decode_one()` opens and decodes the entire source blob and only then selects the requested member. If one archive contains several logical DBF members—explicitly a supported APAC case—the same archive can be reopened/decompressed/reparsed separately for each member or family record.

**Fix:** group selected work by source path/digest. Decode an archive once per fetch/build call, cache its `DecodeOutcome` for that source, and dispatch matching member tables to all requested family/member consumers.

### HI-10 — `fetch()` inherently materializes the entire requested extract, and its normalization adds expensive repeated provenance strings

**Location:** `retrieve._read_families()`; `normalize/engine.py::add_provenance()`.

`_read_families()` retains every normalized `RecordBatch` in a Python list and combines them only after all selected files are processed. Because `fetch()` returns a `pa.Table`, a final materialization is part of the current contract, but peak memory is amplified by retaining wide intermediate batches and by adding four repeated string values per row (`_source_path`, `_blob_sha256`, `_ingested_at`, `_schema_signature`). These are built with patterns like `pa.array([value] * n, type=pa.string())`, not compact dictionary arrays.

At millions of rows, constant provenance strings can represent hundreds of megabytes of transient Arrow string buffers.

**Fix:** dictionary-encode constant provenance, keep provenance at batch/file metadata when possible, and introduce a streaming/scanner public API for large requests (`scan()`/`iter_batches()`), with `fetch()` documented as the eager convenience API.

### HI-11 — Label rendering repeatedly leaves Arrow and loops through Python objects

**Location:** `src/pegasus_data/view.py`, especially `_labels_for()`, `_check_width()`, `_combine()`, `_derive_age_years()`, `_render_multi_valued()`, `_contradictions()`, and `render_table()`.

The default `fetch(labels=True)` path repeatedly calls `to_pylist()` on whole columns, builds Python sets, performs Python dictionary lookups per row, and then reconstructs Arrow arrays. Several labelable columns are traversed more than once: observed-code set, width checks, contradiction checks, mapping, and combination.

For a million-row categorical field with six distinct values, doing one million Python dictionary lookups is the wrong cost model. Arrow/dictionary encoding can reduce semantic mapping to a handful of unique codes plus an index remap.

**Fix:** dictionary-encode each code column once; resolve labels for unique codes; use Arrow `index_in`, `take`, dictionary arrays, joins, or equivalent vectorized primitives; memoize reference maps and contradiction maps for the render call. Avoid unconditional `combine_chunks()` for columns that do not need it.

### HI-12 — Reference-table reads defeat Parquet partition/filter pushdown

**Location:** `persist/reference.py::read_reference_table()`.

Reference tables are stored in Hive-partitioned directories by system and window, but `read_reference_table()` first does:

```python
dataset = pads.dataset(base, ...)
table = dataset.to_table()
```

and only afterward filters `system`, `code_width`, `valid_from`, and year in Python/Arrow, often via `to_pylist()`.

Thus every lookup can read every system/window for that codelist before discarding almost all of it. `render_table()` may evaluate up to twelve candidate codelists for one ambiguous field, multiplying this cost.

**Fix:** build a PyArrow Dataset filter expression and projection before `to_table()`. Push down `system`, `window`, and code-width predicates. Cache the resulting `(codelist, system, vintage, width)` lookup map within and across a render operation where safe.

### HI-13 — The first labelled `fetch()` can unexpectedly materialize the entire reference warehouse

**Location:** `retrieve._ensure_reference_tables()`; `persist/reference.py::write_reference_tables()`.

If no materialized reference tables exist but the catalog dictionary does, a normal `fetch(labels=True)` calls `write_reference_tables()`, whose contract is to materialize **every code table**. This is a global build-stage side effect hidden inside an interactive retrieval API. The function also deletes and rebuilds the whole reference root.

**Fix:** make label lookup lazy per required codelist or use the shipped label pack directly. A fetch for SIH sex/age fields should not have to materialize unrelated codelists for every DATASUS system.

### HI-14 — Cold `fetch()` discovery performs a broader schema census than the request needs

**Location:** `retrieve._discover()`; `pipeline.Pipeline.schemas()`.

On a fresh catalog, `fetch("SIH-RD", uf="AL", years=2024)` crawls the requested system, inventories it, then calls `pipeline.schemas(systems=[system])`. The schema census can therefore issue prefix requests for every missing stratum in the system, not only RD/AL/2024. Byte volume is intentionally tiny, which is good, but hundreds/thousands of sequential FTP round trips can dominate wall time on a high-latency legacy server.

`Pipeline.schemas()` itself uses one FTP client and processes targets sequentially.

**Fix:** add a request-scoped census mode that learns only enough schema/family information to fulfill the requested logical dataset and temporal/geographic filters. Keep exhaustive system census as an explicit catalog-building stage.

### HI-15 — The timeout abstraction abandons threads rather than stopping work, and one use shares an FTP client with the abandoned thread

**Location:** `progress.py::run_with_timeout()`; `pipeline.py::schemas()`; `retrieve._read_families()`.

`run_with_timeout()` explicitly acknowledges that a timed-out worker thread is left alive. That means “timeout” limits how long the caller waits, not how long CPU, disk, memory, or external-library work continues. Repeated timeouts can leave several expensive decoders active in the background.

The schema census is more dangerous: it wraps `client.retrieve_prefix()` in `run_with_timeout()` while reusing one shared `FtpClient`. If a prefix request times out, its abandoned thread may still be reading/reconnecting the same FTP object while the main stage advances to another target using that client. `ftplib.FTP` is not designed for concurrent protocol operations on one control connection.

**Fix:** do not use an unkillable thread as the ownership boundary for stateful network clients. Use socket-level deadlines and synchronously replace the client after failure, or isolate each timeout-able operation in a process/disposable client that can be terminated without sharing mutable protocol state.

### HI-16 — A stalled fetch can return while worker threads remain active and keep mutating catalog/stats

**Location:** `acquire/fetcher.py::fetch_many()` stall path.

When the batch stall deadline is reached, the main thread records `stats.stalled`, pushes sentinels, joins each worker for at most five seconds, and returns. In-flight daemon workers are not cancelled. Sentinels are also appended behind outstanding queued work, so a worker that eventually recovers can continue processing ordinary paths before reaching its sentinel.

That permits late blob writes/catalog updates after `fetch_many()` has returned and after `ensure()` has already started resolving available digests. `FetchStats` can also change after the caller thinks it is final.

**Fix:** add a cancellation event checked before dequeuing another item; stop scheduling on stall; actively close/replace data sockets where safe; do not return ownership until workers are known stopped or their late results are explicitly isolated from the returned batch state.

### HI-17 — `fetch()` discards acquisition diagnostics and its `bytes_downloaded` metric is not network bytes

**Location:** `Fetcher.ensure()` and `retrieve._read_families()` / `FetchReport`.

`ensure()` throws away the `FetchStats` object, so `fetch()` cannot report cache hits, network misses, retries, failed refresh reasons, or stalled paths from the acquisition layer. Missing digests are later reduced to `undecoded` without preserving the causal network error.

Separately, `_decode_one()` returns `len(payload)`, and `_read_families()` adds that value to `FetchReport.bytes_downloaded` whether the bytes came from the network or from a six-month-old local blob. A warm-cache request can therefore report megabytes “downloaded” despite zero network traffic.

**Fix:** return a structured acquisition result from `ensure()` containing per-path status and digest. Track at least `network_bytes`, `cache_bytes_read`, `cache_hits`, `cache_misses`, retries, and errors. Keep “raw bytes decoded” as a separate metric if useful.

### HI-18 — Builder/Lake code creates batches but then defeats streaming immediately before Parquet output

**Location:** `build.Builder.build()` and `persist/lake.py::write_batches()`.

`Builder` accumulates every normalized batch for a `(UF, year)` partition in a list. `Lake.write_batches()` then makes another `collected` list and creates one whole `pa.Table` before calling `pq.write_table()`.

The design therefore carries batch abstractions through decoding and normalization but materializes the entire state-year partition at the storage boundary—the place where streaming is most valuable.

**Fix:** use `pyarrow.parquet.ParquetWriter` (or dataset writer) and write batches incrementally to a staged partition, accumulating row/byte statistics separately.

### HI-19 — Re-running `build` re-decodes and re-normalizes unchanged source data

**Location:** `build.Builder.build()`; `lake_partitions` metadata.

The raw CAS prevents re-downloading unchanged blobs, but the derived Parquet layer has no source/transformation fingerprint. A repeated build still reads the raw blobs, decompresses DBC, normalizes, and rewrites partitions.

**Fix:** record a deterministic partition build fingerprint derived from ordered source SHA-256 values plus normalization/schema/curation version and relevant build options. Skip a partition when both source and transformation fingerprints match. This turns the lake into a real derived-data cache instead of only a storage target.

### HI-20 — Reference-table rebuilding is destructive and non-atomic

**Location:** `persist/reference.py::write_reference_tables()`.

The function begins with `shutil.rmtree(root)` and then reconstructs every reference table. A failure midway leaves the reference warehouse partially absent. Because labelled APIs may call this implicitly, an interactive request can degrade an otherwise valid local installation.

**Fix:** write to `reference.__staging__`, validate, then atomically swap directories. Incremental per-codelist materialization would be preferable for interactive use.

### HI-21 — The render lookup cache key omits code width/field context

**Location:** `view.render_table()` nested `_lookup()`.

The cache key is only:

```python
key = "|".join(codelists)
```

but the lookup produced below that key depends on `field_name` through the curated token width. Two fields using the same codelist list but requiring different widths can therefore share a lookup that was filtered for the first field's width.

This undercuts one of the project's central protections against mixed-width classifications.

**Fix:** key on the complete semantic lookup context, at least `(tuple(codelists), system, vintage, code_width)`, or simply on field + those parameters.

### HI-22 — Explicitly requested derived columns do not cause their input dependencies to be loaded

**Location:** `api.load()` projection construction and `view._apply_derived()`.

`load(columns=...)` projects only the requested raw columns and optional companions. `_apply_derived()` later skips a derivation when its required source columns are absent. Therefore a caller can explicitly request a derived field while using a narrow `columns=` projection and receive no derived field simply because the API did not pull the dependencies needed to produce it.

**Fix:** resolve the derivation dependency graph before reading. Hidden dependencies can be loaded, used to compute the requested derived result, and then dropped from the final projection unless the caller requested them directly. If a requested derivation cannot be produced, raise or report it explicitly rather than silently `continue`.

### HI-23 — DBF record-count reconciliation can silently truncate valid trailing records

**Location:** `decode/dbf.py::read_dbf_bytes()` around `n_records = min(declared, available)`.

The code notes that DATASUS DBF header record counts are “frequently stale,” then chooses the smaller of header-declared and physically available complete records. If the stale header is **lower** than the complete record count on disk, this necessarily drops valid trailing records. The adjacent comment says the policy avoids “dropping rows,” but `min()` does the opposite in that case.

I cannot determine from this archive alone how often DATASUS headers are stale-low rather than stale-high, so this is a high-risk correctness issue requiring empirical validation rather than an assertion that current published data are already truncated.

**Fix:** characterize mismatch direction on the corpus. If physically complete records beyond the declared count are structurally valid and followed by a proper EOF, prefer the physical count and record a warning; otherwise establish a documented conservative rule and expose mismatch counts in verification.

### HI-24 — DuckDB file decoding leaks temporary directories

**Location:** `decode/registry.py::_read_duckdb()`.

The implementation uses `tempfile.mkdtemp(prefix="pegasus_duck_")` and comments that it “is cleaned when the process exits.” `mkdtemp()` does not register automatic cleanup. No `TemporaryDirectory` owner is retained and no `rmtree` is performed.

Repeated `.duck` decoding therefore leaks temp directories/files until external OS cleanup, potentially substantial for large databases.

**Fix:** make the decoded object own a `TemporaryDirectory` whose lifetime extends only as long as the DuckDB reader needs it, or materialize the CAS blob by path and avoid a copy entirely.

### HI-25 — Archive-member read failures can disappear without appearing in the decode outcome

**Location:** `decode/registry.py::_read_archive()` and `decode/archives.py::iter_members()`.

`_read_archive()` catches `Exception` around `archive.read(member.name)` and simply `continue`s. No failed `DecodeAttempt`, warning, open question, or member-level error is added. This contradicts the broader package guarantee that every file/member that could not be read is named.

**Fix:** record a member-qualified decode attempt/error and keep it in `DecodeOutcome`; include it in `FetchReport`/build diagnostics.

### HI-26 — One-entry reference groups are silently omitted during materialization

**Location:** `persist/reference.py::write_reference_tables()`, nested `_flush()`.

The writer returns without writing when `len(batch) < 2`. A codelist/window/system combination containing exactly one legitimate code is therefore absent from the materialized reference lake with no warning.

Unless there is an explicit semantic reason that a one-code list is invalid, this is a correctness bug.

**Fix:** write any non-empty group. If singleton groups are suspected parser debris, validate them before persistence and record the rejection explicitly.

### HI-27 — Cross-system “borrowed” codelists are used implicitly

**Location:** `persist/reference.py::read_reference_table()`.

When `system=` is requested, the function narrows to that system only if scoped rows exist. Otherwise it returns the unscoped union and relies on contradiction checking later. The docstring explicitly calls this “a borrowed table.”

This can produce labels from another system without the returned data/report making that provenance obvious. Contradiction detection catches only disagreements among overlapping observed codes; a foreign table with non-overlapping or coincidentally identical codes can still be accepted.

**Fix:** return reference-resolution metadata (`native_system`, `borrowed_from`, fallback reason) and make borrowing explicit in `RenderReport`. Consider requiring `allow_borrowed=True` for strict analytical profiles.

### HI-28 — `export()` is eager end-to-end and does not guard Excel's hard limits

**Location:** `api.export()`, `write_table()`, `_flatten_lists()`, `_write_xlsx()`.

`export()` first calls eager `load()`, fully renders a `pa.Table`, then writes it. CSV and Parquet exports therefore cannot exploit streaming even though the destination itself could. `_flatten_lists()` additionally combines chunks / Pythonizes list columns.

The XLSX writer uses openpyxl write-only mode, which is good, but there is no check for Excel's worksheet limits (1,048,576 rows and 16,384 columns). A large epidemiological extract can therefore produce a workbook that Excel cannot faithfully represent.

**Fix:** build exports on a scanner/batch interface, stream CSV/Parquet, and enforce/split Excel dimensions with an explicit message.

## P2 — medium-priority API, performance, maintainability, and observability findings

### ME-01 — `years` accepts an integer in `fetch()` but not in `load()`

`fetch(years=2024)` is normalized by `_as_years()`. `load()` and `Lake.read()` type the argument as a sequence/range and eventually call `list(years)`, so the analogous `load(..., years=2024)` is not supported. Public APIs that otherwise present themselves as parallel should share filter normalization.

### ME-02 — `labels` and `profile` overlap confusingly, and one branch is a literal no-op

In `api.load()`:

```python
if labels is False and profile == "analysis":
    profile = "codes"
if labels is True:
    strict_labels = strict_labels or False
```

The second branch does nothing. `labels=True` also does not necessarily override a caller-supplied `profile="codes"`. The surface has accumulated two ways to express the same rendering decision.

**Recommendation:** make `profile` authoritative and deprecate `labels`, or precisely define precedence in one normalization function.

### ME-03 — Equivalent failures use inconsistent exception classes across `fetch()` and `load()`

`fetch()` has domain-specific `DatasetUnknown`, `NothingPublished`, `FilterHasNoAxis`, and `MissingColumnError`. `load()` often raises generic `KeyError` or `FileNotFoundError` for corresponding situations. This makes robust downstream handling unnecessarily dependent on which retrieval path was used.

**Recommendation:** define a shared public exception hierarchy and use it from both online and lake-backed APIs.

### ME-04 — `FieldDescription.__repr__()` can fail when semantic confidence is unknown

`semantic_confidence` is typed as `float | None`, but `__repr__()` formats it with `:.2f`. An unresolved field with `None` confidence will raise `TypeError` simply when displayed in a notebook/REPL.

### ME-05 — `open_lake()` leaks the catalog connection it creates

`api.open_lake()` creates a `Catalog`, passes `cat.store` into `DuckLake`, and returns only the `DuckLake`. `DuckLake.close()` closes DuckDB but does not own/close the catalog store. The catalog connection therefore has no exposed owner after `open_lake()` returns.

**Fix:** make `DuckLake` optionally own the `Catalog` and close both, or return a wrapper/context object that does.

### ME-06 — Runtime configuration contains dead or ignored controls

`Settings.process_workers` is not referenced elsewhere in the package. `Settings.keep_raw` defaults to `False`, but both `fetch()` and `Builder.build()` force `plan.keep_raw=True` unless the CLI explicitly supplies a build option; the setting is therefore not the default policy it appears to be.

Unused knobs make performance tuning misleading. Either wire them into the implementation or remove them.

### ME-07 — `FetchReport.years_returned` and `ufs_returned` are publication-file facts, not necessarily row coverage

`_read_families()` populates returned years/UFs from `file_facts` for matched source files. For national files containing many states internally, `ufs_returned` can be empty/`NA` even though the returned table contains all states. The name sounds like row-level result coverage.

**Recommendation:** rename to `file_years_returned` / `file_ufs_returned`, and optionally compute row-level coverage only when a known canonical row field is available.

### ME-08 — Normalization is described as fully vectorized but contains important Python row loops

`normalize/geo.py::to_seven_digit()` and `uf_array()` use `to_pylist()` and Python comprehensions. `normalize/time.py::parse_date_array()` falls back to element-wise Python on invalid dates, and `epi_week_array()` always iterates through Python `date` objects. The fallback date parser is defensible for malformed values; the general municipality/UF and epidemiological-week paths deserve vectorization or lookup joins.

The issue is both performance and documentation accuracy: a developer reading “every step is vectorised” will look in the wrong place when profiling large fetches.

### ME-09 — The DBF reader's “zero-copy” claim is inaccurate

`decode/dbf.py::_string_array()` calls `np.ascontiguousarray()` on a strided record slice and then `.tobytes()`. Those are copies. Arrow then receives the resulting byte buffer. The reader is sensibly vectorized compared with row-at-a-time DBF libraries, but it is not zero-copy.

This matters when reasoning about memory bandwidth for a 100+ column DBF.

### ME-10 — Build accounting records mismatched sources as though they contributed to a partition

In `Builder.build()`, `sources.append(path)`, `stats.files += 1`, and `family_files += 1` occur even when `matched_here` is false because the decoded table does not fit the family's schema. A subsequently written partition can therefore list a `source_path` that contributed zero rows because of schema mismatch, and `files_decoded` is closer to “files attempted” than “files accepted.”

**Recommendation:** separate attempted, decoded, schema-matched, and rows-contributed counters; only attach contributing sources to the partition provenance.

### ME-11 — `load()` does unnecessary work across irrelevant families and uses N+1-style schema queries on error paths

`_resolve_family()` can return many families. `load()` tries each one rather than first pruning by catalog `time_min/time_max`, available lake partitions, requested UF, and requested years. On large fragmented systems this causes unnecessary filesystem/dataset opens.

When columns are missing, it also computes “elsewhere” by repeatedly calling `store.count()` inside nested family/column loops. The schema-presence matrix should be loaded once.

### ME-12 — Rendering emits every report warning through Python's global warning channel

At the end of `render_table()`, every `RenderReport.warning` is also `warnings.warn(...)`. Wide datasets with many unresolved/ambiguous fields can generate a large warning stream, adding latency and making notebook output difficult to use.

**Recommendation:** let the structured report be the default carrier; emit one aggregate warning or make warning emission configurable.

### ME-13 — Codelist candidate selection is bounded and scores distinct codes rather than row-weighted coverage

`_choose_binding()` tests at most `_MAX_CANDIDATES = 12`, even though comments note fields can have 114 bound tables. The list is ranked, but correctness still depends on the true table appearing in the first twelve. Candidate coverage is `hits / len(observed)` where `observed` is a set, so a rare unique code has the same weight as a code present in 90% of rows.

Distinct-code coverage is a reasonable semantic signal, but it should not be the only one. A robust report should expose both distinct-code and row-weighted coverage, and strong curated/family-specific bindings should eliminate search where possible.

### ME-14 — Reference validity is calendar-year-level, not competência-level

Even after CR-02 is corrected to avoid one year for the entire table, `read_reference_table(year=...)` cannot distinguish two codelist windows within the same year. The schema already stores `valid_from`/`valid_to` in `YYYYMM`-like form, so the API should accept `competencia` or an exact date where source semantics require it.

### ME-15 — A supposedly read-oriented `Catalog()` can create a new persistent catalog as a side effect

`api.Catalog.__init__()` opens read-only only if the catalog path already exists; otherwise it creates a writable `_Store`, which migrates/creates the catalog. A user who calls a read method against the wrong root can therefore create an empty database and receive “nothing found” rather than “no catalog exists here.”

Consider an explicit `create=False`/`read_only=True` public default for inspection APIs, with pipeline/build code responsible for creation.

### ME-16 — `_read_archive()` mutates the list it is iterating

`decode/registry.py::_read_archive()` starts with `members = archive.members()` and then extends `members` with nested `inner.members` inside `for member in members`. Python's list iterator sees appended items, so nested synthetic member names can later be treated as if they were direct members of the outer archive, causing redundant failed reads or confusing traversal.

Use a snapshot for direct members and a separate result list for recursively discovered members.

### ME-17 — Source archive hygiene and reproducibility are weak

The supplied archive includes multiple `__pycache__` directories and generated `.egg-info` but omits the top-level packaging/config files needed to reproduce lint/type/test tooling. This is not necessarily true of the canonical repository, but the artifact itself is not a clean review/release source bundle.

### ME-18 — Several hot-path modules/functions are too complex for the invariants they enforce

`render_table` at complexity 80 is the standout. It simultaneously handles codelist selection, ambiguity, mixed widths, internal/external rendering modes, multi-valued parsing, contradictions, labels, companions, derived variables, translated headers, warnings, and reporting. `api.load`, `Builder.build`, and `Fetcher.fetch_many` similarly combine policy, orchestration, error handling, and I/O.

The defects in this review often arise at those boundaries. Refactoring should be behavioral, not cosmetic: isolate dataset resolution, filter normalization, semantic partitioning, reference resolution, acquisition scheduling, and materialization into independently testable components.

### ME-19 — Environment-variable configuration is asymmetric

`load_settings()` honors `PEGASUS_CONNECTIONS` for crawler connection count but not an analogous environment override for `fetch_concurrency`, item timeout, stall timeout, or process workers. Since acquisition and crawl have separate concurrency knobs, a user can believe they tuned network pressure while `fetch()` still uses eight workers.

### ME-20 — There is no lazy public analytical API between `fetch()` and the lake

The package currently offers eager `fetch()` and eager `load()` returning whole `pa.Table` objects, plus a DuckDB connection for lake data. A natural missing primitive is a `scan()` / `dataset()` / `iter_batches()` interface that supports projection, predicates, and bounded memory without forcing a materialized table. This would make national/multi-year analyses much safer and would also give `export()` a streaming foundation.

### ME-21 — External archive extraction could use explicit path-safety hardening

RAR/7z handling extracts remote archive contents through `rarfile.extractall()` or external 7-Zip into a temporary directory. The source does not perform its own validation that member paths remain within the intended extraction root before collection. I did not establish an exploitable traversal with the particular tools/versions, so this is a hardening recommendation rather than a confirmed vulnerability.

Because DATASUS archives are remote input, the package should validate normalized member paths and reject absolute/parent-traversal paths regardless of what the extraction backend currently sanitizes.

## Additional design inconsistencies and smaller defects

### Fetch and load disagree on structural missingness

`fetch()` concatenates Arrow tables from different schemas using `promote_options="permissive"`. If a requested column exists in at least one generation, the combined table contains it and older generations can be null-filled. `load()` instead skips generations lacking that column (CR-03). Thus the same logical request can produce different row counts and structural-missingness semantics depending on whether it came directly from raw DBC or from the lake.

This should be resolved as one public policy, not left as an implementation accident.

### `max_files` truncation is global and can bias schema/family coverage

`_read_families()` builds `selected` family by family and then applies `selected = selected[:max_files]`. This is useful for debugging, but it preferentially keeps earlier families and can make `report.families` name families whose files were all removed by truncation. If this option is public, define whether it is “first N source artifacts for debugging” rather than a representative sample.

### Set construction is repeated inside file-selection comprehensions

Both fetch/build selection expressions repeatedly construct `set(ufs)`, `set(years)`, etc. inside row comprehensions. This is a minor cost relative to DBC decoding, but trivial to remove by precomputing filter sets once.

### `write_reference_tables()` and the lake have different durability models but both mutate derived state globally

Both should use the same staged-artifact abstraction. A general “derived artifact transaction” utility would reduce duplicate recovery logic and make rebuild semantics easier to test.

### Reference fallbacks should be provenance-bearing values, not implicit branch behavior

The same principle applies to current-vintage fallback when a requested historical year has no explicit window. `read_reference_table()` silently returns current or the whole table when no dated match exists. The caller can inspect `valid_from`, but `render_table()` does not automatically warn that a historical label used a fallback vintage. That should be visible in `RenderReport` and strict mode should be able to reject it.

### Per-row label construction can often preserve dictionary encoding

Even after vectorizing lookup, the API does not need to expand every repeated label into a full plain-string Arrow buffer. Returning dictionary-encoded categorical labels can reduce memory substantially. A report/export path can expand them only at final serialization if necessary.

### `ReaderRegistry.open_path()` defeats the purpose of accepting a path

It immediately does `p.read_bytes()` and routes to `open_bytes()`. A path API should allow readers such as DBC, Parquet, XLSX, DuckDB, and DBF to work with paths directly so memory mapping, streaming, and third-party file APIs can be used.

### Archive/decode failure granularity is inconsistent

The registry properly catches and records top-level reader exceptions as `DecodeAttempt`, but inner archive member read exceptions are swallowed. The same error model should extend recursively: source → container → member → reader → normalization.

### Stalled callback exceptions can kill a worker invisibly

`Fetcher.fetch_many()` calls `on_result(result)` outside a protective block in the worker thread. If a user callback raises, that thread exits; the exception is not propagated to the main thread in a structured way. Depending on remaining workers, the batch can limp on or reach a stall without naming the callback exception as the cause. Callbacks should either be explicitly fatal and marshalled back to the caller thread, or isolated and recorded.

### `BlobStore.put_file()` is not atomic like `put_bytes()`

`put_bytes()` stages and `os.replace()`s, while `put_file()` directly `shutil.copy2()`s into the content-addressed target. A crash can leave a partial file at a path whose name claims the complete SHA-256 of the source. This path deserves the same temp-file + atomic-rename discipline.

### `read_reference_table()` fallback may return the whole table when neither dated nor current rows exist

For a requested `year`, if no dated match and no open-ended/current rows exist, it returns `table`. That can merge multiple nonmatching historical windows—the exact state the comments elsewhere say should never be merged. Strict reference resolution should fail or return an explicitly unresolved result instead.

### Warning/fallback metadata should be machine-readable

Many semantic decisions are currently encoded only as free-text strings in `RenderReport.warnings`. For research auditability, important states such as `borrowed_system`, `fallback_vintage`, `partial_codelist_match`, `rollup_used`, and `structural_column_absence` should have structured fields as well as prose.

## Why `fetch()` can lag massively even with a warm cache

The current warm-cache hot path is substantially longer than the name “fetch” suggests:

```text
logical dataset resolution
→ possible metadata/discovery work
→ start FTP workers even for cache hits
→ cache decision
→ read each compressed blob fully into RAM
→ write DBC back to temporary disk
→ decompress to temporary DBF
→ read DBF fully into RAM
→ construct every DBF field as Arrow
→ normalize every field
→ add repeated provenance columns
→ retain all RecordBatches for all files
→ concatenate generations permissively
→ only now apply columns= projection
→ potentially materialize global reference tables
→ repeatedly read/filter codelist Parquet
→ repeatedly convert Arrow columns to Python lists
→ map labels in Python
→ derive companions/derived fields
→ create the final Arrow table
```

Only the first actual network transfer disappears on a cache hit. The expensive derived work is intentionally recomputed because `fetch()` does not use the Parquet lake as a derived cache.

A redesigned fast path should instead resemble:

```text
resolve logical dataset with the shared ontology resolver
→ validate file-axis filters
→ resolve exact source/member work
→ validate all local cache hits BEFORE opening a network connection
→ stream only cache misses to CAS with incremental SHA-256/resume
→ group work by source digest so each archive/source is decoded once
→ decode files concurrently under a RAM budget
→ construct only requested columns + semantic dependency closure
→ normalize only those columns
→ render each (schema family, validity window) partition with the correct codelist
→ use Arrow-native dictionary lookups
→ concatenate final projected batches
→ return table + truthful acquisition/render report
```

For repeated analytical workloads, the preferred route should remain:

```text
CAS raw blobs → one incremental build → Parquet lake → projected/filter-pushed load/scan
```

but the direct `fetch()` API can still become substantially faster and safer without turning itself into `build()`.

## Recommended remediation order

### Phase 0 — correctness before optimization

Fix CR-01 through CR-06 before performance tuning. In particular, do not benchmark an API whose row set and labels can change incorrectly across schema generations. Create regression fixtures for stale refresh failure, multi-vintage labels, mixed-generation missing fields, national-file axis filters, ontology family resolution, and interrupted partition replacement.

### Phase 1 — make warm-cache `fetch()` genuinely local and bounded

Move cache validation ahead of FTP creation; correct the worker connection-failure scheduler; return per-path acquisition results; stream downloads into CAS; implement actual REST resume; decode cached blobs by path/hardlink rather than bytes; and group archive members by source path.

These changes should dramatically reduce unnecessary network dependency, memory copying, and temporary I/O without changing public semantics.

### Phase 2 — push projection and parallelism down the decode pipeline

Compute an output/dependency column closure before decoding; teach DBF parsing to materialize only those fields; normalize only required fields; add bounded file-level parallelism; dictionary-encode constant provenance.

### Phase 3 — replace Pythonized rendering with Arrow-native semantic joins

Render per semantic partition (family + competência/vintage), push reference filters into Parquet scans, cache lookup dictionaries by complete semantic context, dictionary-encode code columns, resolve labels for unique codes, and then remap indices. Make every fallback structured in `RenderReport`.

### Phase 4 — make the lake a real incremental derived cache

Stream partitions through `ParquetWriter`; stage atomically; fingerprint source blobs + transformation versions; skip unchanged partitions; atomically materialize reference tables; add recovery/verification of staging artifacts.

### Phase 5 — unify and simplify the public API

Create shared services for dataset resolution, filter normalization, axis validation, column availability, and exceptions. Add a lazy scanner/batch API. Deprecate overlapping `labels`/`profile` semantics and normalize `years`/`uf` input types across `fetch`, `load`, population, and export.

## Benchmark suite that should be added before claiming `fetch()` performance

A useful benchmark suite should distinguish network, decode, normalization, rendering, and materialization rather than report only wall time. At minimum, benchmark these workloads on a fixed local corpus:

1. **SIH-RD, AL, one year, cold cache, labels off.** Measures actual acquisition + decode.
2. **Same request, warm cache, labels off.** This should perform zero network connection attempts after the cache fix.
3. **Same request, two columns only.** Compare full-width decode vs projected decode.
4. **Same request, labels on.** Isolates semantic rendering/reference lookup overhead.
5. **Five- to ten-year longitudinal request spanning at least two schema/codelist vintages.** Measures both correctness and scaling.
6. **National or high-volume state request.** Measures peak RSS and batch behavior.
7. **Archive-backed dataset with several members.** Detects repeated source decode.
8. **Build followed by identical rebuild.** The second build should eventually become nearly metadata-only when fingerprints match.

Record wall time, CPU time, peak RSS, network bytes, number of FTP connections, cache hits/misses, bytes read from CAS, temporary bytes written, DBC decompression time, Arrow decode time, normalization time, rendering time, reference-table bytes read, and final rows/sec. Without stage-level metrics, an optimization can simply move cost from one opaque block to another.

## Test-suite gaps exposed by this review

The supplied suite is large, which is a strength, but several high-risk interactions are not covered by the tests I inspected. Add explicit regression tests for:

- stale cache rejected → refresh fails → stale blob must **not** be returned;
- all files warm → real `Fetcher` opens **zero** FTP connections;
- one of several worker connections fails while another succeeds → healthy workers still process the queue;
- same-size remote republication with changed mtime/content;
- multi-year rows receiving different label vintages in one returned table;
- historical rows loaded without explicit `years=` not silently receiving current labels;
- family-specific codelist bindings in a multi-generation request;
- requested column present in some but not all generations;
- parity of `fetch()` and `load()` structural-missingness behavior;
- `load()` rejecting a `uf=` file-axis filter on a national-file dataset;
- ontology-based family parity across `fetch`, `load`, `describe`, and DuckDB views;
- interrupted Parquet replacement preserving the previous valid partition;
- interrupted reference rebuild preserving the previous reference tree;
- timeout/cancellation behavior with no background catalog mutation after return;
- archive with multiple selected members decoded only once;
- singleton codelist materialization;
- `FieldDescription` representation with `semantic_confidence=None`;
- `open_lake()` closing every connection it creates;
- Excel row/column limit enforcement;
- DBF header count lower/higher than physical complete-record count.

The current test named along the lines of “catalogued system never touches the network” is not sufficient for HI-01 because the retrieval tests use a fake fetcher and patch discovery rather than exercising the real `Fetcher.fetch_many()` connection/cache order.

## Maintainability observations

The package's comments are unusually valuable: many document actual historical failure modes rather than generic prose. That is worth preserving. The danger is that several comments have become stronger than the implementation. Examples include “retry, resume” without resume; “the second call costs nothing” even though a warm cache still opens FTP and re-decodes; “version-scoped” labelling despite a single scalar year for the whole result; “parallelise across files” while fetch/build decode serially; and “zero-copy” around code that explicitly copies buffers.

I recommend turning those comments into executable invariants. Whenever a comment contains language such as “never,” “nothing is fetched twice,” “version-scoped,” “cannot silently,” or “one call costs nothing,” there should be a focused test/metric proving that property.

The highest-complexity functions should also be decomposed along invariant boundaries. For example, `render_table()` should not own both “which semantic context applies to these rows?” and “how do I map these already-resolved codes to labels?” The first is partitioning/reference resolution; the second can be a small vectorized renderer. Similarly, `Fetcher.fetch_many()` currently owns worker lifecycle, connection establishment, queue scheduling, cache policy, stall detection, callbacks, and result accounting; separating cache planning from network execution would eliminate multiple bugs at once.

## What is already strong and should be retained

The problems above should not obscure that several core choices are correct and worth preserving:

- The content-addressed raw blob model is a substantially better foundation than filename-keyed downloads.
- Schema families and explicit schema drift are appropriate for DATASUS's changing layouts.
- Prefix-only DBF/DBC schema census is an excellent domain-specific I/O optimization.
- Parquet with UF/year partitioning, statistics, dictionary encoding, and Arrow/DuckDB access is the correct analytical storage direction.
- The ontology approach is the right response to unstable filename-derived series identities; the problem is simply that it is not yet used everywhere.
- `FilterHasNoAxis` is exactly the kind of guard epidemiological software should contain; it needs to become a shared API invariant.
- The curated semantic evidence/provenance model is much more rigorous than heuristic labelling alone.
- The renderer's refusal to silently invent labels when codelists disagree is a good policy.
- The codebase already has substantial tests and an internal code-health script, which makes the remediation work tractable.

## Bottom line

`pegasus-data` is architecturally much stronger than a typical DATASUS downloader, but the public API currently has a mismatch between **semantic ambition** and **execution discipline**. The code knows what it should guarantee; several hot paths do not yet guarantee it.

For `fetch()` specifically, I expect substantial unnecessary lag on warm-cache, wide, labelled, multi-file requests because the current path opens network connections unnecessarily, performs repeated whole-file copies, serializes independent DBC decodes, materializes every DBF column before projection, retains the whole extract in memory, and performs much of semantic rendering in Python object space. Those costs are not inherent to DATASUS.

More importantly, `fetch()` and `load()` need correctness work before speed work: failed refreshes can fall back to stale blobs; multi-year labels are not truly row-vintage-scoped; `load()` can silently drop schema generations; `load()` lacks the file-axis guard that prevents false-empty epidemiological answers; and the logical-dataset resolver differs between raw and lake-backed APIs.

The recommended target is not to replace the architecture. It is to make the implementation obey it: **one logical dataset resolver, one filter/axis policy, one structural-missingness policy, explicit freshness state, semantic rendering partitioned by actual vintage/generation, cache-first acquisition, bounded streaming I/O, and atomic derived-state writes.** Once those invariants are centralized, most of the performance work becomes straightforward and the existing Parquet/CAS design can deliver the behavior the codebase already promises.
