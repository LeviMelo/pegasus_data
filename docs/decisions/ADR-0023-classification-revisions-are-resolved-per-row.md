## ADR-0023: Classification revisions are bound together and resolved per row; presence in a bound table outranks shape

**Date:** 2026-08-19. **Status:** active.

**Context.** Measured on 2026-08-19 (`docs/history/FINDINGS.md` §3d, §3f):

- 386 of 5,000 sampled SIM `CAUSABAS` values failed ICD-10 shape validation;
  338 of those are valid ICD-9 codes. SIM ran on CID-9 until 1996.
- The proposed 1996 boundary is wrong: `SIM/CID9` spans 1979–1998 and
  `SIM/CID10` 1996–2024, so they overlap for three years.
- SIH has the same problem in another shape: 426 of 1,590 distinct
  `DIAG_PRINC` values are 6-digit numeric CID-9 (`065099` is "650 - Parto
  normal"), shipped as seventeen chapter files.
- The code spaces are disjoint: SIM's 9,740 CID-9 and 14,198 CID-10 codes
  share none; SIH's 7,681 CID-9 codes have zero contradicting labels and zero
  overlap with CID-10.

Implemented in `6fd1d80` (2026-08-19).

**Decision.**
- Both classifications are bound to the column, and exact matching selects the
  right one per row. No year threshold is used. The boundary is recorded as a
  `vintage_note`, read from the dictionary rather than hard-coded.
- **Presence in a bound table outranks shape.** If a codelist bound to the
  column decodes a token, the token is valid; a shape regex is inference
  (`docs/history/pegasus_data_ARCHITECTURE.md` §6.4).
- A value valid under another revision is reported apart from a structurally
  broken one.
- A token rule may name a set of separators (`ATESTADO` mixes `/` and `*`),
  and the separator is chosen by measured coverage.

Result: malformed values across 23 ICD-bound columns fell to 913 of 53,156
(1.72%); `SIM.CAUSABAS` and `SIHSUS.DIAG_PRINC` to 0.

**Alternatives.** A 1996 year boundary. Rejected: the trees overlap.

**What would reverse it.** Two revisions whose code spaces overlap. Exact
matching could then not choose, and the row's vintage would have to.
