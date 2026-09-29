## ADR-0080: A code belongs to its form; per-form alternatives are chosen per family, never merged

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0072 (compiled bindings), ADR-0079 (inline code tables).

**Context.**
- **A wrong label in production.** SINAN meningitis 2023 rendered
  `CLASSI_FIN = 2` as **"Só Exposição"**, a label from another form. The
  meningitis dictionary says `1 confirmado, 2 descartado`.
- **Why.** The curation bound `CLASSI_FIN` (and `CRITERIO`, `EVOLUCAO`) to a
  list of six tables, one per form. A `codelists:` list means "tables applied
  together" (vintages, widths), so the renderer **merged** them. The first
  table's `2` won; it was the poisoning form's `CLASINTO`.
- **The evidence was available.** Every SINAN NET form has an official "Dicionário
  de Dados" PDF with the code list of every field. Reading those tables
  (`scripts/harvest_codes.py`, pdfplumber) gives 1,264 code tables over 41
  forms. They show the same column name carrying different codes on different
  forms (EVOLUCAO, CLASSI_FIN).
- **Hand transcription was the wrong approach.** On 2026-09-28 the review
  agents began typing these code sets into the YAML by hand, one field at a
  time. That is slower and less faithful than parsing the dictionaries.

**Decision.**
- **Harvested tables.** `scripts/harvest_codes.py` writes the generated
  `curation/codes/sinan.yml`, keyed **series → field**, with each field's
  source PDF. Rows whose codes exceed the declared width are dropped. The
  tables are served as `CURATED.SINAN.<SERIES>.<FIELD>`
  (`semantics/curation.harvested_codelist`).
- **Precedence** for a column of a family:
  1. the variable's own `codes:`;
  2. the family's **own form's dictionary table**, if it decodes at least 95%
     of the column's **rows**. The measure is rows, not distinct values:
     meningitis has 379 rows of an undocumented `8` beside 25,642 documented
     ones;
  3. a hand `codelist:`;
  4. adjudication;
  5. measured weighing.
- **`per_form: true` on a variable.** Its `codelists:` are alternatives. They
  become candidates weighed per family, both at query time and in
  `compile_bindings`, and are never merged. Set on SINAN `CLASSI_FIN`,
  `CRITERIO` and `EVOLUCAO`; stored in `variable_docs.per_form`.
- **Hand codes survive the catalog.** Inline `codes:` are recovered from the
  shipped YAML when docs are loaded from the catalog, so they keep top
  precedence.

**Result, 2026-09-28, SINAN-MENI 2023 (26,629 rows):**
- `CLASSI_FIN` reads 1 confirmado (16,649) and 2 descartado (8,993); the
  undocumented `8` stays raw.
- `EVOLUCAO` reads 1 alta and 2 óbito por meningite.
- BOTU `EVOLUCAO`, `TPNEURO` and `CLASSI_FIN` read from the botulism
  dictionary.

**Open.**
- Ten dictionary PDFs have no series mapping yet, and some layouts (the
  poisoning v6 edition) yield few rows.
- The other systems' layout documents (SIM, SINASC, SIH, CNES) are the same
  kind of source, and are not yet harvested.
