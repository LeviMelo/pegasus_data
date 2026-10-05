# Three defects PegaSUS found by consuming pegasus_data (2026-10-04)

**Regime:**
- **Branch:** `pegasus-core-fixes` (from `linkage` at 14a337f).
- **Inputs:** the maintainer home's IBGE sources (`registries/ibge_points`, `registries/regic`) and `sources/cid10csv_v2008.zip`.
- **Live data:** SINASC records read into PegaSUS's own fresh root.
- **Artefacts:** the rebuilt resources `code_trees.parquet` and `proximity.parquet`, with their manifest entries.

## 1. ICD-10: COVID-19 categories were missing

- **The defect:** `code_structure("ICD10")` held U071, U072, U099 and U109, WHO's 2020–21 subcategories, but not their categories U07, U09 and U10, which the 2008 Brazilian tables never defined. COVID-19 deaths therefore fell outside every chapter, about 700,000 in 2020–21.
- **The check was blind to it:** it caught null parents only, never a parent that names no node.
- **The fix:**
  - `build_code_structures.py` creates the three categories with WHO's titles in Portuguese, `valid_from` 202001, under chapter XXII;
  - it refuses any other subcategory whose category no source defines;
  - it fails on any dangling parent.
- **Result:** 14,563 ICD-10 nodes, none dangling.

## 2. Contiguity: 32 borders had no length

- **The defect:** 64 directed rows of `proximity_graph("contiguity")` had a null weight, e.g. 1303007–1303403 and 2901155–2919157.
- **The cause:** `make_valid` returned a GeometryCollection (polygon plus stray lines) for a few municipalities. A collection's `boundary` is None, so every border length touching one of them was null.
- **The fix:** keep the polygonal part after repair (`_polygonal`).
- **Rebuilt and diffed against the shipped pack:**
  - all 218,271 rows match on keys;
  - no other value changed;
  - nulls went from 64 to 0;
  - 3 of the 32 edges are corner touches (length 0), so zero-length rows rose from 1,022 to 1,028.
  - `municipality_areas` and `regic_cities` are identical.

## 3. `logmoments`: the log-normal accumulator (handoff §4)

**The kind:** `kind: logmoments` stores (n, Σ log m, Σ (log m)²), the sufficient statistics of a log-normal mark.
- A value that is not positive has no logarithm and is left out of the state, as a blank is.
- It finalizes to the mean of log m (`sumlog / n`), because the wire formula admits no `exp`.

**Checked on SINASC AC 2022 birth weight (PESO):**
- the scalar lift/merge and the columnar lift (`_lift_columns`) both give n = 14,389, Σlog = 115,830.827 and Σlog² = 933,132.003;
- direct numpy sums agree to 1e-12;
- the geometric mean is 3,134 g.

No recipe uses the kind yet; a mark aggregate is the next step.

## 4. Roles named a derived column that no table has

- **The defect:** `roles()` upper-cased every declared column, so the derived age stratum `IDADE_anos` (from IDADE and COD_IDADE) was served as `IDADE_ANOS`. Three role files also spelled it that way. A role-driven `count_events` on SIH-RD 2022 failed with `No match for FieldRef.Name(IDADE_ANOS)`.
- **The fix:**
  - the declared spelling is kept (only the linkage cross-check compares upper-case);
  - SIM-DO, SIH-RD, SINAN-DENG and CIHA declare `IDADE_anos`.
- **Result:** the strata now read `IDADE_anos` for SIH, SIM and SINAN.

## 5. Zero-byte placeholders chosen over the real files

- **The defect:** `SIHSUS/2010/XML/` holds 324 `RD*.xml` files of **0 bytes**, listed since 2014. They share their logical ids (`SIHSUS|RD|BA|201003`) with the DBCs in `200801_/Dados/`. `choose_representations` ranks by bytes on the wire, so it chose the empty file every time.
  - SIH-RD 2010 failed with 146 of 324 sources not contributing.
  - The empty XML is on no reachable route (the mirror returns 404), while every DBC probed is mirrored (206).
