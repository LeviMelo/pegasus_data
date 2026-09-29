## 2026-09-28 — The first live runs on a fresh home: the primary interface returned codes without meaning

**Question.** Does pegasus_data work for a person who installs it and follows
the README? It had never been run that way: every earlier check used the
repository's own 3.5 GB data home, which a command run inside the repository
adopts automatically.

**Regime.**
- Script: `scripts/live.py` (written for this), runs `baseline-2026-09-28`,
  `m1-fixes-1` and `m1-fixes-2`; artifacts under `data/probes/live/<run>/`.
- The home was `~/pegasus_live/home`, emptied before the baseline, with the
  working directory outside the repository. Real FTP server.
- Baseline on commit `61f4bfc`. The fixes were applied while the baseline was
  running, so the later scenarios ran with some of them. `sia_pa` onward had
  the width fix. `sinan_tube`'s 51 labelled columns show it also ran after
  the `label_of` gate was removed. The timing and failure findings do not
  depend on this; the label counts of `sia_pa`, `sinan_deng` and `sinan_tube`
  are not a clean baseline.
- Machine: Windows 11, `pegasus` conda env (Python 3.11.15).

**What was counted, and why.**
- Did the call work, and how long did it take? That is the unit that binds
  for a person.
- How many coded columns came back with a `_label` companion, and what share
  of each column's non-empty values got a label (`label_coverage` per
  column)? Meaning is the project's deliverable (CLAUDE.md §3).
- How many warnings the user saw.
- The tables themselves were read, not only the counts.

**Result: the baseline.**

| scenario | s | rows | labelled columns | warnings |
|---|---|---|---|---|
| `metadata`: `info()` ×3, `search()` | — | — | — | **`info()` failed** (`OperationalError`), **`search()` failed** (`FileNotFoundError`); `explore()` worked |
| `sih_rd` `query("SIH-RD", "2023-01", "AL")` | 31.4 | 14,340 | **2** | 39 |
| `fetch_sih`, same data through `fetch()` | 14.2 | 14,340 | 9 `_label` + ~29 replaced in place | 2 |
| `sim_do` `query("SIM-DO", 2022, "AL")` | 17.1 | 23,122 | **3** (not `CAUSABAS`) | 52 |
| `sinasc` `query("SINASC-DN", 2022, "AL")` | 19.1 | 45,742 | 13 | 21 |
| `cnes_st` `query("CNES-ST", "2023-01", "AL")` | 51.0 | 3,996 | 54 | 84 |
| `sia_pa` `query("SIA-PA", "2023-01", "AC")` | **339** | 95,414 | 6 | 52 |
| `sinan_deng` `query("SINAN-DENG", 2022)` | 237 | 1,405,095 | 17 | 70 |
| `sinan_tube` `query("SINAN-TUBE", 2022)` | 26 | 103,382 | 51 | 3 |
| `cli_get` `pegasus-data get SIH-RD …` | 9.8 | — | — | exit 0 |

**Defects found, and their causes.**
1. **`query()` returned codes, not meaning.** `_query_engine/semantics.py`
   dropped every label whose codelist was not the target of a declared
   `label_of` relation. `curation/joins.yml` declares six, so SIH kept 2 of 39
   labellable columns. The gate also cost 12 of the 15 s of a warm `query()`,
   and wrote an adjudication row per column on every read.
2. **Every 3-character CID-10 code went unlabelled.** The renderer filtered
   the codelist to the field's curated token width (4 for `DIAG_PRINC`). That
   dropped I64, J18, I10, F29 and 268 other categories: 1,907 of 14,340
   admissions (13.3%). The codes were in SIHSUS's own table.
3. **The default `fetch()` profile replaced internal codes in place**
   (`MORTE` `0` → `Sem óbito`), discarding the raw value.
4. **`SEXO` was unlabelled in SIH** by a curation decision that read the
   merged tables of every system. SIHSUS's own table is identical in all four
   vintages. The contradiction is RESP's coding (1 = Feminino).
5. **No age in years anywhere in `query()`.** The derived `IDADE_anos` needed
   a codelist for SIH's `COD_IDADE` that does not exist, and `query()` turned
   derived columns off. Two converters existed (`view._derive_age_years`,
   `_age.years_column`) and disagreed on sub-year ages.
6. **SIA's split files were unparseable.** The largest states' monthly
   production is split into parts (`PASP2301a.dbc`, `…b`, `…c`). The part
   letter defeated the filename grammar, leaving 727 files (71 GB: SP, RJ, MG
   since 2015) with no UF and no date. That created 1,013 SIASUS "series",
   and a single-state request spent 5 minutes censusing their strata.
7. **Leaks.** Decoder worker processes outlived the interpreter. Their pipes
   stayed open, and decode spools were cleaned only by the garbage collector.
8. **A fresh install cannot answer `info()` or `search()`**, because they
   need catalog tables and a dictionary database that only a maintainer's
   build has.
9. The old documentation's "183 GiB" tree is wrong: the listed sizes sum to
   991 GiB (`explore()`), and `explore()`'s own totals are right.

**After the fixes (`m1-fixes-2`, same home, blobs cached).**

| scenario | s | labelled | warnings | read in the table |
|---|---|---|---|---|
| `sih_rd` | 10.3 | **39** | 1 | `SEXO_label` Masculino; `DIAG_PRINC` 100% labelled; `IDADE_anos` 48.0 |
| `sim_do` | 8.1 | **52** | 1 | `CAUSABAS_label` "C34.9 Bronquios ou pulmoes NE"; `IDADE` 478 → `IDADE_anos` 78.0 |
| `sinasc` (`m1-fixes-1`) | 7.2 | 31 | 2 | `PARTO_label` Vaginal, `CODMUNRES_label` "270640 Pão de Açúcar, AL" |
| `cnes_st` (`m1-fixes-1`) | 4.8 | 113 | 2 | every labelled column ≥ 99% |
| `sinan_tube` | 17.7 | 51 | 1 | `NU_IDADE_N` 4026 → `IDADE_anos` 26.0 |

What changed:
- The gate was removed.
- The width filter was removed.
- Raw codes are kept.
- SIH `SEXO` is bound to SIHSUS's own table.
- `IDADE_anos` is declared in SIH, SIM and SINAN with its encoding and
  computed by the one converter (completed years).
- `query()` carries derived columns.
- The filename grammar reads the part letter, and the part enters the
  logical identity.
- The decoder pool shuts down at exit.
- Spools are released after reading.

The remaining warning per call is one summary, "(+N more in
RenderReport.warnings)".

**Still open** (STATUS M1):
- `info()` and `search()` on a fresh install;
- SIA's first-request cost until the catalog is re-derived under the new
  grammar;
- low coverage in a few columns: SIH `GESTOR_COD` 7.6%, `TPDISEC1` 13%;
  SINAN `TPUNINOT` 17%;
- `CNES`/`CGC_HOSP`/`PROC_REA` refused as having more than 12 bound codelists.
