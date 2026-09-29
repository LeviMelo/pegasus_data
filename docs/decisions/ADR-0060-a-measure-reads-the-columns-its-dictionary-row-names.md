## ADR-0060: A measure's source columns are the ones its dictionary row names; a `sum` may declare several

**Date:** 2026-08-30. **Status:** active.

**Context.** The CNES artifact existed to prove the aggregate layer handles
stocks, and it did while measuring the wrong stocks
(`docs/history/FINDINGS.md` §3y). `consulting_rooms` read `QTINST07` and
`beds_total` read `QTINST08`, but the dictionary rows for the installations
grid say those positions are the male and unsegregated rest rooms of the
emergency block. São Paulo showed 1,934 "beds" against its real ~80 thousand.
The error surfaced only once the frontend reduced stocks honestly and the
headline number became readable enough to be visibly absurd. Fixed in
`97e1a27` (2026-08-30).

**Decision.**
- A measure's `field:` is chosen from the column's dictionary row, never by
  position or number. A measure whose field was picked by number is guessed,
  not curated, and a guess inside a correctly working algebra is worse than a
  refusal.
- `field:` on a `sum` measure accepts a list, summed row-wise at lift in both
  the row and the columnar paths; a row where no column parses stays null.
  Only `sum` composes this way; any other kind with several fields is refused.
- The CNES spec reads beds as `QTLEITP1 + QTLEITP2 + QTLEITP3` (surgical,
  clinical, complementary; São Paulo mean 78,594 in 2022) and consulting rooms
  as `QTINST14`–`QTINST18`.

**Alternatives.** None recorded.

**What would reverse it.** Nothing. It is ADR-0009's rule (never guess a
code's meaning) applied to measures.
