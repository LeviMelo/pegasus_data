## ADR-0221: an axis binding names roles; each dataset's columns come from its roles

**Date:** 2026-11-09. **Status:** active. **Extends** ADR-0217 (the cube reads a dataset's place and time bindings) and
ADR-0219 (a column is declared once). **Request:** the population account's build failed on 1991 (SIM-DOR bound to
SIM's CODMUNRES and DTOBITO, columns its files do not have), and stage 5 of docs/plans/cubes.md (axes from the roles).

**Context.** `semantic_axes` named columns: `residence: {fields: [CODMUNRES]}`, declared once per system and inherited by
every dataset of it. A dataset of another layout inherited columns it does not have. A scan of every roles file found
the default bindings of SIM-DOR, SIM-DORIG, SINASC-DNR, SINASC-DNRIG and SINAN-NTRA wrong that way, and 74 bindings in
all naming columns their datasets' files do not carry (checked in the catalog's schemas: none of them is in the files).

**Decision.**
1. A binding names the roles it binds (`residence: {roles: [deceased.residence]}`); each dataset resolves them through
   its own roles file (`DatasetSemantics._resolved`): SIM's residence is CODMUNRES in SIM-DO and MUNIRES in SIM-DOR. A
   role stated by one column per era binds the latest era's. A binding whose roles a dataset does not carry is absent
   from it, never another layout's column. 162 bindings were rewritten from columns to roles; one (SISCAN's
   `CO_ANO_MES_RESULTADO`, in no roles file) keeps its column.
2. A dataset's bindings are its curated ones, resolved, and every binding its roles imply (`semantics_from_roles`,
   under the role's name); a curated default it does not hold yields to its roles' default, else none.
3. A date written with a two-digit year declares its century on its column (`century: '19'`, SIM-DOR's DATAOBITO and
   DATAREG); the binding carries it to the reader.
4. The cube refuses a bound column its dataset's roles do not declare.
5. A binding names roles and nothing else: what its columns code is their roles'. A place's code system comes from its
   role's codelists (`_place_code_system`); a period's form from its columns: two are a year and a month, one is a year
   (a role whose property is the year, or an intake year), a month (`precision: month` on the role, AAAAMM: a
   competence, whose year does not spill over a billing tail) or a day date whose layout is measured. A binding that
   still states `encoding` or `code_system` is refused. A year and a month held apart pair by their property's stem
   (`admission.processing_year` + `processing_month`), so the roles imply SIH's competence too.
6. The binding names (residence, occurrence, competence, notification...) stay a curated vocabulary: one name gathers
   the roles of different entities across systems (residence is `patient.residence` in SIH, `deceased.residence` in SIM,
   `mother.residence` in SINASC), and a name serves place and time alike (SIM's occurrence is `death.municipality` and
   `death.date`). No role property yields that name, so it is declared, once per system.

**Evidence** (evaluation 2026-11-09-principles-audit-defects, row "axes from roles"). Of 157 curated datasets' bindings,
450 resolve to the columns they named, 15 are corrected (SIA-BI/PS/SAD residence is MUNPAC, not the APAC header's
AP_MUNPCN; SIH-SP's and SIH-ER's own columns; SIM's subsets' registration is DTRECEBIM), 74 false ones are gone, and
18 datasets gain a default from their roles (SIA-BI's competence is DT_ATEND). Totals unchanged: SIM-DO 2022 1,544,266,
SIM-DOR 1995 893,868 (+9 unplaced), SINASC-DN 1994 2,571,571, SIH-RD AC 2022 49,547.

**Evidence for 5** (evaluation 2026-11-09-stage-5-one-door). Of 1,239 resolved bindings of 158 datasets, 1,173 are
unchanged; the 59 one-column months gained `precision: month` on their roles (13 CNES `COMPETEN`, SIA's `AP_CMP` and
`AP_MVM`, `PA_CMP`, SIH-CH/CM, 25 SISCAN columns), after which every curated binding resolves as before (4 `yyyymm`
are the reader's equivalent `year_month`); 52 bindings the roles imply are corrected from a day date to a month; 10 false
ones (a year or a month number read as a date) give way to 5 year-month pairs; SRAG's notification and hospital places
declare `BR_MUNICIPALFA`. SIM-DO 2022, SIM-DOR 1995, SINASC-DN 1994 and CNES-ST AC 2022-12 cubes unchanged.
