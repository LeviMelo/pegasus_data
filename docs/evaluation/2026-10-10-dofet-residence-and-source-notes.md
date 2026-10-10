# SIM-DOFET's residence column across layout generations; source notes (2026-10-10)

Regime: branch `pegasus-core-fixes`, PegaSUS's data root (`pegasus_core_data`), lake years read from it.

**The failure.** `count_events('SIM-DOFET', 'foetal_death', by=['MUNIRES'])` raised `MissingColumnError` for 2010.
The catalog holds 18 DOFET families: residence is `MUNIRES` in the 1979-1995 ones and `CODMUNRES` in all 1996-2026 ones,
and the role file declares both as `deceased.residence` with their years. PegaSUS's gateway collapses a dataset's
stratum roles by property (`{property: column}`), so the last one wins, alphabetically `MUNIRES`. The same two-column
role is declared for DOINF, DOEXT, IBGE-POP (and SINAN-LEPT's infection place). No schema generation lacked a role:
the role file was right, the lookup ignored the years.

**The fix.** `roles(dataset, period=None)` returns only the columns whose years intersect `period` (a year, a pair or
a range; a column with no years always). `roles('SIM-DOFET', period=2019)` has one residence, `CODMUNRES`; the
gateway's `_strata` needs `pg.roles(dataset, period=year)` (a PegaSUS edit; checked by patching: MUNIRES to CODMUNRES).

**Counts** (`count_events(..., by=['CODMUNRES'])`, TIPOBITO 1; every row of every year is TIPOBITO 1, none has a null
residence, so events = the file's rows):

| year | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 |
|---|---|---|---|---|---|---|---|---|
| foetal deaths | 30,929 | 31,613 | 32,229 | 31,981 | 32,145 | 32,994 | 30,210 | 30,620 |

| year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 (PRELIM file) |
|---|---|---|---|---|---|---|---|---|
| foetal deaths | 30,690 | 29,105 | 28,993 | 29,325 | 27,394 | 26,545 | 24,364 | 25,073 |

The fall after 2016 is the series' own; 2025 is the preliminary publication.

**Source notes.** Nota Técnica 133/2022 (`sources/sinan_docs/Nota_Tecnica_Toxoplasmose.pdf`, read with pypdf) is declared
on SINAN-TOXG and TOXC (`event_types('SINAN-TOXG')[0]['source_notes']`); an invalid block raises (eight cases tried).
Rotavirus 30/2024 declared as the second example. Not declared: Creutzfeldt-Jakob 48/2025, Surtos de DTA 45/2024.

**In PegaSUS** (`gateway._strata(dataset, event, year)`, same day): `event_counts('SIM-DOFET', 'foetal_death', 2019)`
reads `CODMUNRES` and accounts for all 29,105 (122 outside a municipality, the rest unallocated by **age**: a foetus
has no age, so DOFET is read as a ratio field without strata). Over SINASC births it is 10.2–10.9 foetal deaths per
1,000 births in 2018–2023, Brazil's known level.
