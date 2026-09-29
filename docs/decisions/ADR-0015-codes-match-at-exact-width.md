## ADR-0015: Codes match at exact width; a mixed-width table is split by width, never padded

**Date:** 2026-08-18. **Status:** active.

**Context.** Measured on 2026-08-18 and 2026-08-19:

- `CBO` in the current SIH kit mixes 3,000 three-digit CBO-1994 codes with
  2,813 six-digit CBO-2002 codes in one file (`docs/history/FINDINGS.md` §3b).
  452 reference tables mix widths.
- `SP_ATOPROF` holds 398 distinct 8-character and 400 distinct 10-character
  values; `TPROC` holds 8-character codes (1994 era) and `TPROC10`
  10-character ones (post-2008 Tabela Unificada). Binding either alone leaves
  half the history unlabelled (FINDINGS §3d).
- SIM's 9,740 CID-9 codes and 14,198 CID-10 codes share exactly zero codes, so
  exact matching selects the right classification without knowing a row's
  vintage (FINDINGS §3f).

Implemented with reference tables in `b68e446`.

**Decision.** Codes are never padded and never truncated to make a join
succeed (`docs/history/pegasus_data_ARCHITECTURE.md` §6.4, §18). Reference
tables carry `code_width`; mixed-width tables are flagged as open questions;
`load_reference(..., code_width=6)` keeps a join on one vintage. Where the
width selects the era, both tables are bound and merging them is safe. A
codelist that mixes widths warns and labels only what matches exactly.

**Alternatives.** Zero-padding codes to a common width. Rejected: it merges
CBO-1994 into CBO-2002 and would label codes against the wrong classification.

**What would reverse it.** Nothing foreseen.
