No. The codebase is **substantially better than the previous snapshot, and many of the old defects were genuinely repaired**, but I cannot certify the current tree as sound in all regards. More importantly, this is not because I found a handful of cosmetic or maintainability issues. I found several **current correctness defects capable of producing semantically wrong output**, along with serious reliability and I/O problems that the current tests do not exercise adequately.

I treated `pegasus_data_source.zip` as authoritative and re-audited the current implementation rather than carrying old findings forward. The historical `DEFECTS` document says its earlier defect catalogue was closed after live-DATASUS verification, and the current source confirms that many of those fixes really did survive.  At the same time, the newer project notes themselves contain an important warning: municipality labels, doubled labels, and completely blank data dictionaries all survived apparently green test suites and were found only when somebody inspected the actual rendered output.  That warning remains directly relevant to what I found.

## What I could independently validate

The current repository is materially more complete than earlier snapshots. It contains the packaging configuration, about 35,000 lines of package Python, a large test suite, packaged resources, the architecture document and dedicated regression tests for projected vintages, process-isolated decoding, migration constraints, entry-point parity, freshness, staging and other previously problematic areas.

All Python under `src/`, `tests/` and `scripts/` compiles successfully with `compileall`. I also ran the repository's own code-health analyzer and performed targeted pure-Python fault injection against transaction and migration code.

I could not execute the complete pytest suite because this execution environment lacks PyArrow, DuckDB, `datasus-dbc` and `dbfread`. Therefore I cannot independently reproduce whatever current “1,000+ passing” result was obtained in the Pegasus environment. That limitation matters, but several of the defects below are direct control-flow failures requiring no inference about runtime behavior; two of the durability failures I reproduced directly.

## A large amount really has been fixed

The earlier code should not be judged by the previous review anymore.

Warm cache hits are now settled before opening FTP connections. `fetch_one()` received the same repair. Freshness metadata is persisted, `refresh="remote"` exists, interrupted downloads are resumable, stale fallback is explicit rather than accidental, and the partially-warm scheduler now has a separate terminal counter instead of counting pre-resolved hits against network misses.

DBC decoding is path based, and requested-column projection is pushed into DBF construction rather than applied only after building all Arrow columns. Large eager `fetch()` calls have a preflight limit. Default `fetch()` refuses partial answers. `FetchReport` has considerably better network/cache accounting.

`load()` now preserves the partition `year` as an internal semantic dependency when projected columns are requested, renders separately by family and vintage, and removes the hidden year afterward. That repairs the previous projected-`load()` vintage bug. `render_groups.py` is also a real improvement: some semantic policy is finally shared rather than duplicated.

The lake writer no longer collects an entire partition before opening `ParquetWriter`. Scanner schemas now use projected schemas. Eager exports use staging. Reference tables are system-scoped, scoped rebuilding occurs at `codelist/system` depth rather than deleting sibling systems, and `load_reference()` exposes `system=`.

Decoder timeout handling has moved in the correct architectural direction: interactive retrieval can use persistent decoder subprocesses rather than pretending an abandoned Python thread has been cancelled. The huge `.duck` file is no longer loaded into a Python `bytes` object merely to stage another copy.

Catalog migration now understands table-level composite primary keys, UNIQUE constraints and foreign keys rather than only columns. Whole-tree staging has unique transaction names and rollback. Public API consistency around `root=`, `settings=`, integer years, `path` versus `out`, and several exception classes has improved considerably.

The semantic work has improved too. The latest project measurements report actual live fetches for SINASC, SIM, SIH, SIA and SINAN in which municipality values were inspected and corrected rather than merely counted as “labelled”; the project records 128 municipality columns explicitly bound to `BR_MUNICIPALFA`, 12 to `BR_MUNICGESTOR`, and none left on known roll-ups/per-UF lists. 

So this is not a failed remediation effort. A great deal of the old engineering debt has been removed.

## Release blocker: projected `fetch()` has reintroduced the historical-vintage bug

This is the clearest current P0.

`_read_families()` correctly retains `_source_path` because `fetch()` needs it to know which physical source, family, year and competence produced each row.

