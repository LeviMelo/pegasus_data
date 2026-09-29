## ADR-0079: A code table found only in a document is written in the curation

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0072 (compiled
bindings), ADR-0012 (codelists come from the TabWin kits).

**Context.**
- Every label came from a TabWin `.CNV` or `.DBF` table, carried in the label
  pack, or from the lake's reference tables.
- On 2026-09-28 the review of 1,799 inferred descriptions checked them against
  the SINAN NET data dictionaries, the INCA forms and the SISCAN technical
  notes. It found several hundred coded columns whose codes are printed in
  those documents but that no kit carries. Examples:
  - botulism toxin type: 1 A … 7 Outra, 9 Ignorado;
  - the SINAN yes/no flags (1 Sim, 2 Não, 9 Ignorado);
  - the tetanus birth-attendant list.
- Those columns reached the user as bare digits.

**Decision.**
- A variable entry may carry `codes: {code: label}`. Codes are kept exactly as
  written: `"01"` is not `"1"`.
- The loader names the table `CURATED.<SYSTEM>.<FIELD>` and makes it the entry's
  codelist. A coded entry marked `code_system: none` becomes `internal`
  (`semantics/curation.py`: `_parse_codes`, `curated_codelist_id`,
  `inline_codelist`).
- `persist/reference.read_reference_table` answers a `CURATED.` table from the
  package's own curation YAML. So a fresh install labels these columns with no
  catalog, lake or label-pack rebuild.
- A table that exists in a kit is still **bound** by name (`codelist:`), not
  copied. The inline form is for codes that live only in a document.
- The entry's `source_ref` cites the document, as it does for the description.

**Limits.**
- Inline tables have a single vintage and no per-system copies.
- Curation holds one entry per (system, field). A code set that differs
  between two SINAN forms under the same column name cannot yet be expressed:
  for example `HIV`, `TIPO_ACID` or `OUTRO_DES`. On 2026-09-28 no field was
  defined in two curation files, so none collides today.

**What would reverse it.** A kit or pack that carries these tables. The entry
then switches to `codelist:` and the inline copy is deleted.
