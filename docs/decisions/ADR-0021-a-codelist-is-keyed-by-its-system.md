## ADR-0021: A codelist is keyed by its system, and a codelist that maps one code to two labels is refused

**Date:** 2026-08-19. **Status:** active.

**Context.** Sweeping every bound codelist for self-contradiction on
2026-08-19 found 311,844 `(code, window)` pairs across 264 codelists that
carried more than one label (`docs/history/FINDINGS.md` §3e). Grouped by
system as well: zero. Every one was manufactured here. Reference tables had
been keyed on codelist name alone, and thirteen systems ship a `SEXO.CNV` that
disagree (SIHSUS codes sex `1`/`3`, SINASC `1`/`2`, SINAN `M`/`F`), so one
merged table said `1` meant Masculino and Feminino. `ANO` ships in 15 systems,
`MUNICBR` in 11. A second class was cross-vintage: a no-year read merged every
window. Fixed in `5ec4463` ("Refuse to label from a codelist that disagrees
with itself") and `21861fe` ("The SEXO contradiction was manufactured").

**Decision.**
- Reference tables are scoped by system as well as by vintage
  (`lake/reference/<table>/system=<SYS>/window=<w>/`); a field decodes against
  its own system's copy (`docs/history/pegasus_data_ARCHITECTURE.md` §6.3,
  §7.3). **Never key a codelist without its system** (ARCH §18).
- A codelist that maps one code to two labels is not a usable lookup, and is
  refused.
- Stored labels are checked against their own system-scoped binding by a
  standing `verify` assertion (`check_stored_labels_agree`). The one-off audit
  found 149 stored values, 0 contradicting, 0 unverifiable: the build had
  always used a system-scoped cache, so the lake was never poisoned.

**Alternatives.** Codelist-name keys with a global merge. Rejected by the
measurement above.

**What would reverse it.** Nothing foreseen. The same lesson (compare within
the right scope first) recurred for geography (ADR-0049).
