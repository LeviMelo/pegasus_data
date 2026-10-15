# Fatal outcome codes: declared from DATASUS's labels, read against real records (ADR-0191)

Regime: branch `worktree-agent-a76ed45173272d203` (from `d87d3d1`, `pegasus-core-fixes`), 2026-10-14. Read-only on `pegasus_core_data` (lake parquet, one column at a time; cached `.dbc` blobs decoded for one column; the catalog opened read-only). The main repo's `pegasus_data_home` holds the catalog and no records, so it could not serve the counts. The labels the package applies to forms without a dictionary came from `translate(series=, year=)` on a scratch copy of the catalog. Probes were throwaway scripts (scratchpad); the figures are what they printed.

**Declared:** 73 columns. `fatal` and `fatal_other` on the outcome column of 46 SINAN datasets; `fatal: ['1']` on `MORTE` (SIH-RD, SIHSUS-RJ, CIHA, CIH-CR), `AP_OBITO` (20 APAC layouts), `PA_OBITO`, `ST_OBITO` (2). Undeclared, with the reason: `CON_EVOLUC` 2000-2006 of 7 SINAN datasets (no published dictionary), HIVE `EVOLUCAO` (11 of 6,088 records filled in 2015; none in 2017, 2020, 2024).

**What was counted, and why it is the thing that matters.** The share of rows a case fatality would call fatal, from the declared codes read off `roles()` (not typed into the probe), against what each outcome is known to be: all-cause in-hospital mortality of SIH a few per cent, dengue and chikungunya lethality well under 1% of notifications, leptospirosis and tuberculosis lethality of a few to some ten per cent. A wrong code (a cure, an "ignorado") would put the share at tens of per cent.

| dataset, year | rows | fatal code | fatal | of all rows | of known outcome | `fatal_other` |
|---|---|---|---|---|---|---|
| SIH-RD `MORTE`, 2022 (27 UFs) | 12,520,914 | `1` | 605,542 | 4.84% | 4.84% | |
| CIHA `MORTE`, 2022 | 20,549,661 | `1` | 98,211 | 0.48% | 0.54% (2,338,793 null) | |
| SINAN-DENG `EVOLUCAO`, 2018 | 262,611 | `2` | 203 | 0.077% | 0.114% | `3`: 57 |
| SINAN-DENG, 2021 | 540,049 | `2` | 279 | 0.052% | 0.067% | `3`: 159 |
| SINAN-CHIK, 2017 | 244,070 | `2` | 236 | 0.097% | 0.113% | `3`: 363 |
| SINAN-ZIKA, 2016 | 273,904 | `2` | 41 | 0.015% | 0.023% | `3`: 128 |
| SINAN-LEPT, 2022 | 15,217 | `2` | 322 | 2.12% | 3.06% | `3`: 1,021 |
| SINAN-SIFC, 2022 | 26,515 | `2` | 345 | 1.30% | 1.34% | `3`: 186 |
| SINAN-TUBE `SITUA_ENCE`, 2022 | 103,382 | `3` | 4,549 | 4.40% | 4.52% | `4`: 4,402 |

"Known outcome" leaves out null and the column's `missing` codes. Left in neither list: DENG 2018 `4` (54), CHIK 2017 `4` (44), SIFC 2022 `4` aborto (1,125) and `5` natimorto (716). SIH's 4.84% is the all-cause in-stay mortality.

**An independent structure.** SINAN-LEPT 2022 by `CLASSI_FIN`: every `2` (322) sits in the confirmed class (`1`: 2,556 alive, 322, 42 other cause, 180 ignored, 145 null) and none in the discarded (`2`: 6,574 alive, 965 other cause, 0 fatal). Among the 2,920 confirmed with a known outcome, 11.03% are fatal; among all notifications, 2.1%. The denominator of a case fatality is the confirmed class, which the consumer must choose.

**Labels where no form dictionary exists.** The seven forms without one (ZIKA 2016, TOXG and TOXC 2021, DCRJ 2023, SIFA 2020, VARC 2022, VIOL 2010) are labelled by the package `1` Vivo, `2` Óbito pelo agravo notificado, `3` Óbito por outra causa, `9` Ignorado (VIOL also `4` Óbito em investigação); the declarations rest on those labels. DENG 2018 is labelled by its form (`cura`, `óbito pelo agravo`, `óbito por outras causas`, `óbito em investigação`), TUBE 2022 by its form (`3` Óbito por TB, `4` Óbito por outras causas). TUBE's records hold `1`..`10` unpadded, so the codes are declared at that width.

**Loader.** Eight malformed declarations written by hand were each rejected with a message (an integer code, a code also in `missing`, in both lists, `fatal_other` alone, an empty list, a bare string, a repeated code, `fatal` on a number); the 73 shipped ones load. `roles("SINAN-DENG")` returns `fatal: ['2']`, `fatal_other: ['3']` for `EVOLUCAO`; `roles("SIH-RD")` returns `fatal: ['1']`, `fatal_other: None` for `MORTE`.
