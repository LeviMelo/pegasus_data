## 2026-08-19 — COD_IDADE is deliberately unbound

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### `COD_IDADE` is deliberately unbound

The instruction expected five distinct values and that "the codelist certainly exists". Measured:
**six** distinct values (0–5), and **no codelist of time units exists** in the 4.0M dictionary rows
ingested. The `.DEF` files bind `COD_IDADE` to `IDADEPUB`, `IDADEBAS`, `IDADEDET` and `IDADE18` —
all four are TabNet age-**band** axes with 3-character codes labelled `< 1 ano`. They decode a
tabulation axis, not this column.

Guessing here is the one error in the gap list with clinical consequence: `IDADE=030` with the wrong
unit turns thirty-month-old infants into thirty-year-olds. It is recorded as the open question
`semantics.cod_idade_units`, naming exactly what would close it, and the derived `IDADE_anos` column
is withheld until it is. No derived age beats a wrong one.