- **The fix:** a zero-size candidate is dropped when its publication has a non-empty one. A lone empty file still surfaces as empty.
- **Result:** SIH-RD 2010 counts 11,228,060 admissions, plus 129,905 unallocated. The FTP data channel was still filtered on DATASUS's side (`curl -v`: login and CWD answer, PASV ports time out), so the files came from the mirror.

## 6. The Census as a population series (`CENSO`)

**Source:** `sources/census.py`, SIDRA tables 1378 (2010) and 9514 (2022), by municipality × sex × single age (0–100+). Built into PegaSUS's root with `pegasus-data population --series CENSO`.

**Result:** every municipality's sum equals the table's own total.

| census | persons | municipalities | mismatched |
|---|---|---|---|
| 2010 | 190,755,799 | 5,565 | 0 |
| 2022 | 203,080,756 | 5,570 | 0 |

**SIDRA's limits were measured** (DATA_SOURCES). The builder plans each request under 50,000 values by state.

## 7. A record's identity depended on the columns read

**The defect:** `record_keys` hashed the batch it was given, so a projected read gave every record a different `_record_key`. Three selections of SINASC 2022 gave three keys for its first record. A link built in a lake-less home could not be joined back to its records: 0 of 26,055 pairs matched.

**The fix:** a batch missing any of its family's columns carries no content key, so identity falls back to `_blob_sha256:_row`, which every projection of the file shares. Lake builds read full records and keep the content key.
- **The trap that remains:** a read of *all* columns gets the content key. A cohort joined to a link built from a projection must therefore also read with a column list.

**Result:** the infant-death links were rebuilt: 2021 has 26,008 pairs, 2022 has 26,055.

## 8. Downloads resume; SINASC sex has two codings

**`sources.fetch_url`:**
- it retries `http.client.IncompleteRead`, which is not an `OSError` and was never retried;
- it resumes with HTTP Range from the bytes already received (MIDR answers 206);
- it checks the length against Content-Length.

**SINASC `SEXO`** (corrected the same day): the first reading, that national files write M/F/I and state files 1/2/0, is not supported by any file read. DNBR2020-2022 and DNSE2021 all write 1/2/0 (counts in DATA_SOURCES). The 2019 layout lists M/F/I, so both codings stay decoded. No label-pack rebuild is needed for it: inline `codes:` are read from the shipped YAML at translate time, and a fresh home labelled both codings.

## 9. A refused representation ended the read

**The defect:** SINAN dengue 2010 and 2013 returned `NothingPublished`. The cheapest representation (the `Dados_Abertos` CSV) was chosen, its family's schema refused it, and no other was tried.

**The fix** (`retrieve.fetch`): when a read has refusals and dropped alternatives, it repeats without the refused paths, so the next representation answers. A publication has up to four (CSV, JSON, XML, DBC), and ZIKA 2017 refuses two, so the repeat continues while there is a new refusal that has an alternative. A refusal with none stays in the read and in the report.

**Result:** dengue 2013, 1,455,118 rows; dengue 2010, 1,004,314; ZIKA 2017, 31,754 (CSV and XML refused); CHIK 2016, 310,746.

## 10. SINAN dates typed from the DBF header

**The defect:** SINAN dates arrived as text (`YYYYMMDD` from the DBCs, ISO text from the CSVs). The seed carries no profile or ledger, so nothing in a fresh home typed them.

**The fix** (`normalize.engine.build_plan`): a column with no profile takes its container's declaration, and the engine already types a DBF `D` field. The header declares `D` on 213 names in 96 of the 98 SINAN families, and on no other system. `parse_date_array` also reads ISO text and passes a typed date through; the aggregate time axis and the linkage roles accept a typed date.

**Counted before and after** (the old behaviour reproduced by dropping the declaration, same files, date columns only, non-null counts per column):

