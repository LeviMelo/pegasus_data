# What a paper's Table 1 read wrong: SIH-RD and SIM-DO missing codes, GESTRISCO, schooling (2026-10-14)

Regime: branch `fix5-semantics` (from 0325b7c), read-only on `pegasus_core_data` (lake through DuckDB; labels through `pg.levels` on a
scratch copy of the catalog, curation reloaded there), one raw file `RDAL1607.dbc` (1.09 MB) fetched from the FTP into the scratch
folder. Throwaway probes; the figures are what was run. Decision: ADR-0180. Study read: Alagoas, SIH-RD, DIAG_PRINC I21-I22,
IDENT 1, file years 2014-2023: 9,080 AIHs in the lake (the folder said 9,324, counted by another year rule), 5,373 men.

**Alagoas infarction AIHs, per code, and the share recorded under the declared missing codes** (before: `missing` `[]` or undeclared):

| column | codes held | missing before -> after | recorded before -> after |
|---|---|---|---|
| `RACA_COR` | 99 5,172; 03 3,507; 01 269; 04 75; 02 53; 05 4 | undeclared -> `00`, `99` | 100% -> 43.0% |
| `INSTRU` | 0 9,080 | `[]` -> `0`, `5`-`9` | 100% -> 0.0% |
| `GESTRISCO` | 1 9,080 | `[]` -> `1` | 100% -> 0.0% |
| `VINCPREV` | 0 9,080 | `[]` -> `0`, `7`-`9` | 100% -> 0.0% |
| `CONTRACEP1` | 00 9,080 | `[]` -> `00`, `13` | 100% -> 0.0% |
| `NACIONAL` | 010 9,080 | `[]` (unchanged: NACION3D defines no such code) | 100% |

**1. GESTRISCO.** Raw `RDAL1607.dbc`: `1` on 15,733 of 15,734 AIHs (men 5,850, all `1`); the lake equals the file. SIH-RD 2009-2025, all
states: `1` 99.6-99.9% every year, `0` 10,486-60,925 a year. 2014-2023: `0` on 148,028 of 859,946 AIHs of procedures 0409060186
"laqueadura tubária", 0409060313 "laqueadura na mesma internação de parto normal", 0411010042 "operação cesariana com
laqueadura", on 4,747 of 118,145,000 others; `1` on all 969,672 "parto normal em gestação de alto risco" (0310010047), 9,450,303
"parto normal", 1,571,172 "cesariana em gestação de alto risco" (31 `0`) and 6,581,773 "cesariana" (46 `0`). Among the
laqueadura AIHs `CID_NOTIF` is Z30.2 in 94% of the `0` and 99% of the `1`, an O-chapter code in 5.6% of the `0` against 1.3% of the `1`. Rival reading
(TabNet's `SIMNAO`, `1` Sim): men and every non-obstetric admission would be high-risk pregnancies, and the high-risk and ordinary
deliveries would read alike; it does not survive. Labels now: `0` "Sim, gestação de alto risco (só laqueadura)", `1` "Não (valor padrão
de toda AIH)", `pg.levels` on the scratch catalog; was `0` Não, `1` Sim.

**2. RACA_COR.** The SIH table was bound all along (`RACACOR.CNV`, `describe` -> `RACACOR`): `levels("SIH-RD", "RACA_COR", ["01".."05","99"])`
decodes all six. Asked the codes `0`-`9` (PegaSUS `gateway._value_labels`, whose race branch assumes one digit), it decodes none and warns
"reference table 'RACACOR' matched none of the observed codes": that is the study's "(undecoded)". Not a pegasus_data defect; the width
rule (no padding) forbids the library from guessing. SISAIH01 field 40: 01 Branca, 02 Preta, 03 Parda, 04 Amarela, 05 Indígena, 99
Sem informação; SIM's table is not borrowed. `99` share by year (all states): 34.6, 34.8, 34.1, 35.8 (2009-2012), 29.0 (2014), 22.1
(2019), 19.2 (2022), 2.8 (2023), 0.0 (2024, 2025); `03`: 42.8, 55.2, 57.4 (2022-2024).