But later, in `retrieve.fetch()`, the user projection is applied **before semantic grouping**:

```python
if columns:
    ...
    keep = [c for c in table.column_names if c in set(columns)]
    table = table.select(keep)
```

Unless the caller explicitly asked for `_source_path`, that deletes it.

Immediately afterward `fetch()` calls:

```python
split_by_source(
    table,
    fetch_report.source_facts,
    fallback_year=min(want_years) if want_years else None,
)
```

And `split_by_source()` explicitly does:

```python
if "_source_path" not in table.column_names or not source_facts:
    return [(table, None, fallback_year, None)]
```

Therefore a very ordinary request such as:

```python
fetch(
    "SIH-RD",
    years=[1995, 2024],
    columns=["DIAG_PRINC"],
)
```

loses the information needed to distinguish 1995 rows from 2024 rows **before labels are rendered**.

It then falls back to the earliest requested year and `family_id=None`.

That is effectively the old P0 vintage defect again, but only through the projected `fetch()` path.

The new projected-vintage regression tests cover `load()`. They do not cover projected multi-vintage `fetch()`.

This is exactly the kind of entry-point divergence the shared rendering work was supposed to eliminate.

The repair is straightforward conceptually: `_source_path` must be treated like `load()` treats `year`—a hidden internal dependency retained through rendering and removed only after semantic resolution if the user did not request provenance.

Until that is fixed, I would not trust a multi-year projected `fetch(labels=True)`.

## Release blocker: archive provenance does not use one identity

There are currently **three incompatible ideas of what identifies an archive source**.

Normal `DecodedTable.source_id` uses:

```python
physical_path!member
```

The process-isolated `_RemoteTable.source_id` uses:

```python
physical_path#member
```

But `_select_files()` stores semantic facts under only:

```python
physical_path
```

with no member at all.

Normalization writes:

```python
_source_path = table.source_id
```

Therefore an archive-member row can carry something like:

```text
/dissemin/.../acac0202.exe!ACAC0202.DBF
```

while `FetchReport.source_facts` contains only:

```text
/dissemin/.../acac0202.exe
```

`split_by_source()` cannot find the row's facts.

That loses the member's family/year/competence semantic context and causes fallback rendering.

This is particularly serious because the project correctly went to considerable effort to establish that one APAC LHA SFX archive can contain **seven different logical datasets and seven schemas**. Archive member identity is supposed to be first-class, not decorative.

There needs to be one function—something like `logical_source_id(path, member)`—used by selection, normalization, isolated decoding, ordinary decoding, reporting, catalog provenance and render grouping.

Until then, archive-backed data do not have reliable semantic provenance through `fetch()`.

## Release blocker: `scan(..., on_missing_column="null_fill")` is not actually null-filling the lazy stream

This is another old invariant that is correctly implemented for eager `load()` but incompletely implemented by the newer lazy API.

When one generation lacks a requested column, current `scan()` handles `"null_fill"` by doing:

```python
scanner = cat.lake.scanner(
    ...
    columns=None,
)
```

That means:

> read every physical column from the generation.

It does not mean:

> emit the caller's requested schema with the missing field represented by nulls.

`LakeScan.iter_batches()` then simply does:

```python
yield from scanner.to_batches()
```

without conforming those batches to the requested schema.

Consequently a lazy scan across schema generations can yield radically different schemas. A generation possessing the requested field can produce the narrow projected schema, while a generation lacking it produces its **entire physical schema** and still does not contain the requested null column.

`LakeScan.to_table()` partly disguises this because permissive concatenation can reconcile schemas after materialization. But the point of `scan()` is that callers consume individual batches.

It also contaminates:

```python
export(..., stream=True)
```

because streaming export builds its union schema from `scan_result.schemas`. A two-column request can therefore expand toward an entire physical schema simply because one generation did not have one of the requested fields.

The current parity test checks row counts. It doesn't assert identical schemas or null values.

This needs an explicit requested-output schema and per-batch conformance. Missing fields must be generated as Arrow null arrays; unrequested physical fields must never reappear.

