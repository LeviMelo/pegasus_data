# ANS beneficiaries by municipality, 2000-2026, and the population without private coverage back to 2000 (2026-11-22)

**Regime.** Branch `worktree-agent-af84eba314a2cfbd7` off e007bff1, a scratch data home (deleted after). Source `ans_beneficiaries_municipal` (`curation/intake.yml`), fields `ans_beneficiaries_quarterly`
and `ans_dental_beneficiaries_quarterly`; layout in DATA_SOURCES §16. The intake reads `format: dbc` through the package's decoder (`decode.dbc`) into a Parquet of strings, rows counted against the DBF header.
Landed: all 107 quarters 2000-03 to 2026-09, 176,199,297 rows (each unit's rows equal its DBF header's record count).

**December counts (NR_BENEF_M).** 2012: 1,768,458 cells in 5,558 municipalities, 47,751,772 links placed (47,846,092 with the 94,320 in no IBGE municipality). 2020: 5,570 municipalities, 47,895,510 placed.
2021: 49,209,906 placed, 49,252,210 in all.

**Against PDA-024, December 2021.** `ans_beneficiaries` (Médico-hospitalar) has 49,209,904 placed and 49,252,210 in all: the two sources agree to 2 links, in one municipality (430210: 47,690 and 47,688); by sex
26,145,814 / 26,145,813 F and 23,064,092 / 23,064,091 M. They are one SIB count published twice, so the product uses one source throughout (ADR-0235).

**The product, `sus-dependent-4`** (population account bands 7, December of 2000-2025, 4,884,576 rows; comparable areas to 2009, municipalities from 2010). National links by year: 30.1 million (2000), 41.0 (2008), 47.7
(2012), 50.5 (2014, the peak), 47.0 (2019), 47.9 (2020), 52.8 (2025); coverage 0.172 in 2000, 0.241 in 2012, 0.225 in 2019, 0.245 in 2025. Against `sus-dependent-3` (PDA-024, 2021-2025), 189,006 cells a year: populations
equal; links differ in 30-38 cells a year by at most 3 (2021-2024) and 10 (2025), 36-55 links in all (ANS republished the December files after sus-dependent-3 was built, DATA_SOURCES §12), uninsured by as much.
**Registry above population.** A place-year whose links exceed its population: 40 of 143,664 (2000-2009 areas: 1-4 a year; 2010-2020: 1-2; none from 2021), 31 of them with under 20,000 residents, the largest ratio 9.65
(a registered-residence artefact of a very small place); cells flagged `registry_exceeds_population` (links above the interval's upper bound): 141 in 2000, 100 in 2012, 17 in 2021, 12 in 2025. The uninsured count is 0 in 2,127 of
4,884,576 cells.

**Memory.** `build_source` read every year of a field whole after landing (27 years of 7 million rows took 10.8 GB and was killed, 2026-11-22). It reads each month's cube alone (peak 1.15-1.33 GB for a quarter of about
1.75 million cells, `psutil` resident set), and the product reads one December per year.
