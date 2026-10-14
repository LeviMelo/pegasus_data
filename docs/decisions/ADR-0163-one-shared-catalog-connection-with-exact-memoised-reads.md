# ADR-0163: one shared read-only catalog connection per process, reads remembered until `data_version` moves

**Date:** 2026-10-14. **Status:** accepted.

**Context.** A query opened four or five fresh connections to the catalog (planner, executor, `Catalog`, the presentation,
the dimensions), each with a cold page cache, so nothing it worked out about the catalog could outlive the call. That was
0.65 s of every query: a dataset's file axes (a scan of its `file_facts`, 129-245 ms), its families, its publications
(18,991 rows loaded for SIH-RD to look at ten years), its lake partitions, its schema census. A cache keyed on the dataset
and the year alone would serve stale lake coverage after a build.

**Decision.** `CatalogStore.shared(path)` is the process's one read-only connection to a catalog file (replaced when the
file is replaced; `close()` releases a use, it does not close the connection). `CatalogStore.memo(key, compute)` remembers
a result on a read-only store until SQLite's `PRAGMA data_version` moves, which it does whenever ANOTHER connection (another
process included) commits: exact, no mtime heuristics. A writable store never memoises (its own uncommitted writes are not
a snapshot). `Catalog` and `plan`/`query` read through the shared store; what is remembered is catalog state only: a
dataset's families, publications and lake partitions, the schema census, the file axes (`DatasetAxes`), the lake-coverage
decision, the bindings of a family. What is not catalog state is looked at every call: that the lake's partition files are
on disk, that a cached blob is.

**Consequences.** A query's fixed cost fell from 0.2-1.3 s to 0.07-0.1 s warm (docs/evaluation/2026-10-14-query-fixed-cost.md).
The cached values are shared: callers treat them as read-only (`_resolve_family` hands out copies). A test or process that
deletes a catalog file calls `catalog.store.close_shared()` first.
