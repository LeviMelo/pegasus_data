## ADR-0020: `COD_IDADE` stays unbound, and no `IDADE_anos` column is derived

**Date:** 2026-08-19. **Status:** superseded (2026-09-28, by ADR-0064). **Amended by:** ADR-0058.

**Context.** The brief pushed a `COD_IDADE` binding as high priority twice and
expected five values from a codelist that "certainly exists". Measured on
2026-08-19 (`docs/history/FINDINGS.md` §3d): six distinct values (0–5), and no
codelist of time units in the 4.0M dictionary rows ingested. The `.DEF` files
bind `COD_IDADE` to `IDADEPUB`, `IDADEBAS`, `IDADEDET` and `IDADE18`, all
TabNet age-**band** axes with 3-character codes; they decode a tabulation
axis, not this column. SIH's own `SEXO`/`COD_IDADE` were also marked
"DELIBERATELY UNBOUND" in curation, and that prose was later made structural
as `code_system: none` (`docs/history/DEFECTS.md`, Status). Settled in
`3201d60` (2026-08-19).

**Decision.**
- `COD_IDADE` is not bound to any codelist.
- A derived `IDADE_anos` column is withheld. The raw columns pass through, and
  the gap is the recorded open question `semantics.cod_idade_units`, naming
  what would close it.
- Recorded as settled and "not to be revisited"
  (`docs/history/pegasus_data_ARCHITECTURE.md` §19 item 8;
  `docs/history/HANDOFF.md` §1).

**Alternatives.** Binding to an age-band table, or deriving years from an
assumed unit. Rejected: with the wrong unit, `IDADE=030` turns
thirty-month-old infants into thirty-year-olds. No derived age beats a wrong
one.

**What would reverse it.** A source that states the unit codes. ADR-0058 later
banded age in aggregates by reading only the "years" and "100+" units and
treating every other unit as under one year. Row-level `IDADE_anos` is still
not derived.
