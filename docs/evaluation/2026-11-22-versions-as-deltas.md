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
- **(d) The real home: every download landed or released** (2026-11-22, 01:54-11:23 local; logs under
  `data/probes/live/`: `2026-11-22-migration.log`, `-land-rest.log`, `-prune3.log`, `-land-dbc.log`,
  `-other-reps.txt`; blob censuses `-blobs-{before,after,final2}.txt`; reasons from `scratch/left2.py`, `left303.py`).

| | Downloads (blobs) | Snapshot versions kept as blobs | Partitions listed (bytes) | Deltas |
|---|---|---|---|---|
| before, 01:30 | 11,511 files, 21.95 GB | 823, 1.74 GB | 29.89 GB (re-encode evaluation of 2026-11-21) | 0 |
| after, 11:23 | 136 files, 0.66 GB | 14, 0.02 GB | 17,621 files, 39.50 GB, 3.06 billion rows | 258, 46 MB |

  - Steps, all on master code (81ad2362, then 1e4759b2 and e6ccf766):
    1. `prune --keep-versions` (01:54-02:19). The catalog was backed up first; the backup was later removed by
       another session's cleanup. 933 versioned paths landed, 225 versions became deltas, and 1,079 downloads
       (2.80 GB) were released.
    2. Every download no partition held was landed with the downloads it read released (`build.land`, smallest
       first, a batch only with 4 GB free). The 04:00 snapshot was let run alone, and the OS crash during it left no
       partial lake file or catalog row (checked: 0 rows point at missing files). 8,787 paths in 288 batches, then
       a pass over the snapshot's new versions (61 files, 22 kept as deltas): about 6,170 partitions written
       (1.01 billion rows; SIA-PA and SIA-BI most of them). Blobs went from 8,815 (15.92 GB) to 1,049 (2.83 GB).
    3. (The CNES registers had been landed by another session's queries the same night, R2 in use.)
    4. `prune --keep-versions`. It dropped 487 state partitions (43.1 M rows, 1.0 GB) whose every record the national
       reading holds (SIM, SINASC, RESP, SINAN preliminary state files), and released their downloads by that
       containment. It kept the 2 partitions deltas stand on, and released 659 downloads (1.37 GB).
    5. The Dados Abertos copies (CSV, JSON, XML) of final SINAN publications were released once the lake held the DBC.
       The DBCs of 204 such publications were downloaded first (0.72 GB) and landed (202 partitions, 16.0 M rows).
       254 copies (0.81 GB) went.
  - Failures: 3 corrupt LHA members in SIA APAC 2005 (ACPR0510, ACSP0502, ACSP0504), 2 in APAC 2001 (UDSP0103,
    UOSP0103) and 3 ESUSNOTIFICA DCCR files whose layout no family has. No file was locked. One run raised: `prune`'s
    delta-base list shadowed a parameter; fixed in e6ccf766, nothing lost.
  - What stays (0.66 GB), and why:

| Kept because | Size | Blobs |
|---|---|---|
| SIA APAC archives with a member not held (corrupt members above, or members of families not built) | 0.28 GB | 53 |
| no family reads it: kits and documentation (CNES 0.13, IBGE 0.08, SIA 0.07) | 0.28 GB | 29 |
| Dados Abertos copies of current-year publications, which DATASUS rewrites (released when the year is final) | 0.07 GB | 33 |
| other (a representation or national reading the build does not choose, no fetch row) | <0.01 GB | 17 |

  - The 4 SIM files `prune` had kept (0.02 GB) were a rule gap. DATASUS lists SIM's 2025 DOEXT, DOMAT, DOFET and
    DOINF byte-identical in `PRELIM/DOFET` and `CID10/DOFET`. The lake held the CID10 copy at the same digest, and
    `prune` required every path a blob was fetched for. A blob is now held when any plain path holds its bytes, and
    `read_version` reads the other path from that copy (`persist.versions.same_bytes`). Read so, all four equalled a
    decode of their own blob in every column (156,883, 1,238, 25,073 and 29,904 rows), and were released: 132 blobs,
    0.64 GB left.

