# Versions as deltas (2026-11-22)

Scenario `scratch/run_all.sh` and `scratch/r1.py` (not in the repository; log `data/probes/live/2026-11-22-versions-as-deltas.log`),
on a scratch home: the real catalog copied, no lake, the real kept downloads of RDAC25*, DENGBR26.dbc and CHIKBR26.dbc.
DATASUS's republications were replayed by setting each path's listing and latest fetch to a version. Branch
`claude/versions-as-deltas-2bb44d`, code of ADR-0234 (uncommitted working tree on 7e416265 when run).

- **(b) SIH-RD Acre 2025.** Built from the versions of 2026-10-05, then September to December 2025 replaced by the
  republication of 2026-10-16: 4 files decoded, 6 carried, 4 versions kept. The other 8 sources' 41,821 rows were
  identical in every column, `_ingested_at` included; 52,796 rows, as the real lake's partition.
- **(a) `query(as_of=)` from deltas against the blob read**, every column but `_ingested_at`, rows by source and `_row`:

| File | Version | Rows | Removed / added | Delta | Blob | Equal |
|---|---|---|---|---|---|---|
| RDAC2509-2512 | 2026-09-07 | 19,759 (61,580 with the year) | 0 / 0 | 53 KB | 1.41 MB | yes |
| DENGBR26 | 2026-09-22 (two deltas back) | 460,356 | 14,945 / 19,912 | 895 KB | 22.6 MB | yes |
| DENGBR26 | 2026-09-29 | 465,323 | 32,590 / 45,671 | 1.54 MB | 23.4 MB | yes |
| CHIKBR26 | 2026-09-22 | 130,003 | 1,676 / 3,503 | 167 KB | 5.65 MB | yes |

  The SIH republication changed no record, only the order: 317-382 runs a month. DATASUS reorders dengue too (231,311
  runs for 445,411 kept rows), so runs are stored delta-encoded, `(old_start, offset, length)`: 2.3 times smaller.
- **(c) Bytes.** 2.66 MB of deltas in place of 53.1 MB of blobs (5.0%). `prune` then released all 7 blobs of these
  files (79.9 MB with the current versions), and every version was read back from the lake.
- **R1.** `query("SIH.RD", "2024", "AC")` with nothing built: read from 12 downloads (4.1 MB, 7.4 s), landed (1
  partition, 57,272 rows) and released; the second read came from the lake in 0.5 s with 0 bytes downloaded, every
  shared column equal (the lake read adds the partition columns `uf`, `schema_signature`). Same for 2023 (59,835 rows).
- **R2, CNES-ST Acre.** December 2023 was fetched, landed and released (62 KB); the second read came from the lake in
  0.2 s. November 2023 then landed into the same partition, carrying December without a download (2,734 rows). Before
  coverage was narrowed to the months asked, a one-month partition never covered its year and every read downloaded
  again. A CNES field reads its December register through the same `query`; it was not run here (a national read).
- **Raw-text renders.** No build partition of the real home carries `pegasus.raw_render` (0 files; renders are on
  intake units only). A delta's rows are still taken with their text whole and without render metadata.
- **Snapshot transport.** The 2026-10-05 run (log `pegasus_core_snapshot.log` in the user folder, exit 1) judged the
  data channel down from one slow LIST and left 92 files waiting with "mirror holds another state": SINAN PRELIM COLE,
  COQU, DIFT, HIVC, HIVG, IEXO, SIFA, SIFC, SIFG, TETA, TETN, VARC and CNES ST 2508 of every state. They were re-run
  on the scratch home with a declaration naming only them (`PEGASUS_CURATION_DIR`) and the listing forced to be judged
  slow (`scratch/snap92.py`, log `data/probes/live/2026-11-22-snapshot-92.log`). Observed by stat, all 92 were
  transferred from DATASUS (120 MiB, 0 failed, 0 from the mirror), built into 91 partitions (2,166,088 rows) and 91
  downloads released. The one kept is COLEBR25 (2,923 bytes): it decodes to no rows, so no partition holds it.
  Re-run on master's form of the fix (49c69386, here 20b3023f) with those versions forgotten: 91 transferred from
  DATASUS and 1 adopted from its kept download, 0 failed, none from the mirror; the partitions were current and
  reused, and the 91 downloads released again.
- **(d) The real home migrated** (01:54-02:19 local, branch head 81ad2362; `prune --keep-versions`; log
  `data/probes/live/2026-11-22-migration.log`, census `...-migration-blobs-{before,after}.txt`, `scratch/left.py`).
  The catalog was backed up first (`_catalog/catalog.before-versions-2026-11-22.sqlite`).
  - Two attempts stopped early and wrote nothing but digests. Attempt 1 crashed: a partition file's row groups carried
    differing dictionaries. The fix also covers the 8,670 intake units, which keep no digest and are released by path.
    Attempt 2 was stopped to add the handling of files a reader holds open: a redundant partition is moved aside whole,
    and a locked one or a locked blob is left and counted.
  - 933 versioned paths with no partition were landed: 464 partitions, 42.4 M rows, 8 changed files downloaded.
  - 225 downloads of replaced versions became deltas (30.9 MB); 1,577 downloads were of versions the lake holds.
  - `prune` released 1,079 downloads (2.80 GB) and dropped 114 partitions as redundant (15.6 M rows, 486 MB).
    Among them were 108 preliminary state files of SIM and SINASC landed in this run, whose records the national
    file holds. Two of those were the bases of deltas (Roraima's DORR2026 and DNRR2026), so their two versions became
    unreadable. `prune` now keeps a partition a delta stands on, and the two were landed again.
  - Read back, all 225 kept versions gave the row counts recorded when they were kept.
  - Blobs went from 11,511 (21.95 GB, 823 snapshot versions, 1.74 GB) to 8,815 (15.92 GB, 116 snapshot versions, 0.41 GB).
    1,617 of the 2,696 blobs that went were released by another process in the same window: CNES PF, LT, EQ, HB and ST
    partitions written 01:30-02:00 by queries landing what they downloaded (R2 in use on the real home).
  - What stays, by reason (15.92 GB):

| Kept because | Size | Blobs |
|---|---|---|
| no partition holds the path: files only a query or an extract read (SIA 10.04 GB, CNES 0.75, IBGE 0.19, SIH 0.13, and smaller systems) | 11.2 GB | 8,091 |
| no partition holds the path: SIM, SINASC and SINAN files, among them the preliminary state files beside their national file (112 snapshot versions) | 3.6 GB | 411 |
| intake sources (Dados Abertos), held by path, not listed as such by their units | 0.88 GB | 285 |
| no family reads it (kits, documents, archive members) | 0.28 GB | 23 |
| held by the lake, released at the next `prune` (the two landed again with release off) | <0.01 GB | 3 |
| no fetch row | <0.01 GB | 2 |