## Release blocker: the shipped label pack is still not vintage-capable

The **code that builds new label packs has now been corrected** to incorporate validity windows.

The **actual `labels.parquet` shipped in this ZIP has not been rebuilt**.

The repository's own test says explicitly:

> “The artifact currently shipped has no window columns.”

I independently inspected the packaged Parquet metadata strings as far as this environment permits; `codelist` and `code_lo` are present, while `valid_from`/`valid_to` are absent.

The fallback logic knows this. But the chosen default is:

```text
historical_labels = "current"
```

because refusing every unwindowed mapping would leave much of a fresh installation unlabelled.

Thus on a fresh install, a historical request can still receive current/unversioned labels. The decision is recorded internally as `unwindowed-pack`, but ordinary:

```python
fetch(...)
load(...)
```

returns a table, not the rendering report. Unless the caller explicitly requests a report or strict semantics, that warning is not materially visible.

This is not merely theoretical. The project's own measurements establish why codelist windows exist: the same codelist can legitimately contain different mappings or wording in different eras. 

The appropriate final fix is not more fallback logic. **Regenerate the distributed `labels.parquet` using the current builder and full semantic catalog before release.**

Until that happens, the fresh-install path does not satisfy the package's central vintage-correctness promise.

There is also an API inconsistency: `fetch()` exposes `historical_labels=`, but `load()` does not.

## Decoder process isolation fixes one problem but introduces a protocol-recovery defect

Moving decoding into killable subprocesses was the correct solution to the old fake-timeout problem.

The current worker protocol is not robust after errors.

`DecoderPool.decode()` borrows a worker and always returns it to `_free` in `finally`.

`_read_reply()` reads the first frame. If it says:

```json
{"ok": false, ...}
```

it immediately raises `IsolatedDecodeError`.

But the worker protocol sends a zero-length reply terminator after that error frame.

Because the parent raised before consuming it, that terminator remains unread in the worker pipe.

The same worker is returned to the pool.

Its next job can therefore read the previous job's terminator as the new response header.

A failed decode can poison a persistent worker for the next request.

There is a second protocol problem. `_worker._run_job()` sends the `"ok": true` header **before it iterates lazy batches**. If iteration subsequently throws, the outer worker loop sends an `"ok": false` JSON frame into a stream the parent is currently interpreting as Arrow IPC data.

This protocol needs the rule:

> Any exception or malformed/incomplete response makes that worker disposable.

Kill it and replace it instead of returning it to the pool.

A regression test needs to exercise **error → same-pool next successful decode**, not merely successful-worker reuse.

## Process isolation is also much less streaming than its documentation says

The worker documentation says:

> neither side ever holds the whole decoded table.

The parent does:

```python
batches: list[pa.RecordBatch] = []
...
batches.extend(stream)
```

for every table and returns `_RemoteOutcome` only after the whole reply has been received.

So the entire decoded source can be resident in the parent process.

The wire protocol is batch-framed, but the API above it materializes the frames.

That is an implementation/documentation mismatch and a potentially important memory problem for large sources.

## DuckDB remains a serious I/O hotspot

The earlier catastrophic:

```text
12 GB file → read_bytes() → temporary 12 GB copy
```

path is fixed.

But `read_duckdb()` still does more work than the API asks for.

It first enumerates every table in the database. It DESCRIBEs and COUNTs each one. Then every table's iterator executes:

```sql
SELECT * FROM schema.table
```

No requested `member` is passed into `read_duckdb()`. No requested columns are projected into the SQL.

Through process isolation, the worker therefore opens the physical DuckDB source and can stream **every table and every column** over IPC.

Only later, back in the parent, `_decode_one()` decides:

> this was not the requested logical member; discard it.

For a source that the project itself documents as approximately 12 GB, this is potentially orders of magnitude too much I/O.

The worker job must contain the desired member/table and projected columns, and `read_duckdb()` needs to issue something equivalent to:

```sql
SELECT requested_columns
FROM requested_schema.requested_table
```

