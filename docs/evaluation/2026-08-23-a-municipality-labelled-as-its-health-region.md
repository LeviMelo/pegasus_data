## 2026-08-23 — A municipality labelled as its health region

*Split from docs/history/FINDINGS.md §3k on 2026-09-28; text unchanged.*

## 3k. A municipality labelled as its health region (2026-08-23)

### Four correct mechanisms produced a wrong answer

`CODMUNRES = 120040` is Rio Branco. It came back **"Baixo Acre e Purus"** — the
health region Rio Branco sits in — and had done for weeks. Nothing was broken.
Each layer did what it was designed to do:

1. `.DEF` binds SINASC's `CODMUNRES` to **145 codelists**, every one at
   confidence 0.9. TabNet declares tabulation axes beside code systems and the
   file format cannot distinguish them, so every axis a municipality can be
   rolled up along arrives as a "binding".
2. `_rank` breaks a confidence tie on name affinity, then **alphabetically**. No
   table is called `CODMUNRES`, so with 145 candidates tied the tie-break that
   actually decided the label was alphabetical order.
3. `CIRAC` sorts 3rd. `BR_MUNICIPALFA` sorts **118th**.
4. `_choose_binding` measures only the first `_MAX_CANDIDATES` (12) candidates —
   a deliberate cost bound, since `.DEF` binds `DIAG_PRINC` to 114 tables.

So the correct table **was bound, was never loaded, and was never measured**.
`CIRAC` — 24 rows, 4 distinct labels — decodes 100% of Acre's municipality codes
and won.

