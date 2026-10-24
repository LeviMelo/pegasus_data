# Care-flow edges carrying the sum of a role-named quantity (2026-10-24)

**Check.** `care_flows(..., measure=ROLE)` (ADR-0201) adds `<role>_n` and `<role>_sum` to every edge. The sums were
compared edge by edge with a reading of the same records written apart from the code under test: `query` of the
columns, the event rule applied by hand, the role's declared `missing` codes and `domain` applied by hand, the same
municipality codes. What was counted: edges whose sum or count differs; the totals; the events with no value and why;
the events no edge holds. It matters because a sum that mishandles a missing code is a plausible wrong mean: the 147
`CONSPRENAT` 99s below, taken as visits, move Acre's 2015 mean from 6.04 to 6.87 prenatal visits.

**Regime.** Branch from `4b207c3`, scratch home (blobs 6.2 MB for everything below, fetched in the run), Acre
published files, 2026-10-24. `care_flows` counts whole years, so `period="2023-01"` would still read the year: the
smallest sample is a state-year. The scripts live outside the repository (scratch); no artifact under `data/probes/`.

| sample | events | role (column) | n | not recorded | outside domain | sum | edges differing |
|---|---|---|---|---|---|---|---|
| SIH-RD AC 2023, 283 edges | 59,782 | `admission.length_of_stay` (DIAS_PERM) | 59,782 | 0 | 0 | 271,932 days (mean 4.55) | 0 |
| SINASC-DN AC 2023, 107 edges | 14,473 | `birth.weight` (PESO) | 14,384 | 89 blank | 0 | 45,787,089 g | 0 |
| | | `birth.apgar5` (APGAR5) | 13,748 | 725 blank | 0 | 130,122 | 0 (2 edges with no value: n 0, sum null) |
| SINASC-DN AC 2015, 118 edges | 16,980 | `pregnancy.prenatal_visits` (CONSPRENAT) | 16,281 | 699: 552 blank, 147 coded `99` | 0 | 98,302 | 0 |
| | | `mother.age` (IDADEMAE) | 16,978 | 2: 1 blank, 1 `99` | 0 | 421,726 | 0 |
| SIM-DO AC 2015, 109 edges | 3,517 (= `count_events`) | `death.receipt_delay_days` (DIFDATA) | 3,517 | 0 | 0 | 271,925 | 0 |
| | | `birth.gestation_weeks` (SEMAGESTAC) | 194 | 3,316 blank | 7 | 6,104 | 0 |
| | | `pregnancy.previous_fetal_losses` | 189 | 3,326 blank | 2 | 57 | 0 |

**Accounting closes.** SIM-DO AC 2015 has 4 events whose residence is `120000` (unresolved); those four hold DIFDATA
values summing 293, so the edges hold n 3,513 and sum 271,632, as the direct reading does and as the metadata's `n`,
`sum` less `unresolved` say. `events = n + missing + outside_domain` in every row. No sample had an event with a blank
origin or destination (`unplaced` 0): that mask is the code path of `unresolved`, not exercised on its own.

**Unchanged.** On SIH-RD AC 2023 `from, to, weight, kind, vintage, share` and the `events`, `unplaced`, `unresolved`
metadata equal the table of the commit before the change (283 rows, saved before editing); the same holds with and
without `measure` for SINASC-DN and SIM-DO. `care_flow_profile`, `care_flow_catchments`, `care_flow_communities` and
`compare_flow_regions` return identical tables on the edges with and without two measure columns, with and without
`by="COMPLEX"` (a `by` column and a measure's state stay apart: a role has a dot). `pegasus-data graph SIH-RD
--period 2023 --geo AC --measure admission.length_of_stay --out x.csv` writes the columns and prints the accounting;
`--derive profile` works with it.

**Refused, with the reason** (before any file is read): a column name (`DIAS_PERM`: names the role it stands for), a
misspelt role (nearest roles), a packed age and a category (not quantities), a quantity with no declared `missing`
(CIHA `QT_PROC`), a weighted event (SIA-PA, SIH-SP: a row of N events). A stock: CNES-ST's `QTLEITP1` and `QTINST14`
under their recipes' `additive_over: [geography, dimensions]` are refused over time ("a stock ... Use
time_reducer='mean'") once a role is given `missing=()`, which their roles do not declare (CNES-ST has no flow).
Of the 364 quantities in the 87 flow datasets, 116 declare `missing` and 248 do not.

**National check, bed-days of diabetes (2026-10-24, nees-gt-ms).** `care_flows("SIH-RD", period=2023, geography="BR",
by="DIAG_PRINC", level="category", measure="admission.length_of_stay")`, 34 s from the lake (`pegasus_core_data`, branch
`claude/nees-gaps-dc2b18` at 6091c06): 13,215,246 events, none unplaced or unresolved, every one with a `DIAS_PERM`. Codes
E10-E14: 138,316 admissions and 941,694 bed-days (mean 6.81); Alagoas residents 1,072 (17 treated outside the state, 8,525
bed-days); Maceió's residents 269 of 275 at home (2,338 bed-days there); DF residents 1,672, 1,663 into Brasília. A
`query` of the same records read apart (`IDENT` 1: 138,316 rows, `DIAS_PERM` 941,694; the 43 `IDENT` 5 continuation AIHs,
1,077 days, are outside the event as declared) gives the same numbers; the admission counts equal the ones nees-gt-ms
had verified independently.