The exact same principle applies to multi-member archives.

## Physical-source decoding is not single-flight

The current fetch decode cache is keyed by digest, which is sensible, but it is not a true single-flight cache.

Threads acquire the lock to ask whether a digest has already been decoded, release the lock while performing the expensive decode, and then `setdefault()` the result afterward.

If several logical records point to the same physical archive, several workers can simultaneously see “not cached” and all decode the same physical source.

The eventual cache is deduplicated.

The **work isn't**.

The appropriate structure is:

```text
digest → Future[DecodeOutcome]
```

rather than:

```text
digest → DecodeOutcome
```

so the first requester owns the decode and every concurrent requester waits on the same future.

This is especially valuable now that one archive or DuckDB file can represent many logical dataset members.

## Decoder cancellation is not uniformly applied across the pipeline

Interactive `fetch()` now has process isolation.

`profile()` does not.

`Pipeline._profile_one_inner()` still performs:

```python
self.blobs.read(digest)
```

followed by:

```python
registry.open_bytes(...)
```

inside the old `run_with_timeout()` thread watchdog.

That recreates two old problems: the entire physical source is copied into Python memory, and a timed-out decoder thread continues executing because Python cannot kill it.

`Builder._materialise_partition()` also directly invokes `registry.open_path()` without process isolation or an equivalent killable deadline.

Therefore “decoders are isolated and cancellable” is not yet a pipeline invariant. It is an interactive-fetch feature.

A shared decoding service should serve fetch, profile and build.

## I reproduced a real scoped transaction rollback failure

`staged_tree()` is considerably better than before, and whole-tree replacement has proper rollback.

The scoped merge has one precise failure boundary that still violates its own guarantee.

It does:

```python
if destination.exists():
    destination.rename(backup)

unit.rename(destination)
moved.append((destination, backup))
```

Suppose moving the old destination to the backup succeeds, but installing `unit` as the destination fails.

The `(destination, backup)` pair has **not yet been appended to `moved`**.

The exception handler therefore knows nothing about the subtree it just moved away.

I fault-injected exactly that failure using the current implementation.

Result:

```text
destination exists: False
backup exists:      True
```

The old subtree had disappeared from its canonical location and was stranded under `.__old__...`.

That directly contradicts the staging module's stated guarantee that the old artifact remains intact after failure.

The fix is small: once the old destination has been moved, the rollback record must exist **before** installation is attempted, or that individual install must have its own try/restore block.

## I also reproduced a concurrent `staged_file()` collision

`staged_tree()` now gets a unique transaction token.

`staged_file()` still always creates:

```text
.<target>.staging
```

Two simultaneous writers to one target therefore receive the same temporary path.

I reproduced this with nested writers.

Both contexts got the same staging file. The second writer wrote `SECOND`. The first writer subsequently published those bytes under the target name. When the second context exited, its staging file was already gone and it raised an error.

So `staged_file()` is not cross-process or even cross-context safe.

This primitive backs lake partition writes and ordinary exports.

It needs the same per-transaction uniqueness already introduced for `staged_tree()`, with staging kept in the target directory so final `os.replace()` remains atomic.

`_write_streaming()` independently uses another deterministic `<target>.part` filename and has the same collision class.

## Lake partition replacement is much safer, but still not an atomic partition transaction

The catastrophic old “delete partition then write new file” defect is gone.

There remains a smaller but real consistency window.

The new file is staged and replaces `part-00000.parquet`. Then stale sibling parts are removed and old catalog records are deleted. Then the new catalog record is inserted.

Because `pyarrow.dataset` discovers files from the filesystem rather than the catalog, there are moments in which the new part and stale old parts can coexist and be read together.

There is also a crash window after catalog rows are removed but before the new one is inserted.

A true partition transaction should stage an entire partition directory/manifest and swap the partition boundary, then reconcile catalog metadata transactionally.

This is no longer the most urgent defect, but I would not describe current partition replacement as fully atomic.

## Catalog migration constraint checking is still asymmetric, and I reproduced it

The new migration parser is a real improvement.

