## ADR-0008: Claims about meaning are merged by a source-authority ladder

**Date:** 2026-08-18. **Status:** active.

**Context.** The meaning of a DATASUS code is stated, when it is stated at all,
by several sources of unequal standing: TabNet's `.CNV` codelists and `.DEF`
tabulation files, lookup DBFs inside the TAB kits, SIGTAP, the DEMAS API, PDF
record layouts, community transcriptions, and inference from the data
(`docs/history/pegasus_data_ARCHITECTURE.md` §6.3). They disagree. The first
implementation (`7b9488a`) carried a `SOURCE_AUTHORITY` table; rungs were
added as sources were reached: `manual` with the curation layer (ADR-0018,
`44380a1`), `community` (ADR-0025, `357ab0b`), `layout_doc`.

**Decision.** Every dictionary row carries its source, a source reference, a
confidence and a validity window. Claims are merged by source authority,
lowest number wins (ARCH §6.3):

```
manual(0) → cnv(1) → layout_doc(1) → def(2) → sigtap(3) → dbf_lookup(4)
          → demas_api(5) → pdf(6) → community(7) → semantic_match(7)
          → inferred(8)
```

- `manual` is 0 because a person who has read the form outranks any
  extraction.
- `layout_doc` sits beside `cnv`: a published record layout is a primary
  statement by the publisher.
- `semantic_match` is a candidate, not a claim (ADR-0031).
- A source conflict is never resolved silently: both claims are recorded
  (ARCH §18).

**Alternatives.** Merging by recency or by confidence alone. Neither is
recorded as tried; the ladder was in the first commit.

**What would reverse it.** A measured case where a lower rung is right and a
higher rung wrong often enough to matter. Where this is known in advance, the
ladder is refined rather than inverted. An external canonical classification
ranks beside `cnv`/`def`, not above (ADR-0030).
