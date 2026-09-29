## ADR-0025: Community transcriptions are parsed, never executed, and rank below every primary source

**Date:** 2026-08-19. **Status:** active.

**Context.** CNES had 163 categorical columns, a thin record layout, and value
codings that live almost entirely off the FTP tree
(`docs/history/FINDINGS.md` §3h). `rfsaldanha/microdatasus` (MIT), an R
package, encodes value labels as literal `"code" ~ "label"` pairs in its
`process_*.R` files. Parsed on 2026-08-19, it yielded 4,655 pairs across 582
labelled columns, including CNES (163 fields, 726 pairs) and SIA (37 fields,
570 pairs). Built in `357ab0b` ("Read the codings DATASUS never published, from
a source that can never outrank it").

**Decision.**
- microdatasus is **parsed, never executed**.
- It is ingested as `source='community'`, authority 7: below every primary
  source and `pdf`, above `inferred` (ADR-0008). A test drives a
  contradicting community label against a stored `.CNV` one and confirms the
  `.CNV` holds.
- Every entry carries the repository, the **commit SHA** and the file in
  `source_ref`. A transcription without a version is a rumour; with one it is
  a citation someone can re-run.
- A pair belongs to the field whose `if ("X" %in% variables_names)` block
  encloses it; pairs are never taken file-wide.

**Alternatives.** Leaving CNES columns unlabelled when every practitioner can
read them; or running the R code. Both rejected.

**What would reverse it.** A primary source for the same codings. It would
outrank the community rung automatically.
