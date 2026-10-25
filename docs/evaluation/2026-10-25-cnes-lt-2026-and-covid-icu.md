# CNES-LT 2026, the COVID-19 ICU codes and continuation AIHs (2026-10-25)

**Check.** Three gaps from the nees-gt-ms beds audit (its ADR-0057, P-041), on `pegasus_core_data`, branch `cnes-lt` from
586b696, 2026-10-25. What was counted and why: whether a month TabNet publishes is readable here (a study's "latest
month" must not be silently older); whether ICU beds are counted whole (a missing code is an undercount nobody sees);
whether a continuation AIH's length of stay means what a reader would assume.

**CNES-LT 2026.** January to August 2026 were cataloged and readable (`query("CNES.LT", period="2026-01",
geography="RO")` 761 rows); September was not, because the last crawl of the folder was 2026-10-05. `pegasus-data crawl
--prefix /dissemin/publicos/CNES/200508_/Dados/LT` found 27 new files (LT??2609, dated 2026-10-15), then `inventory -s
CNES`, `schemas -s CNES` and `families` put them in `CNES_LT_0b6b4735a0`: 2026-09 reads, RO 768 rows (6,341 existing
beds), SP 8,317 (115,757). A month not yet published was refused with "DATASUS publishes nothing for uf=['RO'],
years=[2026] in CNES/LT; 0 families were searched", which read as "2026 has nothing"; it now says
"...months=[10] in CNES/LT; the latest it lists is 2026-09 (as of the last crawl: `pegasus-data crawl` lists what was
published since)".

**ESP_LEIT 51, 52, 96.** DATASUS's TabNet `leiutibr.def` (Leitos Complementares) binds `TPCO_LEITO` to
`Leitos_compl2.cnv`: 351 "UTI adulto II COVID-19", 352 "UTI pediátrica II COVID-19", 396 "Suporte Ventilatorio Pulmonar
COVID-19"; the label pack's ESP_LEIT predates them. Declared on CNES-LT `CODLEITO` (`codes:`); 51 and 52 added to
`cnes.icu_bed_codes`, 96 left out (ventilatory support, not an ICU bed). The fields rebuilt for 2019-2023:

| December | ICU beds before → after | SUS ICU beds before → after |
|---|---|---|
| 2019 | 46,062 = | 22,877 = |
| 2020 | 48,424 → 68,962 | 23,516 → 32,588 |
| 2021 | 50,873 → 76,110 | 23,952 → 40,146 |
| 2022 | 61,037 = | 30,148 = |
| 2023 | 62,359 = | 31,136 = |

The 2020 and 2021 increases (20,538 and 25,237) are code 51's beds the audit counted (19,859 and 24,559) plus code 52's.

**Continuation AIHs.** SIH-RD SP 2023: on the 2,618,262 IDENT 1 rows `DIAS_PERM` equals `DT_SAIDA` minus `DT_INTER` on
every one; on the 55,876 IDENT 5 rows on 430 (median 30 days against 423 since `DT_INTER`; 33,706 admitted before 2023, one
in 2011): `DT_INTER` repeats the original admission and `DIAS_PERM` counts the AIH's segment. Declared in the note of
`DIAS_PERM`.
