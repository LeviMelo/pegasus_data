# The read plan and the validity window (ADR-0185)

**Regime.** Branch `struct-query` (base `2e09a61`), the real root `pegasus_core_data` read only (`max_download=0`, a guard refused
any fetch), the catalog and lake as another agent left them: base and new ran back to back on the same state (an earlier base run
differed on one label, `GESTRISCO`, because the catalog had been rewritten between the runs; the pairs below are the valid ones).
Scratch: `s_query/cases.py` (14 calls, saved as Parquet and report JSON), `compare.py` (rows, columns, values, ordering
normalised), `vint_check.py`.

**Same output.** `query` SIM-DO BR 2019 (labelled and codes), SIM-DO 2018-2019 with no state, SIH-RD AC 2019 (labelled, codes),
AC 2017-2019, AC+AP, SINAN-LEPT 2018-2020, SINASC-DN 2019, SIA-PS AC 2019; `load` SIH-RD AC 2018-2019 and AP 2019 all columns;
`scan` SIH-RD AC 2019 and SIM-DO 2019 with no state: 14 tables equal in rows, columns and values, and 8 plans equal in every field
they had. The read plan changed what is read from nowhere; the one difference is in the reports.

**One difference, a fix.** The `RenderReport` of a first call now lists the vintage substitutions it made: SIM-DO 2019 reports
`MUNICBR`, `CID9WHO`, `BR_MUNICIPALFA` and `IDADE` ("no codelist window covers 2019, so the current vintage was used"), SINAN-LEPT
120 such warnings (40 single-window tables x 3 years), SIA-PS 12 (`ETNIA`, one per month). They were recorded only by whichever call
computed a table first in the process: `lookups._lookup_map` on the base, inside a collector, returns the note once (`{('MUNICBR',
'2019', 'current')}`) and an empty set on the second call, and the table had been computed earlier outside the render. The decisions
are now recorded on every use.

**Same classes.** `vint_check.py`: 30 label-pack codelists x SIHSUS and SIM x 219 months (13,140 requests): `reference_vintage`
mapped them to 101 representative requests (of 60 table/system pairs) and the rows served for a month and for its representative
were equal in all 13,140.

**Tests.** Whole suite, `-m "not network"`: 1,730 passed, 28 skipped, 0 failed (15 min).

**Time** (warm medians of 7, base and new alternating, ms; other agents were using the machine, so read ratios):

| call | base | new |
|---|---|---|
| `query` SIH-RD AC 2019, labelled (205 rows) | 880 | 300 |
| `query` SIH-RD AC 2017-2019, labelled (533) | 2,700 | 1,560 |
| `load` SIH-RD AC 2018-2019, 4 columns, labelled | 1,500 | 840 |
| `query` SIM-DO BR 2019 labelled (95,757); codes | 300; 80 | 340; 82 |
| `query` SINAN-LEPT 2018-2020 (45,878 x 200 columns) | 1,900 | 1,950 |
| `scan` SIH-RD AC 2019; SIM-DO 2019, no state | 17; 28 | 17; 27 |

Where it went: 288 (table, month) keys into a 256-entry LRU missed on every warm call, so `_contradictions_uncached` ran 288 times
(0.34 s of 0.84 s of a SIH-RD state-year); keyed by window it runs once per table. The calls that are one group or are bound by the
data (SIM-DO, SINAN-LEPT) did not move, and rendering still makes one group per month: its remaining per-group cost is the
column weighing (`value_counts`, `decide`) and the join (OPEN_QUESTIONS 80).
