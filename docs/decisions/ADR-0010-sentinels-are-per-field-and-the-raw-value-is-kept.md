## ADR-0010: Normalization is typed per field; sentinels are per field; the raw value survives its label

**Date:** 2026-08-18. **Status:** active.

**Context.** `9` is the missing-value code in some DATASUS columns and a valid
category in others (`docs/history/pegasus_data_ARCHITECTURE.md` §7.1).
Numbers are written as fixed-width text, where a blank means absent, not zero
(`docs/history/FINDINGS.md` §3q, second). `999999 → Ignorado ou exterior` is a
genuine DATASUS sentinel for unknown or foreign residence, not a decode failure
(FINDINGS §3k); sentinels such as `120000 → Município ignorado - AC` are
members of geographic classifications (FINDINGS §3n, second). The contract was
set in the brief and the first commit (`7b9488a`).

**Decision.**
- Types come per field from the ledger.
- **Sentinels are per field, never global**; there is no global sentinel rule
  (ARCH §7.1, §18).
- **The raw value is never discarded** when a label is written (ARCH §18). A
  combined render joins `code – label`; an `external` code system keeps code
  and label side by side (ARCH §8).
- A blank numeric cell becomes null before a cast, so it contributes nothing
  to a sum or to a mean's denominator (FINDINGS §3q, second).
- A column carrying one value on every non-null row is flagged
  `constant_column` and raises a question, because `DIAG_SECUN = '0000'` on
  3,784 of 3,784 rows looks like data and would be counted (FINDINGS §2).

**Alternatives.** A global sentinel list, rejected because the same code is a
category elsewhere. Coercing blanks to zero, rejected because it drags every
mean down invisibly.

**What would reverse it.** Nothing foreseen.
