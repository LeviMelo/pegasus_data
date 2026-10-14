# Garbage codes as a declared classification and IPCA for constant reais (2026-10-14)

Regime: branch `fix7-garbage-prices` (from 71873d6); `pegasus_core_data` read-only (SIM-DO and SIH-RD lake columns through DuckDB); the SIDRA
fetch into a scratch data home; sources downloaded to scratch (the two supplements through Europe PMC's REST API, `supplementaryFiles`: PMC itself answered the WebFetch tool
with a browser check, `curl` with a browser User-Agent to `ebi.ac.uk/europepmc` was served). Decisions: ADR-0182, ADR-0183; what the sources
are: DATA_SOURCES §11 and §6.4.

**The case.** An Alagoas study (SIM-DO 2014-2023, residence): AMI is 76.4 % of ischaemic heart disease deaths in 2014 and 88.7 % in 2022; the
ill-defined share (R00-R99) moves between 3.6 % (2018) and 6.4 % (2022). Nothing said which of the two moves was recording.

## Garbage codes

| what | measured |
|---|---|
| list found | França et al. 2020 Suppl. file 1 (GBD 2017, levels 1-4, 4 range lists) and Johnson et al. 2021 Suppl. appendix Figs 3-4 (GBD 2019), both CC BY 4.0; IHME's GHDx mapping is non-commercial (ADR-0140), not shipped; Naghavi 2010's Annex 3 has garbage codes with redistribution targets but no levels, not used |
| the reading of a range | closed interval in ICD-10's order with the point; reproduces França's Table 1 for **Brazil 2016, SIM-DO 1,309,774 deaths** (all-cause 736,842 male, 572,359 female: equal): 16 of 18 leading groups to the unit (pneumonia 40,227; stroke 37,219; I50 13,798; I10 11,783; cancer unspecified 10,229; sepsis 9,769; cardiomyopathy 5,857; Y20-Y34 7,336; V89 5,850; R-codes level 2 3,829 ...), R-codes level 1 39,450 against 39,447, diabetes 22,958 against 22,928 |
| levels, Brazil 2016 (male / female, mine against published) | level 2 **33,076 / 27,394, equal**; level 1 92,958 / 80,552 against 92,102 / 79,980; level 3 23,420 / 21,929 against 24,323 / 22,530; level 4 115,815 / 111,429 against 115,980 / 111,493; garbage total 265,269 / 241,304 against 265,481 / 241,397 (0.03 % and 0.02 % of all deaths). The residual is ~900 deaths moved between levels 1 and 3, not located; two other readings (a subcode inherited by a three-character endpoint) worsen it and make 16-29 codes fall at two levels, the interval reading makes none |
| the supplement's note | J47, K70.4-K70.9, E12-E15, K73 are printed at level 1 and "classified in other levels": applied, printed level kept; reading K73 as K73-K73.9 is what makes level 2 equal |
| two editions against each other | GBD 2017 5,839 codes, GBD 2019 membership 5,889 (the tree-built tables 5,835 and 5,891 with the validity rule): 5,821 shared, 68 only in 2019, 18 only in 2017 (B34.2, K73, I27.0, G21.0, U07.1 ...) |
| GBD 2019 classes | Fig 4 lists 4,256 of Fig 3's 5,889 codes (147 packages; 26 codes in two classes); 1,633 members have none: S00-T98 1,459, the mycoses, I50.0 and I50.1, N17; they are 23,310 of 518,806 member deaths of Brazil 2016 (I50.0 13,661, N17.9 4,684, I50.1 2,361) |
| the Ministry's `SIM-POUCO-UTEIS` (3,090 codes) | 2,498 in GBD 2017 (81 %): Tp 5 381 of 389, Tp 3 19 of 19, Tp 1 1,586 of 1,897; Tp 4 includes D00-D09 in-situ neoplasms, in neither GBD list |
| `garbage_codes()` | 1.0 s the first call (ICD-10 tree + YAML), 0.01 s after |

**What the list showed about the case (Alagoas, residence; share of all deaths).**

| year | deaths | R00-R99 | GBD2017 level 1 / 2 / 3 / 4 | GBD2019 members | of them level 1-2 | AMI of IHD |
|---|---|---|---|---|---|---|
| 2014 | 19,065 | 5.7 | 11.8 / 4.7 / 3.4 / 23.8 | 44.3 | 14.9 | 76.4 |
| 2016 | 20,769 | 4.5 | 11.3 / 5.3 / 3.3 / 23.7 | 44.3 | 14.8 | 82.4 |
| 2018 | 19,411 | 3.6 | 10.8 / 4.9 / 3.0 / 20.4 | 40.1 | 14.0 | 83.4 |
| 2019 | 20,287 | 4.6 | 11.7 / 5.2 / 2.9 / 21.8 | 42.3 | 15.2 | 83.2 |
| 2020 | 24,148 | 6.2 | 12.2 / **19.9** / 2.8 / 16.7 | 37.4 | 15.9 | 86.5 |
| 2021 | 25,090 | 6.0 | 12.5 / **22.5** / 2.5 / 14.5 | 35.6 | 16.7 | 85.5 |
| 2022 | 23,122 | 6.4 | 15.6 / 9.0 / 3.2 / 17.4 | 42.5 | 19.8 | 88.7 |
| 2023 | 21,965 | 4.5 | 13.9 / 6.3 / 3.3 / 17.5 | 41.2 | 18.1 | 86.3 |

- **GBD 2017's level 2 is COVID in 2020-2021:** SIM-DO codes COVID-19 as **B34.2** (Alagoas 3,589, 4,239, 735, 80 deaths in 2020-2023; U07.1 and
  U07.2 do not occur), which GBD 2017 lists at level 2 and GBD 2019 does not. That is why the default edition is GBD 2019 and the 2017 docstring says so.
  A paper reading level shares across 2020 on the 2017 list would have a 15-point recording artefact.
- **The rise of the major garbage share in 2022-2023 is not the B34.2 artefact** (GBD 2019 level 1-2: 15.2 % in 2019, 19.8 % in 2022, B34.2 excluded): 2019 to 2022,
  R99 +330 deaths (658 to 988), septicaemia A41.9 +256 (291 to 547), I10 +223 (644 to 867), R96.0 +109, R96.1 +74, I50.9 +69: of 3,088 and 4,568 deaths at
  level 1-2. Nothing here says why; it says where the change in the AMI share has to be tested against.

## IPCA (SIDRA 1737)

| what | measured |
|---|---|
| series | `price_index_ipca`, table 1737 variable 2266, N1, 562 months 1979-12 to 2026-09, no month missing; first fetch 5.0 s (metadata and one values request), a read after it 1.2 s |
| against IBGE | all 393 months 1994-01 to 2026-09 equal IBGE's `ipca_202609SerieHist.xls` (FTP), including all 144 of 2014-2025; SIDRA's query service: January 2014 3,836.37, December 2020 5,560.59, December 2025 7,403.29; SIDRA's table page shows September 2026 "7.695,82" and "Mês [1/562]" |
| annual mean | 2014 3,953.15; 2019 5,213.61; 2023 6,661.15; 2025 7,300.84 (twelve months); 2026 null (nine months) |
| effect: SIH-RD Alagoas, AIH type 1 (`IDENT` 1), `VAL_TOT` by competence month | 2014 R$ 153.7 million nominal, 2023 222.8 (+45 %); in December 2025 reais 287.8 and 247.5 (-14 %); 2020 195.1 nominal, 268.2 real; 2021 269.4 and 342.9 |

The SIDRA page needs interaction to show another month: two further months were read from the query service (`apisidra`), not from the page.
