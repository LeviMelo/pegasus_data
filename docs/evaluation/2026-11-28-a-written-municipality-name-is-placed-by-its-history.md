# A written municipality name is placed by its history; one reader of a sheet (2026-11-28)

Regime: the working tree on bc1b55f2, the one home (`C:\Users\Galaxy\pegasus_core_data`) read only, a scratch home
for landing (removed after), Windows 11. ADR-0243, ADR-0244.

**What was counted, and why.** Whether IBGE's own record of names can replace a hand list of 43, and whether changing
the reader of a sheet and the placing rule changes any landed value.

| Step | Result |
|---|---|
| IBGE's division read for 25 editions (1994, 2000, 2003-2025) | each year's count equals `municipalities_by_year` (4,974; 5,507; 5,560; ... 5,571); 5,630 names of 5,571 municipalities; every code is in today's universe |
| Names that ever named two municipalities of one state | 0 |
| The 43 hand entries against the history | 26 placed by IBGE's former names; 2 by the 30-character cut; 15 are SENATRAN's own spellings (declared in its `place`) |
| SENATRAN 2015 and 2024 re-landed (new reader, new rule) against the home | 133,704 municipality-months identical (total and motorcycles); 5,570 municipalities placed each year; 34 unallocated rows in both (32 "MUNICIPIO NAO INFORMADO", 2 IBITIUVA) |
| SNGPC rows that name a municipality and are unallocated in the home | industrialized 627,552 of 528,478,139 (22 names); compounded 7,905 of 11,758,269 (2 names); the history places all 24 names (AÇU, ITAPAGÉ, SÃO THOMÉ DAS LETRAS, SANTA ISABEL DO PARÁ...) |
| `scripts/ibge_dtb_vintages.py` through the package's fetch and reader | its JSON byte for byte as before |
| `tests/test_intake_excel.py` | 12 pass |

SNGPC's compounded sales copied to a scratch home and run through `intake` with the name rule in the unit's
fingerprint: 2021 re-derived from the lake's own records, nothing downloaded, 14 s, 2.61 GB peak; 3,455,252 rows and
638,911,239 units as before; unallocated 2,530 to 0, all into 150650 (Santa Izabel do Pará) and 240020 (Açu); no
other municipality's total changed; 2020, not asked, untouched. Not measured: the industrialized sales (528 million
rows) and the main home. Found on
the way and fixed: the first `intake` on an empty home failed with `duplicate column name: widths_json` (twelve
workers open the new catalog at once, each sees the column missing and adds it); `CatalogStore` now accepts a
column another opener added in between. Two empty homes then land SENATRAN 2015 at the first run (motorcycles
237,368,050). IBGE's pairing of 2024 through the new reader: 14,690, 51,638 and 1,478,428, IBGE's Tabela 2.2.

**In the main home (the platform session's run of `intake sngpc_compounded`).** 103 units, 34,232,170 rows,
unallocated 0, 710 s, 2.86 GB peak. 34 units (2019-01 to 2021-10, the months the home held: 11,758,269 rows before)
were derived again from the lake; 69 (2014-2018 and 2026) had never been landed and were downloaded, because a plain
`intake` lands every declared unit and its answer did not tell the two apart. No held month was replaced by a
download. Since then the answer has `landed` (current, from_lake, fetched, not_held, absent) and `replaced_held` (a
held unit that could not be derived again, with why), and `intake --held` downloads nothing. On a scratch copy, 2021
with two units made stale and one removed: `landed` current 7, from_lake 2, not_held 1; no file downloaded.
