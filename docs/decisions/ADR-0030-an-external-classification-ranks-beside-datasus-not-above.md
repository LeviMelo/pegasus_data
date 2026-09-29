## ADR-0030: An external canonical classification ranks beside DATASUS's copy, not above it

**Date:** 2026-08-19. **Status:** active.

**Context.** Classifications DATASUS does not own were researched against
their maintainers (`docs/history/pegasus_data_ARCHITECTURE.md` §14c, commit
`b695b19`, 2026-08-19):

- SIGTAP: the Ministry is the maintainer; keep its own export (ADR-0019).
- CBO belongs to the Ministry of Labour. The FTP table mixes about 3,000
  three-character CBO-1994 codes with about 2,813 six-character CBO-2002 codes
  in one file. A canonical CBO-2002 table from gov.br (`CODIGO;TITULO`) removes
  the ambiguity; DATASUS's copy is kept for the CBO-1994 vintage.
- CNAE: IBGE's API is authoritative and was verified live.
- TUSS and ANVISA registries do not appear in DATASUS public microdata.
- CEP, raça/cor, escolaridade: DATASUS's own codelists, and its copy is the
  right provenance. For CEP no table exists on the tree, the Correios data is
  licensed, and CEP with sex and date of birth narrows a patient to a
  household; recorded as settled (`docs/history/FINDINGS.md` §3d).

**Decision.** Canonical does not automatically outrank DATASUS's copy. If
DATASUS coded a row against its own stale table, that table is what the row
means. An external source is authoritative about the classification and not
about the encoding, so it ranks **beside** `cnv`/`def` for vintage selection.
It is used where DATASUS's copy is absent, ambiguous, or demonstrably a
truncated mirror.

**Alternatives.** Replacing DATASUS's copies with canonical ones. Rejected by
the argument above.

**What would reverse it.** Evidence that DATASUS recoded historical rows to a
newer classification. Its copy would then no longer be what those rows mean.
