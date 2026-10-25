# Census 2010 commuting graphs against SIDRA (2026-10-25)

**Run.** `sources/census_commuting.build()` then `validate()`, branch `mob-census` from a1b70be, data home
`pegasus_core_data`, 2026-10-25; the 27 state zips (1.1 GB) and `Documentacao.zip` in `registries/census2010_microdata/`,
output in `registries/mobility/` (the `validate` side files in `registries/census2010_microdata/`; rerun on branch `mobility`
after the merge, same counts) (about 1.5 min to parse). Layout positions are compared with the documentation's
`Layout_microdados_Amostra.xls` (sheet PESS) at every build.

**Variables** (all from that sheet; categories from it too). Weight V0010 (29-44, 13 implied decimals); residence V0001+V0002.
Work: V0660 (328) 3 = another municipality, 4 = foreign country, 5 = more than one municipality or country (no code), with
V6604 (336-342). Study: V0636 (168) 2 = another municipality, 3 = foreign country, with V6364 (176-182). Code list:
`Anexos Auxiliares/Migração e deslocamento _Municípios.xls` (5,589 codes + `8888888` IGNORADO). The sample holds
20,635,472 persons weighing 190,755,799, the Census population.

| layer | edges | weighted total | sampled in edges | answered "another municipality" | foreign | several places | ignored 8888888 | undocumented 9999999 | no code |
|---|---|---|---|---|---|---|---|---|---|
| work | 128,937 | 9,900,450 | 1,070,288 | 10,146,721 (1,088,349) | 35,984 | 903,585 | 242,628 (17,675) | 3,644 (386) | 0 |
| study | 84,993 | 4,178,493 | 508,369 | 4,301,914 (520,229) | 37,059 | n/a | 120,622 (11,549) | 482 (50) | 2,316 (261) |

Edges + ignored + undocumented + no code = every "another municipality" answer, to the person. No answered person had a
code equal to the residence, and none had a code without that answer. 9999999 is not in the code list and is not a
residence: kept apart, never mapped. Two real municipalities the list omits (1200013 Acrelandia, 1304302) appear as
destinations; a destination is accepted when the list or some residence of the census names it.

**Validation.** SIDRA 1615 (work) and 1611 (school), "Outro município", N6, 2010 (IBGE's own tabulation of the same
microdata, rounded to persons). Everyone answering "another municipality", by residence, against it: 5,561 of 5,561
work municipalities (4 published without value) and 5,565 of 5,565 study municipalities agree within one person (the
difference is SIDRA's rounding); totals 10,146,721 vs 10,146,718 and 4,301,914 vs 4,301,916. The graph's out-commuting
equals that figure except for the persons coded 8888888/9999999/no code: 3,634 work and 3,504 study municipalities still
match within one person. Largest gaps: Brasilia 113,076 published vs 16,388 in the graph (work) and 51,117 vs 23,718
(study), because 96,623 of its 113,076 work persons (and 27,398 of 51,117 study) carry the ignored code (the DF is one municipality, so these may be answers naming another administrative region, coded
ignored; not confirmed against an IBGE note, OPEN_QUESTIONS 94); then Sao Paulo (182,352 vs 167,235), Rio,
Guarulhos, all from the same cause.

**Top work edges** (weighted persons): Guarulhos to Sao Paulo 103,196; Nova Iguacu to Rio 97,842; Duque de Caxias to Rio
97,168; Sao Goncalo to Niteroi 92,361; Aparecida de Goiania to Goiania 91,782; Jaboatao to Recife 80,760; Osasco to Sao
Paulo 79,196; Sao Joao de Meriti to Rio 75,203; Contagem and Ribeirao das Neves to Belo Horizonte 71,766 and 67,938:
metropolitan peripheries into their cores, as expected.
