## ADR-0233: A version is a delta against its successor, and the lake is the only stored form of a publication

**Date:** 2026-11-22. **Status:** active. **Amends** ADR-0141 (versions kept as blobs, `as_of` read from them),
ADR-0208 (a download no partition holds stays) and ADR-0209 (a republished month needs its whole partition rebuilt).
Plan `docs/plans/raw-downloads.md` (R1, R2, R5; R3 by `prune --keep-versions`).

**Context.**
- DATASUS rewrites preliminary and current-year files under the same path (ADR-0141), so a refetch reproduces the
  current version only, and the home kept every other version as a raw download: 22.3 GB of blobs on 2026-11-22, 1.74
  GB of them 823 snapshot versions, the rest files only a query had read (SIA 10.2 GB, CNES 3.9 GB).
- `prune` judged a download by its path: a partition built from the new version of a file released the old version's
  blob unless a snapshot named it. Superseded downloads were lost that way.
- A republished month needed its whole partition decoded again: the eleven other months of an SIH-RD state-year
  were fetched again after ADR-0208 had released them.

**Decision.**
1. **A version is a delta against its successor** (`persist/versions.py`). When a build replaces a source's version in
   a partition, it keeps the old one, before the swap, as:
   - the old rows the new version does not hold, whole, in the lake's encoding (`<id>.removed.parquet`);
   - the rows both hold, as runs of `_row`, `(old_start, offset, length)`, delta-encoded (`<id>.kept.parquet`).

   Rows are matched by record identity: the content key over the record's own fields (`record_key_sql`), exact
   duplicates numbered in file order. The files live under `<lake>/versions/<system>/<family>/<source>/`. The row is
   in `lake_versions`: path, digest, listed size and time, successor digest, rows removed and added, bytes.
2. **A partition takes one source's new version without the others' files.** A source the partition holds at the
   version the server lists is carried from it as stored, not fetched or decoded. That holds only when the partition
   was built by the current plan: its fingerprint is the one this plan gives the sources it holds. Otherwise every
   source is decoded, which a changed plan needs anyway. `build(paths=...)` grows a partition by the files named and
   keeps the ones it holds. A source whose new version will not decode keeps its old rows. `lake_partitions.
   source_digests` records the version of each source.
3. **`query(as_of=)` reads the lake.** A version is the lake's rows of its source, with each delta applied, following
   successors from the lake's version back to the one asked. It needs no blob and no network. The versions of a path
   are the snapshot's observations, the deltas and the lake's current one, each at its listed server time. Under
   `as_of`, a representation with no version by then gives way to another of the same publication.
4. **Downloads are landed, then released.**
   - `snapshot` builds each version it fetches into the lake (`build.land`) and releases the download.
   - A query that read downloaded files lands them after the read (R1). CNES's fields read their registers through
     `query`, so they land the same way (R2).
   - `prune` releases a blob when, for every path it was fetched for, a verified partition holds that path at the
     blob's version, or a delta keeps it. `prune --keep-versions` first decodes every kept download of a version the
     lake does not hold into a delta (`build.keep_downloaded_versions`).

**Rejected.**
- **The keys (with counts) of the rows the successor added**, the first design. It reproduces the version's records
  but not their `_row` or order. `_row` with `_blob_sha256` is a record's identity in its publication (ADR-0107).
  Reading also had to hash every current row. Runs give both, and a chain of deltas stays exact because each version
  is rebuilt with its own `_row`.
- **Runs dictionary-encoded, `(old_start, new_start, length)`**: 2.3 times larger on dengue 2026. DATASUS reorders a
  rewritten file, and consecutive runs have near offsets.
- **Carrying a source across a plan change**: it would mix two normalisations in one partition under a fingerprint
  claiming one.

**Evidence.** Evaluation 2026-11-22-versions-as-deltas, on a scratch home with real files:
- SIH-RD Acre 2025: built from the versions of 2026-10-05, then September to December republished. Four months were
  decoded and six carried; the other sources' 41,821 rows were identical in every column.
- `query(as_of=)` from deltas equalled the blob-based read row for row on 5 versions of 3 files: SIH-RD Acre
  (61,580 rows), dengue 2026 (a two-delta chain, 460,356 and 465,323 rows) and chikungunya 2026 (130,003 rows).
- The deltas took 2.66 MB in place of 53.1 MB of blobs (5%).

**Consequences.**
- A version overwritten twice between two runs is still lost (ADR-0141's limit).
- A query that downloads files decodes them twice: once to answer, once to land.
- An archive of several members keeps its download.
- A delta's removed rows keep the normalisation of their build. A version read after a plan change has its old
  values for those rows, and the plan's for the rows it shares with its successor.
