# ADR-0172: a landed unit is replaced, never added to; an unfinished API unit is read again; an absent source is a gap, not an outage

**Date:** 2026-10-14. **Status:** accepted.

**Context.** A review of `intake.py` and `sources/` on 2026-10-14 (findings 8-11, 22, 23) found landings that could count a unit's
records twice, register records they had not checked, or cache a gap. A unit re-landed under another schema signature (a column
gains a `type:`, a file header changes) wrote a new family and left the old family's `part-<key>-*` files, catalog rows and place in
`lake_datasets.family_ids`; `_derive` and `query()` read every family, so the unit counted twice. `_land` deleted the unit's old
parts before the COPY and registered the new ones before `_land_unit` compared them with the file's line count, so a failed COPY
left catalog rows pointing at deleted files and a "4,007 of 2,844,261 rows lost" unit stayed queryable. An API unit that ended inside
its range (SIES grows monthly) was cached as complete by a fingerprint that does not include how much it held, so the pages the table
later gained inside that range were never read; an answer without the declared list was taken for the end of the data; the list of
filters BNAFAR could only page (`unstable`) was thrown away. Every HTTP error was retried as transient, so a month not yet published
cost 195 s and stopped the source.

**Decision.**
- **The unit is the landing's atom, and landing replaces it.** `_land` converts into a staging folder under `work/intake/`
  (never inside a family: readers glob every parquet there), counts the staged rows (`expect_rows` = the file's lines less the header,
  recomputed after the mixed-encoding retry), and only then swaps. The swap (`_commit`): remove the unit's sidecar; remove its parts in
  every family of (system, series), matched by exact name (`part-<key>-<n>.parquet`, so key `a` never takes key `a-b`); move the staged
  parts in; `_register` in one transaction deletes the unit's `lake_partitions` and `family_files` rows in every family, drops a family
  left with no partition, removes publications of years the unit no longer has, refreshes the touched families and recomputes
  `lake_datasets.family_ids`. Any failure before the swap leaves the previous records, catalog rows and sidecar as they were; a missing
  sidecar means "land again". Undated records (year 0) stay in the lake and in no publication; they are a listed partition since ADR-0174 (they had been in neither).
- **An API unit says whether it is final.** A partition unit (one state) is complete; an offset unit of `PIECE_PAGES` pages is complete
  when it read them all and its last page is full or another page follows. The sidecar records `complete` (a sidecar without it is
  read by its rows); an incomplete unit is read again on every run unless the origin declares `static: true`, and ends an offset read.
  The filters that could only be paged (`unstable`) are in the unit's stats and `build_source`'s report. An empty answer where the
  unit held rows is kept as an anomaly (`empty_answers`), not applied; a table that shrank leaves its tail units until rebuilt.
- **An answer is understood or it raises.** A page whose list key is present and empty ends a read; an answer without the key (or, in
  `page` style, without `pages_key`) raises naming the keys it has. `read_slice` raises when a declared, non-optional column is in no
  row, shares one case-insensitive reader with the bulk path, and does not cache an empty slice unless the declaration sets `cache_empty`.
- **Transport errors are classed.** Resets, timeouts, 408/425/429 and 5xx are retried; any other 4xx raises `SourceAbsent(url, status)`
  at once (a `ConnectionError`), which `build_source` records as `{"absent": status}` for the unit and continues, raising only when
  every unit is absent. A 416 is "complete" only when `Content-Range: bytes */N` gives the length held; resumption sends `If-Range` with
  the validator saved beside the `.part`, and a `.part` with none that is older than ten minutes is discarded. File sources download
  through `download` straight to their target (`fetch_url` is removed).

**Consequences.** Re-landing is idempotent and moves a unit between families without a trace; the staged parts are moved into the lake
(a rename on one volume, a copy when the work directory is on another). The first run after this change reads every old API sidecar by its
rows, so a source's last offset unit is read once more. A table that shrank or emptied keeps its tail until the source is rebuilt.
