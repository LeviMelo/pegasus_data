# A monthly intake unit is the publication of its month (2026-10-24)

**Check.** `plan("SNGPC-IND", period="2014-01")` said "Publication resolution: year" and read the 12 monthly part files of 2014
(58,625,324 rows) for a month of 4,543,907. What was counted: the plan's resolution and lake files, and the rows a month's
`query` returns against the row count of the part files' own Parquet metadata (read directly) and against `_MONTH` /
the competence of every row. It matters because a month that reads its whole year is a 12-fold cost, and the other way
round, a month served from another month's file would be a silently wrong figure.

**Cause.** `intake._register` filed every publication of a unit as `<unit>#year=<record year>` with `normalized_date =
year * 100`, whatever the unit was filed for; the planner takes a year's resolution from `normalized_date % 100`, so a
dataset of monthly files was "annual", and it selects lake files by year only.

**Fix.** A pattern declared by `months:` gives its units a `month` (YYYYMM); `_register` dates the unit's publication by it
(`normalized_date` YYYYMM, `date_format` YYYYMM). The planner (`coverage.in_months`) then opens only the lake files built from
the publications of the months asked, and `coverage.sole_competence` gives the records of a file built from ONE publication
of a month their competence (an intake record stores none), so the generic period filter finds it. Declared by `years:`, listed,
or undated, a unit stays a year. Catalogs written before are dated by `pegasus-data intake-periods` (catalog only, idempotent).

**Regime.** Branch from `ee434cc`; the real home `pegasus_core_data` read only (lake and catalog untouched); the catalog read
through a `sqlite3` backup copy dated by the new command (`PEGASUS_CATALOG_DIR` the copy, `PEGASUS_LAKE_DIR` the real lake),
2026-10-24. Scripts outside the repository (scratch).

| query (`select=[one column]`, `present='codes'`, `max_download=0`) | resolution | lake files | rows | the part files' own rows |
|---|---|---|---|---|
| SNGPC-IND 2014-01, before | year | 12 | the year, 58,625,324 | 4,543,907 |
| SNGPC-IND 2014-01 | month | 1 (`part-201401-0`) | 4,543,907; `_MONTH` 1 on all, competence 201401 | 4,543,907 |
| 2014-01..2014-02 | month | 2 | 8,893,979 | 4,543,907 + 4,350,072 |
| 2014-12..2015-01 (two years) | month | 2 | 9,607,014; months 12 and 1 | 4,876,106 + 4,730,908 |
| 2021-10 (the last month filed) | month | 1 | 1,162,556 | 1,162,556 |
| 2014 (plan) | month | 12 | the 12 files, 58,625,324 | |
| SNGPC-MAN 2019-01, before: 4,132,322 rows, 12.3 s | year | 12 | | 333,909 |
| SNGPC-MAN 2019-01 | month | 1 | 333,909, 3.2 s | 333,909 |
| SNGPC-MAN 2019 | month | 12 | 4,132,322; months 1..12 | 12 files, 4,132,322 |
| SNGPC-MAN 2019-12..2020-01 | month | 2 | 673,839 | 335,489 + 338,350 |
| SNGPC-IND 2021-09..2021-12 | month | 2 | 7,295,037; months 9 and 10 | adaptation: 2021-11, 2021-12 not published |
| SNGPC-IND 2021-11 | | | `NothingPublished`: files no publication (filed in 2021: 01..10) | |

**Which sources are monthly** (from the declaration, `intake._units`): `sngpc_industrialized` (`months:` 201401-202110 and
202601-202609: 103 units, 94 landed here), `sngpc_compounded` (103, 34 landed) and `ans` (the December file of each year by state,
140 units, none landed here). Yearly or undated, and unchanged (plans identical to the commit before): SISAGUA CTLB and VIGB
(`years:` 2014-2026) and CTLD, CTLF, VIGC, VIGD (one undated zip), SRAG (8 listed files, records dated by `date`), FA-HUM,
FA-EPIZ, S2ID (one file), INEP (`years:`), and the API tables (BNAFAR, SIES, REGIAO). A month asked of them is still
adapted to its year ("source publishes annual data") and reads the year's files: SRAG-NOTIF 2021-03 returns 1,753,295 rows,
SISAGUA-CTLF 2019-02 86,462, SISAGUA-VIGC 3,178, FA-HUM 2018-01 1,308, each equal to the commit before, with its `time_resolution` notice. `pegasus-data intake-periods --dry-run` on the
real catalog's copy counts 94 + 34 publications to date, and none among the 145 of SISAGUA (78), SRAG (15) and FA (52) it reads
(plus S2ID, ANS and INEP, with none landed here); a second run dates none.

**Parts whose unit key is not a month.** None in the lake: all 94 + 34 SNGPC parts sit in the year of their unit's month, and
the key is never parsed from a file name; the unit's period comes from the declaration. A monthly unit's records dated in
another year would be a publication of that year at year resolution (`_dated`), served by that year's queries and by no month's.

**Other datasets.** 180 plans (a month, a three-month window and the year) over 44 state-years of 18 DATASUS datasets (SIASUS
AD..SAD, SIHSUS-RD, CIH-CR, CIHA, SIM-DO/DOFET/DOREXT, SINAN-CHIK/DENG/LEPT, PAINEL-PO) equal the commit before in resolution,
years, strategy, adaptations and files except 15: 7 open one file fewer (SIH-RD AC 2025-03 reads one of its two partitions, the
other holds only other months) and 8 now raise `NothingPublished` at plan time: the month asked has no file in that state-year
(SIASUS-ATD AC files 2014-08..12, so 2014-03 is not published; CIH-CR RO 2011 files 01), where the lake returned an empty table
that read as "no records". A request that files only some of its months reads those and carries the notice (`Adaptation
publication`, SNGPC-IND 2021-09..12). `NothingPublished` is the signal the CLI, `serve` and the aggregate builder already handle.

**Open.** The whole-year SNGPC-IND read (58 M rows with the hidden `_source_path`) still fails at rendering (a string column over
2 GB); that is the separate fix of `view.py` and `lookups.py`, not this one.