But `_structural_mismatches()` effectively says:

```python
if want_pk and have_pk and want_pk != have_pk:
    problem

if want_unique and have_unique != want_unique:
    problem

if want_fk and have_fk != want_fk:
    problem
```

That catches a constraint the shipped schema wants but the installed catalog has differently.

It does **not** catch an installed constraint that the shipped schema no longer declares.

I created small SQLite databases and tested the current comparator.

An extra actual UNIQUE constraint: accepted.

An extra actual foreign key: accepted.

An extra actual primary key: accepted.

Thus “installed schema equals shipped schema” is still not what the migration checker proves.

The comparison needs to be symmetric after normalizing SQLite's implicit/index artifacts.

## Incremental-build invalidation has a weak point around municipality data

`plan_fingerprint()` includes:

```python
municipalities=<index size>
```

not a digest of the municipality mapping.

That means a correction that changes municipality mappings while preserving the number of entries leaves the fingerprint unchanged.

The build system can then decide an old normalized partition is still current even though rebuilding it would produce different municipality-derived values.

This matters precisely because municipality semantics have undergone extensive corrections recently.

`TRANSFORM_VERSION = "1"` can compensate only if a developer remembers to bump it whenever transformation semantics change.

A deterministic digest of the actual `MunicipalityIndex` content should be included in the plan fingerprint.

## Not all derived-data writers use the improved durability model

`Builder.population()` still writes final Parquet filenames directly.

`Builder.demas()` still writes:

```text
part-00000.parquet
```

directly.

An interrupted population rebuild can therefore leave a mixture of prior and current files. A failed or empty DEMAS refresh can leave the previous dataset in place looking current.

This is exactly the category of problem `staged_tree()` and `staged_file()` were introduced to eliminate.

The policy has not reached every writer.

## Archive quotas are only partially enforced

The archive subsystem now has explicit limits on member count, total uncompressed size and expansion ratio.

Good.

Those checks are applied to ZIP and external RAR/7z handling.

LHA, TAR and gzip do not go through equivalent quota checks before expansion.

For gzip in particular:

```python
gzip.decompress(self.data)
```

can still create a very large allocation.

For LHA, original member sizes are available and should be checked before decoding.

This is a resource-safety gap rather than an epidemiological-correctness bug, but there is no reason to leave the policy container-specific.

## Acquisition diagnostics can be mistaken for source failures

`FetchStats.errors` mixes fundamentally different things:

```text
actual path fetch failure
<connect> worker connection diagnostic
<stall> batch diagnostic
<workers> shutdown diagnostic
```

`retrieve._acquire()` then copies **every one** into `report.acquisition_failures`.

`FetchReport.is_complete` treats any acquisition failure as an incomplete answer.

Therefore one worker can fail to establish an FTP connection, other workers can successfully fetch every requested source, yet the completed request is subsequently treated as partial because `<connect>` exists in `errors`.

This is a safe false negative—it raises rather than returning wrong data—but it is a reliability defect.

Worker/batch diagnostics need to be separated from unresolved requested paths.

## Cross-system codelist borrowing remains too permissive

`read_reference_table(..., system=...)` first tries the requested system, which correctly fixed the earlier catastrophic cross-system merge.

If that system has no copy, however, the code intentionally falls back to another system's table:

> “a borrowed table is better than none.”

It records the borrowing in `RenderReport`.

`strict_labels=True` rejects vintage fallback, but it does not reject this borrowed-system case.

And ordinary fetch/load calls do not expose the report unless requested.

Given that one of the project's earlier measured defects was precisely that thirteen systems' `SEXO.CNV` tables can disagree, this default is too optimistic.

A foreign-system mapping should be used only if the codelist has been explicitly established as system-independent, or behind something like:

```python
allow_borrowed_labels=True
```

An unlabelled code is much easier to detect than a plausible label imported from the wrong information system.

## Month-level semantic vintages still cannot be represented by the lake

The reference layer supports `competencia=AAAAMM`, which is correct: a classification can change in July rather than January.

Raw `fetch()` computes competence from source-file dates.

