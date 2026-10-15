# Sex codings, sentinels and fills: SINASC and the SIA APAC measures on the audits' records (2026-10-14)

Regime: branch `fix9-curation` (from fe2ba45, `pegasus-core-fixes`) against that base, both run on the same data; read-only on `pegasus_core_data` (lake parquet read by DuckDB,
`query(max_download=0)`; ACF SP 2019-06 and 2023-01 and AB SP 2012-06, 1,742 rows, fetched into a scratch home). Decision: ADR-0189. Scripts and outputs in
`data/probes/fix9/`: `measure_sinasc.py` + `sinasc_compare.out`, `measure_apac.py` + `apac_compare.out`, `event_atd.py` + `event_atd.out`, `apac_values.py` +
`apac_values.out`, `default_fill.py`, `regress_labels.py`. The classification of a measure is PegaSUS's own (`_measures`: not recorded = the raw text is a declared missing code;
valid = it parses and lies in the domain; the rest, a null included, is "outside the domain"); it reproduces the audits' figures from the base declarations (below).

**1. SINASC `SEXO`, DNBR2009-2024 (44,934,834 births).** Coded `1/2/0` in 2009, 2012-2013 and 2015-2024, `1/2/9` in 2010 (442 births) and 2011 (436), `M/F/I` in 2014 (1,526,907 /
1,451,693 / 659); no other category changes its coding: ESTCIVMAE, GESTACAO, GRAVIDEZ, PARTO, CONSULTAS, IDANOMAL, ESCMAE2010 and TPNASCASSI hold one code set in 16 years; four gain a code in some years and decode
(LOCNASC `5` and TPMETESTIM `8` from 2013, both in the layouts; ESCMAE `0`, declared missing, on 2-433 births in 2009 and 2011-2014); three gain a code no layout names and stay undecoded with
TPDOCRESP `0` (RACACOR and RACACORMAE `9` in 2010 and 2014, MESPRENAT `10`, TPROBSON `12`: OQ 83). Labelled read by year (`present="labels"`): the base returns Masculino, Feminino,
Ignorado in every year but 2010 and 2011, where the 878 `9` are `9 (?)`; the branch returns the three labels in all 16 (Masculino 23,007,503, Feminino 21,919,783, Ignorado 7,548 = all
44,934,834). Is `9` the ignored sex? Q56 (indeterminate sex) on 41.5-45.7% of the `9`, 32.3-41.9% of the `0` (2009, 2012, 2013, 2015) and 34.5% of the `I`, against 0.0% of sex 1 and 2; an
anomaly flagged on 64-68% / 60-66% / 51% against 0.6-0.9%; mean weight 2.38-2.41 kg / 2.38-2.46 / 2.53 against 3.12-3.24; and `9` is present exactly in the two years without a `0`. The rival reading,
a fourth category, has no layout and no profile. The case-mix table of the audit keyed on the raw code lists `1` and `M` apart (zero counts for `M` in 2012, `F` in 2015): the label is the
same (`1` Masculino, `M` Masculino), so pooling is by label (PegaSUS). One call over 2009-2014 (`query(period=(2009, 2014), present="labels")`, 17,445,684 births, six files, the three codings) returns Feminino 8,507,739, Masculino 8,934,950, Ignorado 2,995 (462 + 442 + 436 + 465 + 531 + 659).

**2. SINASC measures.** `99` on 223,344 births of CONSPRENAT (0.5%; next value above 80: `97` once), 52,296 of QTDFILMORT, 27,715 of QTDFILVIVO, 30,468 of APGAR1, 23,887 of APGAR5, 3,389 / 2,798 /
2,079 of QTDPARTCES / QTDPARTNOR / QTDGESTANT (at most 12, 28, 10 for any other value above 60), 743 of IDADEMAE (at most 58), 772 of IDADEPAI (56-111 for each age 86-98); PESO `9999` 107, `0000` 5.
Audit's 904 births (PE residents, Q02 among the codes of CODANOMAL, 2012-2019), valid / not recorded / outside the domain, base then branch: QTDFILVIVO 899 / 0 / 5 then 899 / 3 / 2 (QTDFILMORT, QTDGESTANT, QTDPARTNOR and QTDPARTCES likewise, 3 births each); CONSPRENAT 886 / 0 / 18 then 886 / 5 / 13; the base reproduces the audit (APGAR1 893 valid, 11 outside; IDADEPAI 247 / 657;
PESO 903, mean 2,582.75). The outside that remains is null: APGAR1 11, IDADEPAI 657, SEMAGESTAC 14, CONSPRENAT 13. The audit's "outside the domain absorbs the missing values" is therefore mostly PegaSUS
counting a null there (its `is_miss` tests the declared codes only), not the declarations. National 2012-2019 (23,382,156 births): moved to not recorded CONSPRENAT 153,019, APGAR1 16,392, APGAR5 12,983,
QTDFILMORT 4,117, QTDFILVIVO 3,024, QTDPARTNOR 1,991, QTDPARTCES 2,428, QTDGESTANT 1,458, IDADEMAE 278, IDADEPAI 401, PESO 112; means and medians unchanged to the second decimal (the sentinels were
outside the domain already: the state of the count, not the average, was wrong).

