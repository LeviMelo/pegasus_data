# The catalog's lake partitions against the disk (2026-10-15)

**Check.** Every row of the shared root's `lake_partitions` (`C:/Users/Galaxy/pegasus_core_data`) was tested for its
Parquet file under `lake_dir`. Families checked: BNAFAR, CIH, CIHA, FA, Painel, SIASUS, SIES, SIM, SINAN, SINASC,
SISAGUA, SNGPC, SRAG and REGIAO.

**Result.**
- SIH-RD: 448 of 487 partitions are recorded and absent. Only SC, SE, SP and TO remain, about 1.8 GB.
- Every other family is whole, except one REGIAO row.

`lake_coverage` read the catalog alone and reported all 27 states for every SIH year. PegaSUS priced those years as
free, and its lanes, forbidden to download, failed. The reads that did run fetched 324 DBC files a national year again
on every new key (the suicide study in RS).

**Fix.** `lake_coverage` counts only the partitions whose file is on disk; SIH-RD now reads 3-4 states a year.

**Repair.** The lake is being rebuilt nationally for 2014-2023, with the downloads released (`build_lake(...,
release=True)`, log `../pegasus_project/data/probes/build_data.log`). `build_lake` already rebuilds a partition whose
Parquet is missing.
