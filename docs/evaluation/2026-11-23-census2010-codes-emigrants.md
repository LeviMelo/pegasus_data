# Census 2010 sample: the documentation's code lists decoded, and why the emigrants exceed SIDRA 3172 (2026-11-23)

**Regime.** Branch `worktree-agent-af203d67f5e318b14`, the landed lake of the real home read only (DuckDB, 1.5 GB cap), the
held `Documentacao.zip`, SIDRA 3172 fetched with a browser User-Agent; no figure here is from a scratch landing.

## 1. Code lists

The workbooks sit in `Documentacao.zip` under `Anexos Auxiliares/` (nothing was needed from the FTP: the zip is the registry
`census2010_microdata`). `sources/census_codes.documentation_codes` reads them (xlrd, pdfplumber, both declared) and
`scripts/harvest_codes.py --only CENSO2010` writes `curation/codes/censo2010.yml`, the form's harvested dictionary, served as
`CURATED.CENSO2010.<SERIES>.<COLUMN>` and found by the existing binding (`harvested_codelist`), one table shared by the columns
that name it. Only codes of the column's own width are kept. Share of the non-blank values of the whole lake that now decode:

| list | columns (PESSOAS unless stated) | codes | decoded |
|---|---|---|---|
| UF | V6222 V6252 V6262 V6362 V6602 | 30 | 100% each |
| municipality | V6254 V6264 V6364 V6604 | 5,592 | 99.980%, 99.967%, 99.990%, 99.965% (undecoded: `9999999`, 646, 692, 50, 386 persons) |
| country | V6224 V6256 V6266 V6366 V6606; EMIGRACAO V3061 | 195 | 100% each |
| occupation COD 2010 | V6461 | 438 | 100% of 9,151,107 |
| activity CNAE-Domiciliar 2.0 | V6471 | 241 | 100% |
| courses | V6352 / V6354 / V6356 | 90 / 79 / 76 | 100% each |
| religion | V6121 | 150 | 100% of 20,635,472 |
| activity and occupation of Census 2000 | V6472 / V6462 | 222 / 511 | 100% / 99.9995% (undecoded: `6121`, 46 persons) |

Checked by hand against the workbook cells: V6461 `2211` MÉDICOS GERAIS, V6352 `721` MEDICINA, V6254 `1200401` RIO BRANCO and
`3550308` SÃO PAULO, V3061 `8000840` ESTADOS UNIDOS and `8000620` PORTUGAL.

What the workbooks needed, each read from the file and named in the code: (a) three occupation residuals (`299`, `599`, `999`) and
two course fields (`85`, `97`) are numeric cells inside the military branch / general area 0 that lost their leading zero; they
are `0299`, `0599`, `0999`, `085`, `097`, which is exactly what the microdata holds and no other row can be. (b) The migration
municipality list omits Acrelândia (1200013) and Urucará (1304302), 1,099 values in the four columns; the documentation's own
Divisão Territorial lists them and supplies the name. (c) Country `8000826` is printed under five names (ESCÓCIA, INGLATERRA,
IRLANDA DO NORTE, PAÍS DE GALES, REINO UNIDO) and keeps all five. (d) The country list is filed twice; the `Países` copy lacks
ÁFRICA DO SUL and spells four names differently, the complete `Paises` copy is read. (e) V1005's `1`/`2` were labelled
"Masculino"/"Feminino" from a stray cell of the layout; they are "Área urbanizada"/"Área não urbanizada" (layout text) in all four
sources: a wrong label, corrected. Not decoded: V1002, V1003 (the meso- and microregion codes repeat across states: 15 distinct
values for 137 state-meso pairs, so they need the state's code and the Divisão Territorial list) and V1004 (the region list is in no
workbook). The `CD2000` activity workbook has two sheets, `Plan2` (222 codes, covers the data) and `Plan1` (221, a subset with the
same labels): `Plan2` is read.

## 2. Emigrants against SIDRA 3172

The weighted EMIGRACAO total is 560,532.8 (53,777 records in 45,604 households, 28 parts, each one landing, no duplicate part;
AC 169 and RR 165 equal the files' lines); SIDRA 3172 gives 491,645 (men 226,743, women 264,902; its 5,156 municipal rows add to
the same number). Ours is 14.0% above (men +13.8%, women +14.2%) and above in all 27 states, from +3.5% (AP) to +34.4% (PI).

| candidate | test | result |
|---|---|---|
| wrong weight variable | `V0010` against the initial weight `Domic_Universo / Domic_Amostra` of each weighting area (`Frações.xls`) | the initial weights sum to 561,403, 0.16% above ours: the weight is the sample's own, and the file has no other |
| records per emigrant, not per household | households with an emigrant, weighted (`V0301 = 1`): 483,752 | 0.984 of SIDRA nationally, but 0.86 to 1.03 across sampling-ratio classes, and SIDRA is persons, with a sex split a household has not: a coincidence of totals |
| the universe (still abroad, or a period) | filters on departure year, birth year, country, urban, imputation marks | no filter reproduces the 27 states; `V0305 >= 2000` gives 498,343 (1.014) at a mean state error of 6.3%; imputation marks touch 0.1% of the weight |
| duplicated parts | 28 parts, one per state file; 86 identical records within households (0.16%) | not it |
| a census count, not a sample expansion | IBGE's methodology (p. 284): emigration "está nos dois questionários (investigada censitariamente)"; the municipal values | **supported**: Porto Walter (1200435) has 1 sampled record of weight 1.0 and SIDRA says 4; no subset of the file's records gives 4 |

So table 3172 is the count of the Basic and Sample questionnaires together; the microdata file holds only the sample's records,
and their expansion is 14% above the count, rising with the expansion weight (sample-to-universe ratio up to 3.5: 1.08; 3.5-6:
1.10; 6-11: 1.13; above 11: 1.16). Why the expansion overshoots (the sample questionnaire eliciting more emigrants than the basic
one, or the calibration, which does not constrain emigrants) cannot be told from the file, and no reading is claimed. The defect is
not ours: the sum of `V0010` over the records is what the file says. For a total of emigrants use SIDRA 3172; the file serves the
composition (men are 46.0% of the weighted records, 46.1% of the count), the countries and the households. The Census 2010
microdata note's "not reconciled" row is corrected there.