| series, year | rows | date columns | non-null before = after |
|---|---|---|---|
| LEPT 2002 / 2019 / 2023 | 12,091 / 18,186 / 20,888 | 11 / 26 / 26 | 75,882 / 161,900 / 182,678 |
| CHAG 2005 / 2015 | 6,726 / 4,225 | 5 / 18 | 26,076 / 23,765 |
| ESQU 2012 / 2022 | 8,367 / 2,883 | 14 / 14 | 60,831 / 20,143 |
| ZIKA 2022 | 35,804 | 6 | 176,378 |
| CHIK 2022 | 274,331 | 16 | 1,451,062 |
| DENG 2006 / 2010 / 2011 / 2014 | 411,022 / 1,004,314 / 739,375 / 543,918 | 17 / 11 / 11 / 16 | 2,511,882 / 5,308,263 / 3,892,369 / 2,902,548 |

Every column became `date32`, and no column lost a value (no value failed to parse). Not typed: HANT 1999-2006 declares its dates `N8` (`YYYYMMDD`, `0` for blank; 82 rows in 2003) and a few date-named fields are `C`. A stored link keyed on the old text values would need its record keys rebuilt: `_record_key` hashes the typed value.

## 11. RACACOR labels

**The defects** (found by PegaSUS's race-bridge measurement):
- `translate(system="SIM")` labelled `Bra`, `Amar`, `Indig`: TabNet's own `RACACOR.CNV` abbreviates them.
- SINASC's `RACACOR` pool held a hybrid: the current kit (`NASC_NOV_TAB`) codes 1 Branca, 2 Preta, 3 Amarela, 4 Parda; the older kit (`NASC_ANT_TAB`) codes 1 Amarela, 2 Branca, 3 Indígena, 4 Parda, 5 Preta. `dictionary_conflicts` records the disagreement, the dictionary resolves it code by code, and the codes only the older kit defines survived (5 read "Preta", 6-8 "Ignorado", 0 "Zero").
- The measured pick of a codelist needs half the DISTINCT observed codes decoded, so a column with six extra codes (0, 6, 9, 01, 03, 04) lost all labels in SIM.

**The fix:**
- both layouts' tables are written as `codes:` in the curation (rung 1 of the label decision, ADR-0079), immune to which codes are observed;
- `labelpack` packs only the majority kit of a codelist whose kits contradict each other; the shipped pack is rebuilt in a later slot (the rebuild streams the 22M-row dictionary), so until then `labels.parquet` still carries the hybrid and the abbreviated labels, and only the curated tables above are immune
- SIH `RACA_COR` and SINAN `CS_RACA` need no change.

**Checked** with `translate`, clean codes (1-5, blank) and polluted (0, 6, 9, 01, 03, 04 added), SIM, SINASC `RACACOR` and `RACACORMAE`, SIHSUS `RACA_COR`, SINAN `CS_RACA`: SIM and SINASC give Branca, Preta, Amarela, Parda, Indígena in both, the extra codes stay unlabelled; SIHSUS gives 01 Branca, 02 Preta, 03 Parda, 04 Amarela, 05 Indígena, 99 Sem informação in both; SINAN gives 1-5 and 9 in both.

`translate` labels a column only when the system's curation knows its name (here `RACACOR`, `RACACORMAE`, `RACA_COR`, `CS_RACA`): by design, because the same code means different things in different columns and systems.

## 12. Brasília in SIH-RD before 2018

**The defect:** `MUNIC_RES` holds the Federal District's administrative-region codes (530020 to 530180, 530135) until 2017-12, so Brasília had 11,297 admissions in 2017 against TabNet's 152,622.

**The fix:** the existing `derived` recipe mechanism gained a `remap` kind (`view._remapped`), declared on `MUNIC_RES` as `MUNIC_RES_municipio` with the window 2008-01 to 2017-12. It judges the window by the file's competence, leaves the raw column and every code outside the window as written, and warns when a year alone cannot settle it.

**Checked** on DF files: 2017 holds 11,025 rows 530010 plus 140,876 region codes, 151,901 after mapping against TabNet's 152,622 (the other 721 are in other states' files); December 2017 still has the region codes, January 2018, 2019 and 2022 none. The mapping function was exercised on both sides of the window (2007-12, 2008-01, 2017-12, 2018-01). A translate() read of the derived column was queued behind other work and is not yet checked.
