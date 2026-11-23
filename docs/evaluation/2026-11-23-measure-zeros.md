# Measure zeros: the 27 columns of OQ 101 decided from the forms and companion fields (2026-11-23)

**Scenario.** Residue of [the range sweep](2026-11-23-holdings.md): 27 `kind: number` columns declared `missing: []` from
one year's range, whose zero neither source nor lake settled. Each was read in the real home (lake read-only, DuckDB 1.5 GB,
all held years, strings cast with `try_cast`), against the harvested form or dictionary and a companion field of the same
record; no value was decided from its frequency alone. Regime: master 2f67854c, 2026-11-23. Edits: `curation/roles/<dataset>.yml`.

| column(s) | decision | evidence |
|---|---|---|
| SINAN-FMAC `TIT_IGG_S1/S2`, `TIT_IGM_S1/S2` | `missing: ['0']` | dictionary: titre essential only if the result is not 4 (not performed); result 4 holds 3,035 of 3,035 zero IgG S1 titres, rows with no result 99.4%, positive result 5.5%; a titre is a reciprocal dilution |
| SINAN-LEPT `MICRO1_T_1/2`, `MICRO2_T_1/2` | `missing: ['0']` | titre required only if the serovar is named; MAT result 'Reagente' has 0.2% zero (15 of 8,383), 'Não reagente' 25%; the reading is the result column's |
| SINAN-DENG `S1_TIT1`, `S2_TIT1` | open, `missing_unknown` | legacy 2000-2006, in no harvested dictionary; 14 zeros of 1,567 filled, no pattern with the serology codes, values 1-4 dominate (not dilutions) |
| SINAN-SRC `PESO` | `missing: []` kept, `unit_unknown` | 0 never occurs (0 of 1,855 values, 2007-2026); kg (27 values, 1.765-3.945) and g mixed, plus 7-41,750 neither: no conversion guessed |
| SIASUS-BI `AUTORIZ`, SIASUS-CO `COB_NUM` | `kind: identifier`, `link_only` | an authorisation / APAC number (BI 2023: 6.0M distinct in 73.9M rows, 84% zero; CO: 12-digit, no zero), as SIASUS-PA's `PA_AUTORIZ` |
| SISAGUA-CADP `NU_VALOR_POPULACAO_ESTIMADA`, `NU_ECONOMIA_DOMICILIO_PERMAN` | open, `missing_unknown` | zero together on 90-99% of zero rows, urban/rural blank on 87-93%; a solution moves between 0 and positive across years (377 of 727 SAA zero in 2023 positive in 2024); the dictionary does not say which |
| CIH-CR `UTI_MES_TO` | `missing: ['0']` | 0 on all 5,578,205 rows of 2009-2011 while `UTI_INT_TO` is positive on 5% and `DIAS_PERM` on 83%: not filled |
| CNES-LT `QT_CONTR` | `missing: ['0']` | positive in 12 establishments in 2012-2026; 0 for every private-law establishment with SUS beds in 2026 (15-51% have `QT_SUS` > 0) |
| PNI-DPNI `DOSE1`, `DOSEN`, `DIFER` | `missing: ['0']` | 2019 (the only year held): every row has `QT_DOSE` >= 1 and its `DOSE` order, yet 0 in all three; 2009-2010 (DPNIUF) hold them empty; 2004-2018 not held |
| SIASUS-PA `PA_DIF_VAL` | `missing: []` kept | a difference of unit values: non-zero 1.2% (2014), 0.58% (2015), 0.003% (2016), none in 2012, 2020-23, 2025-26: a vanishing differential, zero is no difference |
| SIASUS-PA `PA_VL_CRD` | open, `missing_unknown` | 0 on all 3.83M rows of 2025-2026, the only years it exists; undocumented |
| SIASUS-SAD `PA_QTDAPR`, `PA_QTDPRO` | open, `missing_unknown` | zero 0.1-17% (2012-2017), 75% (2018, max 1), almost always on both together; `QTDATE` > 0 on 184 of 867 zero lines of 2018; the RAAS-AD rule is not harvested |
| SINAN-CHAG `TEMPO` | `missing: ['0']` | `qt_dia_tratamento` (days): 2022 fills every row, 0 on 4,749 of 5,194 and 4,649 of 4,668 with no `DROGA`; 2023-2025 fill only the treated, 3 zeros in 1,763 |
| SINAN-HANT `CON_LOCALI` | `missing: []` kept | km of the infection site from the seat: 0 km is valid; empty unless answered (74 filled in 4 years, 1 zero) |
| SINAN-ACGR `NU_TRAB` | `missing: ['0']` | 'Se sim, quantos' of `MAIS_TRAB`: 0 on 35% of the yeses (59,143 of 169,037) and >99.99% of the nos (not applicable, derivable from `MAIS_TRAB`) |

**Counts.** 27 columns: 15 declared not recorded (`'0'`), 3 zero kept as recorded (`PESO`, `PA_DIF_VAL`, `CON_LOCALI`; `PESO`
also states why its unit is unknown), 2 reclassified as identifiers, 7 left open with their reason.

**What would decide the open ones.** DENG `S*_TIT1`: a dictionary line of the 2000-2006 layout. SISAGUA-CADP: the registrar's
rule for a solution with no population. PA_VL_CRD: a technical note after July 2019 or a year with a non-zero value.
SAD quantities: the RAAS-AD layout's rule. SRC `PESO`: a unit per record. The PNI years 2004-2018 are to be re-read when held.
