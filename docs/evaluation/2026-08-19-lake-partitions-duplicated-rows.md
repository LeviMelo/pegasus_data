## 2026-08-19 — lake_partitions duplicated rows rather than zeroing them

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

## 3d. Measured results that changed the design (2026-08-19)

### `lake_partitions` duplicated rows rather than zeroing them

`next_part_number` returned the count of parquet files already in the directory, so a rebuild after
a schema correction numbered itself *after its own stale output*: `part-00003` landed beside
`part-00000` and both stayed registered. `ds.dataset()` globs the directory rather than consulting
the catalog, so it read the union and returned **every row twice**. Pinned by a test at 10 rows
rebuilt into 20. Emptiness gets noticed; doubling gets published.