**3. APAC laboratory and clinical measures** (ATD 15,579,053 rows, 2014-08 to 2025-12; AN 5,652,863, 2009-2014; AM 74.8 M and AQ 9.6 M, 2024-2025). Fills: zero in 17.0% (HB), 19.8% (fósforo), 30.4% (Kt/V),
23.4% (TRU), 22.2% (albumina), 25.3% (PTH) of ATD's rows, in 11-14 spellings; `9999` on 14,940 rows, **14,939 of them in five of the six fields at once**; AN's all-nines of each field's width (ALTURA 999,
PESO 999, DIURES 9999, GLICOS 9999, ALBUMI 99) on **9,091 lines in all five**. Alagoas's N18 authorisations (the dialysis audit's, 8,192 here for the audit's 8,285), base then branch, mean / median / sd of the
valid: HB 18.84 / 10.0 / 52.77 (audit: 18.6 / 10.0 / 52.7) then 8.44 / 10.0 / 3.30; albumina 19.08 / 10.0 / 37.02 then 3.55 / 4.0 / 2.00; TRU 27.59 / 10.0 / 170.0 then 19.63 / 10.0 / 29.95. All ATD events:
HB 42.69 / 10.0 / 444.1 then 10.34 / 10.6 / 2.75 (1,006,702 not recorded, 2,205,812 outside, mostly other scales); albumina 83.66 / 3.6 then 3.74 / 4.0 / 0.71; TRU 475.7 / 59 then 62.5 / 68.1 / 23.0. AN
all UFs: HB 13.30 / 10 then 10.63 / 11 / 2.38; albumina 10.75 / 4.0 / 17.0 then 3.64 / 4.0 / 0.77; TRU 588 / 65 then 67.3 / 69 / 15.2; ALTURA 125.5 / 160 / 69.5 then 160.7 / 164 / 22.9; PESO 71.4 / 60 / 116.8 then 64.5 / 63 / 15.7 (domain 1-300 kg: 163,983 values at 300-998 are tenths). Others:
AM_ALTURA 1,079,127 zeros, AM_PESO 160,946 zeros and 1,181,452 values at 300-998 (71.2 / 70 / 19.6 against 80.2 / 70 / 77.5), AQ_TOTMPL 11,251 `999`, ACF diameters 418 / 419 of 1,042 zeros, AB_IMC 49 of 700. What stays wrong: phosphorus, Kt/V and PTH keep means of 115, 21 and 587 (no
document gives their unit or range, so no domain: OQ 82); and the Alagoas medians of 10 are a **default**: four establishments file 10 in every laboratory field (albumin 10 g/dL on 98.8% of one Paraná clinic's
11,507 authorisations, 99.1% of a Paraíba clinic's 6,956, 60.8% of Alagoas's CNES 2010615's 6,527, 62.9% of Goiás's 4,168; 26,799 events), which the albumin domain excludes and the haemoglobin of 10 beside it
escapes. Haemoglobin scales: 12.0 M positive values in 1-25, 0.77 M in 25-250, 0.08 M in 250-2,500, 15,000 at 9999; comma decimals (`10,5`) do not parse as numbers in PegaSUS's `TRY_CAST`.

**4. ATD's event type, on ATD** (every UF; `event_atd.out`). 5,590,747 APACs in 15,579,053 rows (one row 421,205, two 352,991, three 4,814,579). Type 1: 5,491,060 rows, month of `AP_DTINIC` = `AP_CMP` on all
of them; 5,491,059 APACs hold one, always on the earliest competence; type 3: 31,842 single-row APACs; 67,846 APACs hold neither (begun before 2014-08); 88 rows type 4. The AQ figure the evidence quoted
(2,921 of 2,921) is replaced by these. `AP_CIDCAS` on the authorisations of type 1 or 3: `0000` 76.2% (2014), 79.9%, 82.1%, 85.5% (2021), 87.5% (2023), 88.1% (2025); N18 23.7%, 17.0%, 12.8%, 10.2%, 8.7%, 8.4%; any
other N under 0.5%. `ATD_CARACT` 1: 42.9% (2014), 38.7%, 28.8% (2021), 17.8% (2023), 16.8% (2025); of 566,867 patients 403,686 hold a flagged APAC, 173,217 two or more; 66% of first APACs and 24% of later ones
carry it; the first dialysis precedes a flagged authorisation by a median 1.35 years (31.4% within 90 days) against 2.74 for continuity. The audit's 91% (N18 in Alagoas) is the clinics that code N18; nationally it is
17.8% in 2023. 2,029 `(AP_AUTORIZ, AP_CMP)` pairs occur twice (DATA_SOURCES said none).

**5. First competence.** `ATDAC1408.dbc` (`AP_MVM` 201408-201412: 95,928 to 97,543 rows a month, 27 UFs); 2014 has five competences. Recorded as a gotcha of SIA.ATD (printed by `info`) and in DATA_SOURCES 1.11;
the publication records (`publication_coverage.json`, five datasets) hold completeness ratios, not first months.

**Regression.** Labelled reads of curated columns (SINASC-DN 2016 CONSULTAS/ESCMAE/GESTACAO, SINASC-DN 2014 ESTCIVMAE/GRAVIDEZ/RACACORMAE, SIHSUS-RD AL 2019 SEXO/RACA_COR/CAR_INT) are byte-equal on the base and the
branch; the old suite (`-m "not network"`, run once at the end) passes: 1,730 tests, 28 skipped, none failed. Left: DNR/DNRIG 1994-95 declare nothing (no records read); RACACOR `9`, MESPRENAT 10, TPROBSON 12, TPDOCRESP 0 (OQ 83).