The built lake partitions by year. `split_by_year_column()` explicitly says month-level competence is unavailable there and passes `None`.

Therefore `load()` cannot in general reproduce month-exact semantic rendering if a codelist has two validity windows within the same year.

If month-level validity is part of the semantic contract, competence must survive into the lake as an internal column or partition key.

## The generic codelist-selection problem remains open

The municipality catastrophe was fixed primarily through **explicit curation**, not by making the generic ranking algorithm infallible.

That distinction is important.

Current `view.py` still uses:

```python
_MAX_CANDIDATES = 12
```

A `.DEF` can bind a field to more than a hundred tables. `_choose_binding()` only loads and measures the first twelve after the preliminary ranking.

The project's own postmortem measured municipality examples where the correct `BR_MUNICIPALFA` table ranked 118th or 123rd. It was never even considered. The specific municipality fields are now curated around this problem, but the mechanism remains for other ambiguous fields. 

`RESUME` explicitly acknowledges this as still open: a correct table ranked thirteenth or later is never loaded or weighed. 

This is more than an optimization problem because the output can be a plausible label from the wrong aggregation.

For fields with large ambiguous binding sets, the safe behavior should be to require an explicit semantic declaration or refuse to choose if the correct candidate cannot be established—not to let an arbitrary cost cap become an epistemic decision.

## The substantive semantic layer is still not “finished,” by the project's own account

This is distinct from software defects.

The current handoff explicitly says that every catalogued column has a description, but that unresolved work remains around columns that do not decode, prose-quality debt in older curation, and—most importantly—independent review of inferred descriptions. 

I counted the current curation files directly. They contain **4,534 entries, of which 1,801 are marked `source: inferred`**.

That means roughly 40% of this particular curation corpus is explicitly inferential rather than first-party documented.

There are also still unresolved substantive questions such as the Ministry denominator series, genuinely ambiguous filename dates, range rules without a known universe, categorical fields without mappings, and fields for which TabNet names only aggregation axes rather than the raw variable. 

That is not a failure of the architecture. Recording uncertainty rather than guessing is one of the project's strongest decisions. But it means “all semantics resolved” would be an inaccurate release claim.

## Test quality is improved but still insufficient for the guarantees the package claims

This may be the most important process lesson from this audit.

Some current regression tests are genuinely behavioral.

Others still inspect source text.

`test_review_closure.py`, for example, contains assertions that helper names such as `_by_vintage`, `_merge_reports`, or `axis_refusal` appear in source. `_by_vintage` and `_merge_reports` are now unreferenced private functions according to the repository's own `codehealth.py`, while the live code uses `render_groups`.

A token existing in a module therefore demonstrably no longer proves that the public API uses the corresponding policy.

The current missed bugs reflect that weakness. There is a projected-vintage test for `load()` but not `fetch()`. The scan null-fill parity test measures rows, not schema/value equivalence. Decoder isolation tests cover successful worker reuse but not error → worker reuse. Staging tests cover whole-tree swap failure but not the exact scoped-subtree failure I reproduced. Migration tests cover changed declared constraints but not constraints that exist only in the installed database.

The project itself reached the same conclusion after its municipality work: six output defects were invisible to the suite and visible in the first CSV because the tests were measuring process metadata rather than the string the researcher actually receives. 

The correct acceptance suite should drive one controlled fixture all the way through:

```text
fetch → rendered Arrow
load  → rendered Arrow
scan  → batches
export eager → file read back
export stream → file read back
```

and compare actual values, schemas, vintages and row coverage.

## There is still significant structural complexity

Running `scripts/codehealth.py` on the current snapshot reports one import cycle:

```text
_dictionary → api → retrieve → _dictionary
```

and four unused private helpers, including the obsolete `_by_vintage` and `_merge_reports`.

It reports nine modules over approximately 1,000 lines. `api.py` is 1,828 lines, `retrieve.py` 1,646, `cli.py` 1,819 and `view.py` 1,348.

`view._render_table()` has a measured branch complexity of 69 over 291 lines.

