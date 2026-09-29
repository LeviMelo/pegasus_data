## 2026-08-18 — Codelist coverage is a measured gap list, not a whitelist

*Split from docs/history/FINDINGS.md §3b on 2026-09-28; text unchanged.*

### Codelist coverage is a measured gap list, not a whitelist

`pegasus-data gaps` ranks every undecoded field by observed row mass. Unrecognised lookup tables no
longer fall back to "first two columns": code and label columns are inferred from the data
(uniqueness and length) and recorded as inferred, at reduced confidence.

**CBO resolves at the first step of the search order** — it is already in the TabWin kits, no SIGTAP
or MTE trip needed. And the version question was real: `CBO` in the current SIH kit mixes **3,000
three-digit CBO-1994 codes with 2,813 six-digit CBO-2002 codes in one file**, with `CBO2002` shipped
separately at 2,445 codes. Reference tables therefore carry `code_width`, 452 mixed-width tables are
flagged as open questions, and `load_reference(..., code_width=6)` keeps a join on one vintage.
