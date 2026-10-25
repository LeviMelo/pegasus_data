# Disk: downloads beside their Parquet, and the homes left after adoption (2026-10-24)

**Why.** The machine reached 6.9 GB free of 931 GB. The author asked why raw DBC files are kept at all, and asked for
every copy of pegasus data outside the one home to be moved into it, deduplicated, and never made again (ADR-0208).

**Regime.** The measurements below count each file once (by inode) and never follow a junction. Agents' scratch homes
link `lake/`, `registries/` and `blobs/` to the one home, and a walk that follows them counted the lake four times
(316 GB). The code is branch `one-home-storage` off `pegasus-core-fixes` 5d69b6c.

## What the one home's downloads were

| blobs in `pegasus_core_data/blobs` | GB | files |
|---|---|---|
| latest version, a verified partition holds it | 13.64 | 4,285 |
| latest version, no partition holds it (read by queries) | 17.42 | 8,596 |
| snapshot version (ADR-0141) | 1.74 | 823 |
| superseded by a newer fetch of the path | 0.70 | 176 |

* SIH-RD makes 10.17 GB of the first row: the 23/10 download of the project in ADR-0200's context, since built.
* SIA-PA (6.85 GB, 594 files) and SIA-BI (3.45 GB, 114 files) make most of the second. They were fetched between
  2026-08-23 and 2026-10-13 and never built.
* `prune --dry-run` names the same 4,285 files and 13.64 GB.

## Homes outside the one home

* **Adopted and removed** with `adopt --apply --remove`: 23 homes, 15.37 GB. None held a blob or a registry file the
  one home lacks (`blobs moved` 0, `registry files moved` 0). They added 382 fetch rows (380 from the repository's home,
  2 from a scratch home).
  * `~/pegasus_linkage` 10.01 GB, 6.75 GB of it a derived lake;
  * `~/pegasus_live/home` 0.94 GB; `~/pegasus_fresh` 0.54 GB; `fresh2` and `fresh3` 0.23 GB each;
  * `pegasus_project/pegasus_data_home` 0.23 GB;
  * `%LOCALAPPDATA%\pegasus-data` 0.23 GB, which the desktop app's package virtualisation had placed under
    `Packages\Claude_…\LocalCache`;
  * two `C:\tmp\tmp.*` homes, seven `t_build_*`/`t_fetch_*` temp homes and eight homes in agents' scratch folders.
* **Without a catalog, deleted:** 6 homes, 0.16 GB.
  * 21 of their blobs were in no fetch history and absent from the one home: diagnostics of 14/10, which nothing can
    read.
* **The repository's home:** 4.31 GB of copies were deleted, after the build catalog was moved out:
  * 6 blobs held in the one home;
  * registries, 236 of them identical to the one home's and 32 differing (2 newer there, SIDRA metadata, by one byte);
  * a 0.47 GB derived lake;
  * three files of August.
* **Copies of the catalog in a scratch folder:** 8 files, 2.19 GB (backups and copies of 2026-10-23 and 24, and a seed).
  The latest backup was kept.
* **pytest:** three runs of test homes, 10.30 GB.

The label build catalog moved to `pegasus_core_data/_label_build/catalog.sqlite` by rename. It was checkpointed first.
It is 13.19 GB with 22,352,861 dictionary rows before and after, and `quick_check` is ok.

## The change, run

* **`adopt --remove` on a home linking `lake/` to another folder.** The link was removed and its target kept. Removing
  `C:\Users\Galaxy` or `pegasus_core_data\lake` was refused.
* **`build --system SIHSUS --uf AC --years 2025`**, two RD families, on the one home:
  * 1 partition was reused and 1 rewritten (52,796 rows);
  * `released`: 11 blobs and 4.0 MB were deleted, and 0 kept.
* **`query("SIH.RD", period="2025", geography="AC", rows={DIAG_PRINC: diabetes and dengue}, max_download=0)`** then
  read 1,361 records from the lake (`origin` lake) in 2.5 s. The nees-gt-ms extract of the same filter, made before,
  holds 1,361.
* **The native DBC goldens** with `PEGASUS_GOLDEN_HOME` set to the one home: 5 passed. Without it, the 3 that need a
  real file skip. The run left no `pytest-of-*` folder.

**Afterwards, at the author's word.**
* `prune` released 4,274 files, 13.64 GB. It kept 8,772: snapshot versions, downloads never built, and kits.
* `query("SIH.RD", period="2024", geography="AL", …, max_download=0)` then read 2,139 records from the lake in 12.6 s,
  equal to the nees-gt-ms extract.
