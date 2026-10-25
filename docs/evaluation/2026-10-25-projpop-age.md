# IBGE/projpop: the age was null in every row (2026-10-25)

Reported by nees-gt-ms: `load_population(series="projpop")` returned `age` None for all rows.

**Cause.** The files code `IDADE` as `A` + first age + last age, two digits each (`A0000`, `A0101` … `A8989`, `A9090`).
The population build cast every age to an integer, so each code became null.

**What the code means.** TabNet's own tabulation of these files, `ibge/cnv/projpop2024uf.def`, reads `IDADE` through
`IBGE/cnv/fxidadproj0.cnv`. That table gives 91 single years, the last being `90 anos e mais  A9090-A9999`. So `A9090`
is 90 and over.
- **Declared.** The coding is declared as `age_codes` for `projpop` in `curation/populations.yml`.
- **Decoded.** `sources/ibge.decode_age` turns a code whose two ages are equal into that age. A code that spans
  several ages raises.

**Run.** `pegasus-data population --series projpop` on the real home (`pegasus_core_data`), branch `projpop-age` from
b6d6641.
- **Rows.** 71 files, 348,894 rows: 71 years × 27 UF × 2 sexes × 91 ages. No age is null; the ages are 0-90.
- **Against POPSVS 2025.** POPSVS's top group is 80, so projpop's ages 80-90 were summed to match it. Projpop 2025
  equals POPSVS 2025 summed to UF in 4,368 of 4,374 UF × sex × age cells, with 213,421,037 persons in both.
  - Single ages 0-79 agree, so the decoding is right.
  - The 6 differing cells are in PR and SC, at most 66 persons each (PR women 80+: 165,610 against 165,544).
