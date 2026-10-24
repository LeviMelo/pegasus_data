# SIH-SP's sex and age, read through the AIH from SIH-RD (2026-10-24)

**Scenario:** `scripts/live.py sp_strata` (Acre 2023-01; `PEGASUS_SP_PERIOD`, `PEGASUS_SP_GEO` for another), artifacts `data/probes/live/sp-strata-1/`
(also `sp-strata-AC-2008-06`, `sp-strata-AC-2013-06`, `sp-strata-RR-2025-06`). **Regime:** branch `sp-strata` from `16ff861`, a fresh data
home (10.7 MB of source files from the FTP server: SP and RD of ten Acre and Roraima state-months), 2026-10-24. ADR-0199.

**Why it matters.** PegaSUS stratifies a dataset's events by residence, sex and age read from `stratum` roles; SP files none of the last two, and
`gateway._strata('SIHSUS-SP', 'procedure')` raised "no age stratum" before the change. A sex and age taken from the wrong admission, or SP's
lines multiplied by RD's repeated AIHs, would be a count of procedures that looks right.

| check (Acre 2023-01) | result |
|---|---|
| SP rows, own columns only / with `SEXO`, `IDADE_anos` | 46,933 / 46,933, same order and values |
| SP AIHs found in the same month's RD | 4,164 of 4,164 (RD: 4,165 rows, one AIH twice, IDENT 1 and 5, same sex and age); 46,933 of 46,933 rows |
| SP and RD agree on the matched admission (SP's own columns against RD's IDENT 1 row) | residence, principal diagnosis, admission date, facility: 4,164 of 4,164 each |
| A known drop: 50 AIHs removed from the RD rows read | 523 SP rows of those AIHs (counted from SP alone) = 523 reported unmatched = 523 null `SEXO`; 50 keys; all other rows equal the full read |
| `count_events(..., by=[SP_M_PAC, IDADE_anos, SEXO])` | 83,263 events = the sum of `SP_QT_PROC` of the 46,933 lines |
| `SEXO` labels | 1 Masculino 17,310 lines, 3 Feminino 29,623; all labelled |

The same four checks on Acre 2008-06 (25,554 SP rows, 4,026 AIHs, drop 386 rows), Acre 2013-06 (29,685 rows, 4,179 AIHs, five AIHs of four RD rows each,
1+5+5+5, none disagreeing on sex or age; drop 317) and Roraima 2025-06 (26,433 rows, 2,935 AIHs; drop 196): every AIH matched, every agreement 100%,
events = `SP_QT_PROC`. The match alone, six more reads: AC 2010-06, 2016-06, 2019-01 (30,321 lines of 3,284 AIHs, as the declaration says), 2023-02,
2023-01 to 03; RR 2023-01: no SP row without an RD row. So the unmatched path (reported, null, a `ThroughKeyWarning`) is exercised only by the known drop;
no natural case was met in 10 state-months.

**The engine** (`pegasus_core.gateway`, read only, `PEGASUS_DATA_ROOT` and `PEGASUS_HOME` on scratch directories): `_strata('SIHSUS-SP', 'procedure')` returns
`residence SP_M_PAC, sex SEXO, age IDADE_anos, entity patient` (it raised on `16ff861`). `event_counts('SIHSUS-SP', 'procedure', 2023)` with
`count_events` held to Acre 2023-01 counts 83,263 procedures in 21,372 cells, none unallocated:

| age | male procedures | female procedures | male admissions (RD) | female admissions (RD) | per admission, male / female |
|---|---|---|---|---|---|
| 0-9 | 7,984 | 7,988 | 224 | 182 | 35.6 / 43.9 |
| 10-19 | 1,919 | 4,878 | 106 | 403 | 18.1 / 12.1 |
| 20-29 | 2,272 | 9,431 | 156 | 837 | 14.6 / 11.3 |
| 30-39 | 2,762 | 5,995 | 186 | 549 | 14.9 / 10.9 |
| 40-49 | 3,359 | 3,652 | 187 | 286 | 18.0 / 12.8 |
| 50-59 | 5,377 | 2,059 | 196 | 148 | 27.4 / 13.9 |
| 60-69 | 7,129 | 3,089 | 183 | 133 | 39.0 / 23.2 |
| 70-79 | 4,435 | 5,009 | 137 | 115 | 32.4 / 43.6 |
| 80+ | 3,281 | 2,644 | 74 | 62 | 44.3 / 42.7 |

Plausible: women are 65.2% of RD's admissions (obstetrics, 10-39) and 53.7% of SP's procedures, because men and the very young and old carry more billed
lines per admission (intensive care, long stays). The two counts are of the same patients by construction; the table shows no age or sex where the other
has none.

**Noted, not changed.** A read of RD with `IDADE_anos` selected warns "selected fields are structurally absent from some schema generations" (the derived
age is not a file column); the read of SP now repeats it. The sample is two small north-western states; nothing here says the match is complete in São Paulo.
