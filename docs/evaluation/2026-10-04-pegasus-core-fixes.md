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
