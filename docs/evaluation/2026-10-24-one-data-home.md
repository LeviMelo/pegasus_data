# One data home: the strays adopted (2026-10-24)

**Why.** Another project, fetching SIH and SINAN through pegasus_data, reported 11.6 GB downloaded on 23/10 into the
repository's home (`pegasus_data/pegasus_data_home`). The per-user home already held most of those years. The question
is how much of this machine's pegasus data was held twice, and whether the one home recognises the downloads it
adopts, so they are not fetched a third time.

**Regime.** Working tree on `pegasus-core-fixes` after 16ff861: `pegasus_data.adopt`, the placement change and
`listing.same_instant` (ADR-0200). One home is `C:\Users\Galaxy\pegasus_core_data`. Its catalog was backed up before the
adoption (scratchpad `catalog_backup_2026-10-24_pre_adopt.sqlite`).

## The homes found

Found by searching `C:\Users\Galaxy` for `catalog.sqlite` and `pegasus_data_home`, depth 6, plus the system temp folder.

| home | size | blobs | fetch rows |
|---|---|---|---|
| `pegasus_core_data` (the one home) | 93 GB | 47,578 | 63,720 |
| `pegasus_data/pegasus_data_home` | 30 GB (catalog 13, blobs 11, registries 6.2) | 11,602 rows, 3,763 files | 12,014 |
| `pegasus_linkage` | 13 GB | 2,308 | 2,308 |
| `pegasus_fresh` / `fresh2` / `fresh3` | 1.8 GB / 0.2 / 0.2 | 941 / 0 / 1 | 961 / 0 / 1 |
| `pegasus_live/home` | 1.2 GB | 308 | 311 |
| `pegasus_project/pegasus_data_home` | 0.2 GB (a crawl listing) | 0 | 0 |
| temp `lp_freshhome`, `fh1`, `tmp…`, `t_build_*`, `t_fetch_*` | 18 MB | — | — |

## Adoption (`pegasus-data adopt OTHER --apply`)

| from | blobs moved | GB | already held | fetch rows | registry files moved |
|---|---|---|---|---|---|
| repository home | 3,757 | 11.54 | 3,938 | 8,078 | 95 (2.85 GB) |
| `pegasus_linkage` | 1,241 | 3.72 | 1,067 | 2,308 | 0 |
| `pegasus_fresh` | 814 | 1.36 | 127 | 961 | 0 |
| `pegasus_live/home` | 151 | 0.23 | 157 | 311 | 0 |
| `pegasus_fresh3` | 0 | 0 | 1 | 1 | 0 |

* Every digest matched.
* Afterwards no stray home holds a blob the one home lacks.
* Registry files that differ between homes kept the one home's copy, which is newer in every case: CNES CADGER of
  10-05 against 09-29, and the SIDRA registry of 50 MB against 94 KB.
* Derived lake content was not adopted (2.4 GB of linkage `roles`, 2.3 GB of SIHSUS partitions and others): it is
  recomputed here from the downloads by the current code.

## Does the one home recognise them?

The listings were stale against the adopted fetches, so the directories they cover were crawled again: SIH `Dados`,
SINAN `PRELIM` and Dados Abertos dengue. That is 23,392 files in 6 s, with 119 new and 1,556 "changed".

* **What the stale listing would have caused.** Against the 09-28 listing, the 23/10 SIH fetches all disagreed:
  295 files republished since then. Leaving that listing would have meant fetching them a third time.
* **The second fault the crawl exposed.** After it, 588 latest fetches still disagreed. Of these, 563 had the same
  size and times exactly 3 h apart: the server's two clocks.
  * LIST shows the server's wall clock, which is UTC−3. MDTM shows UTC.
  * The offset was confirmed on 1,290 MDTM/LIST pairs in the catalogs (180 or 181 min, every season since 2019) and on
    6 files live, two of them dated 2018-02-05, inside the old summer time.
  * With `same_instant`, 20 of 49,083 latest fetches are judged changed. All 20 differ in size from the listing: real
    republications, to be fetched when asked for.
* **The fetcher's own judgement** (`Fetcher._should_skip`):
  * SIH-RD 2015 and 2020–2026: 2,455 held, 29 never fetched.
  * SINAN dengue: 16 held, 1 republished, 10 never fetched.

## Population series in the one home

PegaSUS had read its population series from the repository home (`PEGASUS_POPULATION_ROOT`). They were rebuilt in the
one home with `pegasus-data population`, at a cost of 168 IBGE files and 257 MB fetched in 8 min. Their blobs had been
pruned from the repository home after its lake was built, so they were held nowhere.

The rebuilt series match the old ones exactly (`load_population`, by municipality and year):

| series and year | rows | population |
|---|---|---|
| POPSVS 2010 | 902,340 | 194,749,329 |
| POPSVS 2022 | 902,340 | 210,862,983 |
| POPTCU 2015 | 5,570 | 204,482,459 |
| POP 2005 | 367,224 | 184,184,074 |

**Not done here.** Deleting the stray folders was refused by the session's permission check and is left to the author
(STATUS). The other project's own copies of records (`data/raw`, 225 MB; its DuckDB, 908 MB) belong to that project
and were not touched.
