## 2026-09-28 — The maintainer catalog refreshed from a full crawl: listing is cheap, and 5% of the tree had no family

**Question.** How current and complete is the maintainer catalog that the
shipped snapshot is built from, and what does it cost to bring it up to date?

**Regime.**
- Maintainer home `pegasus_data_home/`, backed up first to
  `data/backups/catalog-2026-09-28-before-full-crawl.sqlite`.
- Commands: `crawl`, `inventory`, `schemas`, `families`, logged in
  `data/logs/*-2026-09-28*.log`.
- Branch `redesign`, with ADR-0065 applied and the census fixes below.

**Before.** The catalog had been built from seven partial crawls (2026-08-23
and 08-30), totalling 185,278 files. `tree.parquet`, shipped in the wheel,
came from an earlier full crawl in another catalog and listed 207,251.

**The crawl.** 367 directories and **208,095 files in 32 s**, all carrying
size and mtime:
- 22,821 new, 4,353 changed, 180,921 unchanged;
- 4 gone (three SINAN preliminary files and one SIA file);
- 1 coverage gap (`/uploads`, access denied, as before).

Listing the whole tree is cheap. What is expensive is reading schemas.

**The inventory**, re-run after each grammar fix (ADR-0065), 15 s each:

| grammar | strata | SIASUS series | SIASUS strata |
|---|---|---|---|
| before the part fix | 3,156 | 1,013 | 1,223 |
| lettered parts (`PASP2301a`) | 2,826 | 273 | 483 |
| + numbered parts (`BISP2507_1`), + descriptive years (`SISCAN_CITO_COLO_2013`) | **2,569** | **16** | **226** |

**The census.**
- 520 strata awaited a schema. The census read 363 in 2 min 18 s from
  **2.1 MB** of ranged reads (0.27 s a stratum); 156 are not header-readable
  (archives, XML, DuckDB).
- The families stage then built 326 families, which put 200,682 of 207,874
  data files in a family.

**What was missing, and why.**
- 5,221 SIH files had no family. SIH-RD 2008, 2010, 2012 and 2014 are
  published twice: as `.dbc` under `200801_/Dados/`, and as `.xml`/`.csv`
  under `/SIHSUS/<year>/`.
- Both land in one (system, series, year) stratum, and two defects left the
  stratum sampling an `.xml` the census cannot read:
  1. `Stratum.sample_path` picked the smallest file of any format.
  2. `persist_strata` pinned the first sample with `COALESCE`, even one that
     never yielded a schema. And the census chose its own target with a
     separate "smallest file" query, beside the stratum's recorded sample.
- **Fixed:**
  - the sample prefers a header-readable representation;
  - an unsigned stratum takes the current best sample;
  - the census reads the recorded sample, one selection instead of two.
- **After:** 8 more schemas read, 329 families, **206,180 of 207,874** data
  files in a family. SIHSUS has 3 left.

**Still without a family (1,694).**
- SIASUS 1,458: mostly APAC self-extracting `.exe` archives from 2001–2007.
- IBGE 211.
- DADOS_ABERTOS 13: DuckDB and Parquet exports.
- A handful of singletons.

Their schemas need a decode, not a header read (OPEN_QUESTIONS).

**What it means for the design.** A fresh install could list the whole tree
in half a minute, but not learn its schemas. At 0.27 s a stratum, that costs
about twelve minutes for the whole tree and 5.6 minutes for SIA alone before
this fix. So what must ship is the *schema knowledge* (strata, signatures,
families), and the file list can be refreshed live. That is the seed catalog
of STATUS M1.