**3. Missing codes of the category columns, SIH-RD and SIM-DO** (every `kind: category` of the two roles files, observed codes of 2010, 2016,
2023 against the table's label and the layout; SIHSUS-RJ, the same columns, follows SIH-RD):

| dataset.column | declared missing before -> after | the document |
|---|---|---|
| SIH-RD `RACA_COR` | undeclared -> `00`, `99` | SISAIH01 p. 2/8, 99-Sem informação; `RACACOR.CNV` |
| SIH-RD `INSTRU` | `[]` -> `0`, `5`-`9`; note: 0 also not applicable (98.8%) | `INSTRU.CNV` 0-9 "Ignorado/não se aplica"; SISAIH01 p. 5/8 lists 1-4 |
| SIH-RD `VINCPREV` | `[]` -> `0`, `7`-`9` (99.99%) | `VINCPREV.CNV` "Não classificado"; SISAIH01 p. 5/8 lists 1-6 |
| SIH-RD `GESTRISCO` | `[]` -> `1` | SISAIH01 p. 6/8; `RD2008.DEF` (opposite coding) |
| SIH-RD `CONTRACEP1/2` | `[]` -> `00`, `13` (98.8%, 99.2%; `13`: 111 and 97 AIHs) | `CONTRAC.CNV` 00-99 "Ignorado/não se aplica"; SISAIH01 p. 6/8 lists 01-12 |
| SIH-RD `CNAER` (administrative) | `[]` -> `000` (99.99%) | `CNAEG.CNV` 000-010 "Não classificado" |
| SIH-RD `ETNIA` | `0000`, unchanged; note: 0000 also not applicable (75.7%) | IT_SIHSUS SEQ 85 "se raça cor for indígena" |
| SIH-RD `NACIONAL` | `[]`, unchanged; note: Venezuelans in Roraima 55 (2012) -> 7,604 (2019) | `NACION3D.CNV`: no such code |
| SIH-RD other 36 categories | unchanged (no label says not recorded; `NATUREZA` 00 already) | |
| SIM-DO `SEXO` | undeclared -> `0`, `9`, `I` (1,099 and 432 deaths) | `sim2025.txt` campo 10 "I,0,9 - ignorado" |
| SIM-DO `RACACOR` | undeclared -> `[]` (no code for ignored; 9 on 5 deaths left undecoded) | `sim2025.txt` campo 11 |
| SIM-DO the other 43 categories | unchanged, read against `sim2025.txt`: the documented `9` ignorado is declared (ESTCIV, LOCOCOR, ACIDTRAB, ASSISTMED, CIRURGIA, EXAME, NECROPSIA, FONTE, GRAVIDEZ, PARTO, OBITOGRAV, OBITOPUERP, OBITOPARTO, CIRCOBITO, TPMORTEOCO, MORTEPARTO, FONTEINV, ESC, ESC2010) and no code the layout defines as a category is (LOCOCOR 5 and 6, ESC 5, OBITOPUERP 3, TPOBITOCOR 9 kept); codes it does not define (ESC 0, 6-8; GESTACAO 0, 9) stand as TabNet labels them | |

**4. SIM-DO ESC and ESC2010** (national files 2009-2025): filled counts of deaths by year, `ESC` / `ESC2010`: 2009 892,839 / 0; 2010 949,952 / 0;
2011 1,061,343 / 0 (the column present, empty); 2012 1,091,113 / 952,366; 2013 1,037,636 / 1,017,071; 2014 1,140,754 / 1,055,064; 2025
1,456,433 / 1,444,301. 2014-2025: `ESC` 1 Nenhuma x `ESC2010` 0 Sem escolaridade 2,679,156 deaths and no other pair for `ESC` 1; 2 x 1 3,565,378;
3 x 1 or 2; 4 x 2 or 3; 5 x 4 or 5; 9 x 9 1,869,591; `ESC2010` filled on 98.9% of `ESC`'s 15,938,730 (the rest: 70,688 `ESC` 0 and 103,788 older
form). The reader's "none 5,107 / no schooling 5,014" reads as the same persons plus the older form (`ESC` 1 with `ESC2010` blank: 25,993 of 2,705,149 in 2014-2025, 1.0%). `ESC2010` role years 2011 -> 2012;
`ESCFALAGR1`, `ESCMAEAGR1` 2012 -> 2014 (130 and 2 deaths in 2012, none in 2013).

Not measured: SIHSUS-RJ (not in the lake; its roles copy SIH-RD's); SIM-DO 1996-2008 (not in the lake); the siblings DOFET, DOINF, DOMAT.
