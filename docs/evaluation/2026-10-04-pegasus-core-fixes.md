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

**SINASC `SEXO`:** the national files (DNBR2021) write M/F/I (layout 2019), and the state files (DNAC2021) write 1/2/0. The codelist held only the numerals, so national reads lost newborn sex. Both are now decoded. The shipped label pack needs a rebuild to carry them.
