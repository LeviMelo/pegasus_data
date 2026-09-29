## ADR-0032: Personal identifiers pass through unmodified, and stay flagged

**Date:** 2026-08-20. **Status:** active.

**Context.** The recovered APAC `.exe` files (ADR-0005) carry columns named as
CPFs and CNSs beside names, postcodes and serology. A first draft on
2026-08-20 (`7cec6a8`) claimed CPFs were published beside HIV results. That
claim was drawn from column names and value shapes, was wrong, and was
withdrawn on 2026-08-21 (`35b1583`) after check-digit measurement
(`docs/history/FINDINGS.md` §3j):

- Patient identifiers are obfuscated: every `*_CPFPCN` column passes the CPF
  check digit 0% of the time, and `AP_CNSPCN` holds no digits at all.
- Professional and director CPFs are real: `APA_CPFRES`, `APA_CPFDIR`,
  `UDI_NFRCPF` and `UDI_DIRCPF` validate 100% over 612 values.
- The patient record is re-identifiable: the executed join `PAC_NUM` ↔
  `EXA_NUM` matched 52/52 one to one, placing `EXA_HIV` beside full date of
  birth, sex, municipality and eight-digit CEP.

**Decision.** Every such column **passes through unmodified**: nothing is
masked, hashed, truncated or dropped (ARCH §18). The detector flags the
columns, the ledger raises an open question (`V.pii_disclosure`), generated
documentation carries the warning, and `FetchReport.sensitive_columns` names
them. Serving microdata over HTTP is a separate exposure decision, off by
default (ADR-0054). Recorded as settled, "do not relitigate"
(`docs/history/HANDOFF.md` §1).

**Alternatives.** Masking or hashing in the library. Rejected (FINDINGS §3j):
it would destroy the evidence that the data was published, since a researcher
with a masked extract cannot tell whether the Ministry or a tool removed the
columns; the remedy is a decision about what DATASUS publishes, which needs the
Ministry to see the finding; and deciding what may be disclosed about a named
person is not a data library's call.

**What would reverse it.** The Ministry answering the referral, which closes
`V.pii_disclosure`, or a change in what DATASUS publishes.
