# What a measure is measured in: units, the month of money, the schooling grade (2026-10-14)

Regime: branch `fix8-units` (from 71873d6), read-only on `pegasus_core_data` (lake parquet columns, one file or one UF at a time; the catalog was not
opened), documents of `sources/` read as text (PDFs through PyMuPDF). Decision: ADR-0184. The probes were throwaway; the figures are what they printed.

**Declared.** 171 measures state a `unit` with the line it rests on (BRL 39, count 58, years 13 outside the derived `IDADE_anos`, grams 15, days 12, score 10, weeks 8,
kg/cm/mm 2 each, g/dL 2, mg/dL, ml, USD 2, months 4) and 55 say why they have none (`unit_unknown`), over 28 datasets: SIH-RD, SIHSUS-RJ, CIHA, the eight
SIM-DO* and four SINASC-DN* layouts, SIA's APAC family (AB, ABO, ACF, AD, AM, AMP, AN, AQ, AR, ATD), PS, SAD and PA. `undeclared_units()` lists 0 measures in them and 666
in the other datasets. `IDADE_anos` (derived whole years, ADR-0070) is `years` in its 82 files. 41 amounts of money name their competence.

| question | measured |
|---|---|
| SIH-RD, Alagoas 2009-2025, 2,959,773 AIHs: the competence | `ANO_CMPT` = the file's year on all, `MES_CMPT` 01-12 and never null |
| the complements are part of the total | `VAL_TOT` = `VAL_SH` + `VAL_SP` + `VAL_SH_FED` + `VAL_SP_FED` on 100% of the AIHs (99.29% without the complements) |
| `US_TOT` is the dollar twin of `VAL_TOT` | `US_TOT`/`VAL_TOT` median 0.295 (p10 0.183, p90 0.575) |
| the `Zerado` columns of the 2008 layout | zero on every AIH 2009-2025: `VAL_ACOMP`, `OBSANG`, `ORTP`, `PED1AC`, `RN`, `SADT`, `SADTSR`, `SANGUE`, `TRANSP`, `UTI_MES_IN/AN/AL`, `UTI_INT_IN/AN/AL`, `TOT_PT_SP`; `VAL_UCI` non-zero from 2013 (49,891 AIHs, at most `VAL_TOT` on all, no summand), `VAL_SH_GES` in 2023 only |
| SIA-AD, Alagoas 2012 (108,946 APACs) and 2025 (55,443) | `AP_CMP` = `AP_MVM` on 94.4% / 91.8%; `AP_CMP` is the earlier month on the rest (up to 3 months, 95th percentile 1), never the later |
| SIM-DO Brazil 2020, schooling grade against level | level 1 holds grades 1-4, level 2 grades 5-8, level 3 grades 1-3; blank for the other levels, SERIESCMAE likewise: a grade read with the level, not a category |
| plausibility of the documented units, SIM-DO / SINASC-DN 2020 | mother's age median 26 / 27 (years), birth weight 1,600 / 3,230 (grams), gestation 32 / 39 (weeks), Apgar 0-10 |
| SIASUS-AN 2009-2014, every UF (5.65 million rows) | `AN_HB` inside the declared domain [1, 2]: 0.92% (median 10 g%): the domain was wrong and is removed; `AN_ALBUMI` > 10 on 28.2% of positive values, `AN_PESO` > 300 on 4.5%, `AN_HB` > 25 on 8.2%: tenths without the decimal point in those records, stated in their `note` |
| `AP_COIDADE`, SIASUS-AD Alagoas 2012 | 4 (years) on 99.7% of 108,946 APACs, but 2, 3 and 5 occur: `AP_NUIDADE` has no single unit and is no measure |

**What the documents give, and do not.** SIH `VAL_*` are in reais (R$, "valores correntes") by the CEM-USP dictionary (`GEOCOD_AIH.pdf` p.5) and the
procedure value of SIA by the SIA manual (`MANUAL_SIA_Maio_2008.pdf` p.46, "Moeda Nacional (Real)"); neither the SIH layout (`IT_SIHSUS_1603`) nor the SIA Informe
Técnico says the currency. Not given anywhere searched: the unit of `US_*` other than `US_TOT`; of `VAL_ACOMP`/`OBSANG`/`PED1AC`/`UCI`, `PA_VL_CF/CL/INC/CRD`;
`IDADEPAI` (the mother's line says "Idade (anos)", the father's does not); `NUDIASOBIN`; `PERMANEN` (1-31 in AL 2020: a lead, not a unit); `AN_TRU`, `ATD_*`,
`AR_SMRD`, `AB_IMC`, `AB_T_PRC*`, `UTI_*_IN/AN/AL`. Each says so in its role.

**Effect on the ledger.** The ledger's `unit` was `BRL` for any money-shaped column, which labelled SIH's `US_TOT` reais; it is now the role's.
