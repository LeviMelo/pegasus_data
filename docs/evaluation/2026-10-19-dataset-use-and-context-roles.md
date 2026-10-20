# What each dataset is for, and the roles of the context datasets (ADR-0195)

**Regime.** Branch `meta-contexts` from `d7d75ac`, 2026-10-19; a fresh data home (the shipped seed catalog); the live FTP tree, DEMAS,
the Portal de Dados Abertos, ANVISA and the S2iD portal; `pegasus_core_data` (registries, lake) and the maintainer catalog only read.
Artifacts are not kept: every figure below is re-run from the named call.

**Roles written (14 datasets, 298 columns).** SISAGUA CTLB/CTLD/CTLF/VIGB/VIGC/VIGD, SNGPC IND/MAN, BNAFAR-STOCK, SIES-DIST, REGIAO-MUNICIPIO,
ANS-ICB, INEP-EDBASICA, S2ID-EVENTOS in `curation/roles/`. The columns are the ones the intake lands (the SISAGUA headers of seven published
files were read by ranged GET and mapped through the shared dictionary's aliases: 34, 33, 30, 22, 28 and 31 columns; SNGPC's 15 and 17 headers read
in 2014-01/2019-01 and 2026-01); each meaning is a line of the source's own dictionary (SISAGUA's ODT/PDF, ANVISA's two PDFs, SIES' PDF, ANS' ODS, INEP's xlsx,
MIDR's CSV; DEMAS' swagger describes only the filters of BNAFAR and REGIAO). `undeclared_units()` and `undeclared_fact_domains()` list none of them.
Declared from a measurement: `BNAFAR` `codigo_cnes` is width 7 (396 of 11,220 landed rows have 1 to 6 characters: the endpoint serves a number);
VIGB's `ANALISE_REALIZADA` and `PROVIDENCIA` end in 2022 and `DT_ANALISE`, `LD`, `LQ` start in 2023 (first 399 rows of each year 2020-2025: 186-217 and 6-16 filled to 2022,
0 from 2023; 391-399 and 5-26 filled from 2023, 0 before).

**Use declared on 64 datasets** (17 support, 6 denominator, 1 reference, 21 context, 19 not_an_event_source); `undeclared_uses()` lists the 20 that belong to
the SRAG, FA, SINAN-ESPO/NTRA, SISCAN and SISPRENATAL branches. The reasons that rest on a count:

| claim | call | counted |
|---|---|---|
| SIM-DOEXT, DOINF, DOMAT are subsets of SIM-DO | `query` of SIM-DO (AC) and the three national files, 2018; rows matched on death date, birth date, sex, age, residence, occurrence, cause, place | AC residents in DOEXT 689, DOINF 273, DOMAT 9: 689, 273 and 9 found among SIM-DO AC's 4,094 deaths. SIM-DO has 689 deaths with a V-Y underlying cause and 273 with `IDADE` < 400: DOEXT and DOINF are exactly those; DOMAT's rule is narrower than the flags (16 deaths with an O cause or a pregnancy flag, 9 in DOMAT). Nationally DOEXT 150,814, DOINF 35,864 (7 with `IDADE` 400), DOMAT 1,658 (1,639 O, 17 B, 2 F) |
| SIH-RJ is not disjoint from RD, SIH-ER is RJ's errors | `query` SIH-RD/RJ/ER, Alagoas 2018 | RD 177,515 rows (172,837 AIH); RJ 23,601 rows, 18,598 AIH, 4,885 (26.3%) also in RD; ER 27,769 rows, 18,598 AIH, all in RJ, up to 14 each |
| CNES rows are standings | `query` CNES-ST/LT/EQ, Acre 2018-12 | ST 861 rows = 861 CNES; LT 201 rows, 32 establishments; EQ 2,473 rows, 589 establishments |
| S2iD damages are not additive | the 2026 file (76,190 rows, 1991-2025) | `DH_OUTROS AFETADOS` sums to 295,022,756; protocols unique; municipality code 7 characters in all rows |
| SNGPC rows are groups, not sales | ANVISA's dictionary v1.0 (2020) section 5.2.1; headers | no pharmacy, prescription or patient column in either file; `TP_RECEITUARIO` of the industrialised files is `1.`-`5.` in 3 landed months (2014-01: 2,953,904 `5.` of 4,543,907) and 5 raw files, `1`-`5` in the compounded ones |

**Descriptions that were wrong, corrected where written.** SIH-MT was "an admission whose billed procedure changed" (it is 17 columns of professional acts: ATO_PROF,
N_AIH, QTD_ATO, VAL_ATO; the ontology had corrected the name on 2026-10-08); SIH-CH was "superseded by CNES, for the years before it" (its files run 2019-2026); SIA-AC "covers renal
replacement therapy only" (its siblings are chemotherapy, radiotherapy, medicines and others); SIH-RJ's "ABSENT from SIH.RD" (13,713 of the 18,598 AIH are absent from RD in the same year, 4,885 present);
SNGPC-IND/MAN's "one sale line (a pharmacy, a month, a medicine, a prescription)" (the files carry no pharmacy or prescription).
Fourteen datasets that had no description now have one (IBGE POPS/POPT, DADOS_ABERTOS COBERTURA/DOSES_RESIDENCIA, SIH-CM, the SIA 2001-2007 blocks CO, EX, OP, PC, PF, PQ, PR, UD, UO);
SIH-CH, SIH-CM, the POPS/POPT and DADOS_ABERTOS entries state their own `semantic_axes` and the ten APAC 2001-2007 blocks an explicit empty one, so none inherits SIA's AP_* header
columns (`tests/test_semantic_axes.py` names these as the datasets left without both axes, with the reason).

**Found, not fixed (OQ-90).** SNGPC-IND's `TP_RECEITUARIO` lands as `5.`, `1.` ...: the intake drops only a trailing `.0`, so the declared codes `1`-`5` never apply to it.
