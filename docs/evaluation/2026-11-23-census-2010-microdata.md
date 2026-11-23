# Census 2010 sample microdata landed whole, read through `query()` (2026-11-23)

**What.** The four record files of IBGE's 2010 sample (households, persons, emigration, household mortality; 321 variables) are
four intake sources (`census2010_domicilios`, `_pessoas`, `_emigracao`, `_mortalidade` in `curation/intake.yml`), landed with
every variable as filed into the lake as `CENSO2010.DOMICILIOS|PESSOAS|EMIGRACAO|MORTALIDADE`, with a role file each
(`curation/roles/CENSO2010-*.yml`). `intake.py` gained a general `format: fixed` reader (one line a row, columns cut at
declared `positions`); the layout is `census_commuting.record_layouts`, checked at every landing: a position that differs from
the documentation, a layout variable not declared, or a file that is not whole lines of the layout's width lands nothing.
`census_commuting.build` now reads its six columns from the lake (`census2010_pessoas`) instead of parsing the zips itself.

**Regime.** Scratch home (`PEGASUS_DATA_HOME` in the worktree's scratch folder) holding copies of `AC.zip`, `RR.zip` and
`Documentacao.zip` only; branch `worktree-agent-a18c1a3c2d4456beb`; 2026-11-23. The real home was read, never written.

**Landed.** Rows equal the files' own line counts, every unit (the independent figure `_land` checks before the swap):

| unit | households | persons | emigrants | deaths in households |
|---|---|---|---|---|
| AC | 24,339 | 93,675 | 169 | 343 |
| RR | 16,314 | 63,765 | 165 | 236 |

The files are CRLF, 172, 540, 74 and 66 characters wide. Persons AC+RR: 157,440 rows, 288 columns, 9.6 MB of Parquet (about
60 bytes a row; the national 20 M persons are about 1.3 GB); RR's person file (34 MB) lands in 13 s. No value failed its declared
type (`unparsed` empty). A person finds its household through `(V0001, V0300)`: unique in both states, no person without a
household, no household without a person, same weighting area (V0011).

**Against published figures** (SIDRA; `query()` then a weighted sum of V0010, the sample weight with its 13 implied decimals):

| tabulation | ours | SIDRA | |
|---|---|---|---|
| population AC / RR | 733,559.0 / 450,479.0 | 733,559 / 450,479 (table 136) | equal |
| AC sex by situation (6 cells) | 259,387 / 272,892 / 108,937 / 92,343 and totals | table 202 | equal to 1e-8 |
| AC race (5 categories) | 171,257.15 / 41,547.12 / 14,404.19 / 490,507.03 / 15,704.39 | table 136: 171,257 / 41,547 / 14,404 / 490,507 / 15,704 | within 0.4 person |
| 22 AC municipalities by race (105 cells) | | table 136, n6 | all within 0.5 person |
| AC private permanent households (V4001 = 01) | 190,643.6 | 190,645 (table 3218) | -1.4 |
| AC / RR emigrants (EMIG, weighted) | 1,352.8 / 1,401.3 | 1,276 / 1,181 (table 3172) | **a census count against a sample expansion, +14.0% nationally (corrected 2026-11-23: `2026-11-23-census2010-codes-emigrants.md`)** |

The weight is calibrated to the census totals by weighting area, so population and sex agree by construction; race, the household
count and the municipal cells are the checks that read the variables. The emigrant totals differ by 6% (AC) and 19% (RR): table
3172's title ("by the people they lived with before emigrating") may restrict its universe, which the layout does not say, so no
reading is claimed and the file's counts stand as filed. The 343 and 236 household deaths were not compared (no table found).

**Commuting outputs, before and after** (AC only, the same scratch home, old code from master against the new): persons 93,675,
weight 733,559.0000000079, work edges 152, study edges 164; `commute_work_2010.parquet` and both `*_answered_other.parquet`
files byte-identical; `commute_study_2010.parquet` equal to 2.8e-14 in a weight (summation order: the lake's rows are sorted by
municipality), the report's counts identical. The national build (27 zips) was not repeated: the read is the same columns,
and the AC run exercises every branch (foreign, ignored, unlisted, same-as-residence, no-code).

**Left.** (1) (Done the same day, see `2026-11-23-census2010-codes-emigrants.md`: all but the meso-, micro- and metropolitan-region codes are decoded.) The variables' code lists that IBGE keeps in separate workbooks (places of migration and commuting, occupation,
activity, courses, religion, weighting-area composition) are named in the roles' notes and not decoded: a code stays undecoded.
(2) A role's property is English where it is a stratum or a key (sex, age, race, residence, weighting area, household control,
sample weight) and `<entity>.<IBGE variable>` elsewhere, so no questionnaire item is translated into a claim the layout does not
make; units are declared for the ages only. (3) The national landing is the maintainer's (`RUNBOOK`).