The public `fetch()` currently has **28 parameters**, `export()` 21 and `load()` 19.

This isn't merely an aesthetic complaint. The current defects map directly onto policy duplication:

```text
load preserves hidden year
fetch drops hidden source path

load null-fill is coherent
scan null-fill diverges

staged_tree gets unique transaction IDs
staged_file does not

fetch gets process isolation
profile/build do not
```

The next architectural step should therefore not be another pile of local fixes. There should be a shared retrieval plan carrying axes, generations, hidden semantic dependencies, projection and missing-column policy, and a shared decoding service carrying member selection, projection, deadlines and single-flight physical-source caching.

`render_groups.py` is a good beginning; the consolidation simply has not gone far enough yet.

## Documentation/artifact state is also drifting

The current repository simultaneously says:

```text
README:          601 tests
CONTRIBUTING:   1025 tests
Architecture:   1090 tests
latest FINDINGS: 1131 tests
```

Parametrization can explain differences between static test-function counts and pytest cases, but not four maintained prose claims.

This is especially ironic because `RESUME` explicitly says counts were removed from that file after duplicated state tables disagreed and that counts should have one canonical home. 

There is similar semantic-artifact drift. Current source curation contains 4,534 entries, while the bundled `datasus.sqlite` has 4,528 variables. The architecture's confidence prose also still refers to 4,298 curation entries and 1,799 inferred entries, while the current source contains 4,534 and 1,801 respectively.

These are not runtime defects, but for a project built around provenance and truthful state reporting, they should be cleaned up.

## Performance verdict

The main `fetch()` path is dramatically healthier than it was. I no longer expect a normal DBC-based, warm-cache, narrow state-year request to suffer the absurd unnecessary work of the first snapshot.

The remaining serious performance risks are concentrated elsewhere: multi-member physical sources, DuckDB, process IPC materialization, duplicated concurrent decoding, profile's full-blob reads, and build/profile decoder cancellation.

Rendering still has some whole-column Pythonization—for example `_check_width()` calls `to_pylist()` over the column, `_combine()` loops through pairs in Python, and multi-valued rendering is row-wise—but these are secondary compared with the physical-source issues above.

So the answer is no longer “`fetch()` is fundamentally a snail.” It is closer to:

> DBC-oriented `fetch()` has received a serious performance pass; the abstraction becomes inefficient again when one physical source contains multiple logical tables or when execution leaves the optimized interactive path.

## My acceptance verdict

I would **not merge a “defects closed / codebase sound” declaration yet**.

I count at least four current correctness/release blockers: projected `fetch()` loses vintage/family provenance; archive-member provenance cannot match `source_facts`; `scan(null_fill)` does not preserve the requested lazy schema; and the distributed label artifact cannot yet express historical windows while the default still labels from it.

Immediately behind those are several high-severity engineering defects: poisoned decoder workers after error frames, non-streaming parent IPC accumulation, duplicate concurrent decoding of one physical source, pathological DuckDB table/member projection, old unkillable/full-blob decoding still used by profiling, two independently reproducible staging failures, asymmetric migration constraint validation, incomplete incremental fingerprints, non-transactional population/DEMAS writers, incomplete archive quotas, acquisition diagnostics contaminating completeness, permissive cross-system codelist borrowing, and loss of month-level semantic vintage in the lake.

None of this erases the progress. The current codebase is **considerably more coherent, safer and faster** than either prior snapshot. Several difficult problems have been solved correctly rather than superficially. But the current state is best described as **advanced and substantially repaired, not closed**.

The next acceptance gate should be narrow and adversarial rather than another broad feature wave: repair the four correctness blockers; repair process/staging failure recovery; push member/column selection into physical decoders; make decode isolation shared across retrieval/build/profile; regenerate the packaged label data; then run the real Pegasus environment against at least a projected multi-vintage DBC fetch, an equivalent built-lake load, a null-filled multi-generation scan and streaming export, an APAC multi-member LHA source, and a `.duck` source while asserting the actual returned values rather than report counters. Only after those same slices agree at the output boundary would I regard “sound” as a defensible claim.