The granularity tie-break added for `CNES → HOSFEDRJ` (§3, "Choosing which
codelist labels a field") was written for exactly this shape and could not fire:
it only ranks candidates that were *measured*. The rollup guard did fire and
named the problem in a warning — which is not the same as not doing it. A caller
who did not read warnings got a region where they asked for a city.

The candidate counts are worth recording, because they are what makes ranking
unusable here:

| column | codelists bound | where `BR_MUNICIPALFA` sorts |
|---|---:|---:|
| `SIM.CODMUNRES` | 156 | 123 |
| `SIM.CODMUNOCOR` | 152 | 119 |
| `SINASC.CODMUNRES` | 145 | 118 |
| `SINASC.CODMUNNASC` | 144 | 118 |
| `SINAN.ID_MUNICIP` | 51 | 11 |
| `SIA.AP_MUNPCN` | 49 | 34 |
| `SIH.MUNIC_MOV` | 33 | 23 |

**The fix is that the link is stated, not inferred.** The variable → decoder
link is a static build object; a municipality column names its table in curation
and ranking never gets to decide. 167 corrections across 36 curation files.

### DATASUS ships six municipality tables and they are not interchangeable

This is the durable knowledge, and nothing in the tree says it:

| table | rows | exact keys | distinct labels | granularity | notes |
|---|---:|---:|---:|---:|---|
| `BR_MUNICIPALFA` | 5,647 | 5,642 | 5,596 | **0.992** | accented, **UF-suffixed** (`Rio Branco, AC`), 5 ranges |
| `BR_MUNICGESTOR` | 5,645 | 5,641 | 5,595 | 0.991 | the same cities **plus** `120000 → 'Acre - Gestão estadual'` |
| `BR_MUNICIP` | 56,753 | 5,721 | 5,660 | 0.989 | ALL-CAPS, unaccented, ~10 duplicate rows per key |
| `MUNICBR` | 12,470 | 6,078 | 5,687 | 0.936 | **41% of rows are ranges**; sentinels read `12eeee AC - gestão estadual` |
| `??_MUNICIP` / `MUNIC??` | ~32–5,130 | — | — | — | one state each. `MUNICAC` is Acre's 32 municipalities |
| `CIRAC` and kin | 24 | 24 | **4** | **0.17** | health regions. A rollup wearing a municipality's key space |

Three consequences:

* **`BR_MUNICIPALFA` is the municipality table.** The UF suffix is not
  decoration: roughly 250 Brazilian city names are shared across states, so
  without it the label is ambiguous exactly where a national analysis needs it
  not to be.
* **The `gestor` columns need `BR_MUNICGESTOR`, not a plain city list.** SIA and
  SIH record the managing authority as a municipality code *with a state-level
  sentinel* — `UF0000`, and `129999`-style variants. In real SIA-PA data
  `120000 → 'Acre - Gestão estadual'` is the **most common value** (40,650 of
  55,963 rows). A plain municipality table has no row for it.
* **`MUNICBR` is kept as a secondary, not discarded.** It holds 436 keys
  `BR_MUNICIPALFA` lacks. 371 are ignorado/exterior variants and 3 are
  gestão sentinels, but **62 are real municipalities**: the Goiás towns
  transferred to Tocantins in 1988 (`520040 Almas (transf. p/TO)`,
  `520210 Araguaína`…). They can only appear in SIM's earliest years, and
  dropping the table would silently lose them.

### A curated codelist that does not exist decodes nothing, silently

A curated `codelist:` **bypasses measurement by design** — it is a human
decision and nothing may widen it. The consequence had not been thought through:
a name that does not ship does not fall back to a bound table. It produces an
empty label column, no warning, and no error.

**56 references were in this state, across 16 distinct names.** Two dominate:

* `ibge_municipio` on **30 columns** (SINAN and PAINEL_ONCOLOGIA) — a name
  invented in curation that was never a DATASUS table;
* `'..._MUNICIP (per-UF IBGE municipality lists)'` on **6 columns** — a **prose
  placeholder** sitting in a codelist list, in SIASUS `pa.yml` and `_shared.yml`.

The rest were near-misses worth recording as a dialect note: `AGRAVNET` for
`AGRAVONOTS`, `IMUNOCOB` for `IMUNOC`, `TPAPAC` for `TP_APAC`, and six
`CADGER**` names for per-state CNES registries that **do not ship at all** —
those are registry-by-design, and the claim was dropped so measurement runs
instead.

`tests/test_every_curated_codelist_actually_exists` now makes this
unrepresentable.

### Per-UF lists were being applied to national data

A separate defect in the same family, and not a rollup — simply the wrong 0.6%
of the country:

* `SIM.MUNIOCOR` and `SIM.MUNIRES` named `AC_MUNICIP` — Acre's 32 municipalities;
* `SINAN.ATE_MUNICI` and `NM_MUNIC_H` named `MUNICAC`;
* `SINASC.MUNI_MAE` and `MUNI_OCOR` named `BR_CAPITAL` — a list of **capitals**,
  so every birth outside one was unlabelled or folded onto one.

### `code_system` disagreed with itself on 14 municipality columns

§5 names "IBGE município" in its own definition of `external`: the code **and**
the label, because the code is a join key. Fourteen columns said otherwise, and
the two ways of disagreeing failed differently:

* **`internal` (4 columns)** *replaces* the code with the label. `SIM.CODMUNRES`
  came back holding `'120001 Acrelândia, AC'` and nothing joinable — while
  SINASC's identically-meant column kept both. The same fact had two shapes
  depending on which system you asked.
* **`none` (10 columns)** means "the value as typed" and skips labelling
  entirely, so ten columns had a municipality table bound and quietly never
  used it.

### Two defects found by reading a produced CSV, not by a test

Both had passed 1,125 tests. Neither had an assertion anywhere on the rendered
*string* a person actually opens.

**A combined value repeated the code.** `--profile report` joins `code – label`,
and many DATASUS `.CNV` tables write the code into the label itself
(`BR_MUNICIPALFA` maps `120001` to `'120001 Acrelândia, AC'`). Every
municipality cell of every report-profile export read:

    120001 – 120001 Acrelândia, AC

`_combine` now skips the prefix when the label already opens with the code and
the next character is a boundary — the boundary check is what stops code `12`
being swallowed by label `'120001 Acrelândia'`, where the match is a coincidence
of digits.

**The data dictionary described nothing on the CLI's default path.** The
`report` profile translates headers *during* rendering, so a dictionary built
from the rendered table was looking up `"Mother's age"` in a curation layer keyed
on `IDADEMAE`. Every entry came out a bare heading with no prose.
`RenderReport.renamed_headers` now carries `rendered → DATASUS`.

### What was measured, and against what

Real fetches against the live tree on **2026-08-23**, not fixtures:

| dataset | rows | result |
|---|---:|---|
| `SINASC-DN` AC 2022 | 28,966 | `120040 → 'Rio Branco, AC'` on 10,706 rows; **0** unlabelled municipality cells; **0** rollup warnings |
| `SIM-DO` AC 2022 | 4,159 | `CODMUNRES`, `CODMUNOCOR`, `CODMUNNATU`, `COMUNSVOIM` all correct, code **and** label |
| `SIH-RD` AC 2022-01 | 3,977 | `MUNIC_RES`, `MUNIC_MOV` correct; `UF_ZI → '120000 Acre - Gestão estadual'` |
| `SIA-PA` AC 2022-01 | 55,963 | `PA_MUNPCN`, `PA_UFMUN`, `PA_GESTAO` — **0 unlabelled of 55,963** each |
| `SINAN-DENG` BR 2022 | 1,405,095 | `ID_MUNICIP`, `MUNICIPIO`, `COMUNINF` all resolve to cities (395 s, 132 cols) |

`999999 → 'Ignorado ou exterior'` on 18,769 SIA rows is the genuine DATASUS
sentinel for unknown/foreign residence, not a decode failure.

Final state: **128 columns** bound to `BR_MUNICIPALFA`, **12** to
`BR_MUNICGESTOR`, **0** phantom codelist references, **0** municipality columns
on a rollup or a per-UF list, 1,131 tests passing, ruff clean.

### The lesson, stated plainly

Every one of these six defects was invisible to the test suite and visible in
the first CSV anyone opened. The suite asserted on column lists, coverage
percentages and report objects — never on the rendered value. Ranking, coverage
and "labelled: yes" are all measurements of the *process*; only the string in
the cell measures the *answer*.
