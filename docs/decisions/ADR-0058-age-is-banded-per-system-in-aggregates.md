## ADR-0058: Age is decoded per system and banded in aggregates, reading only the "years" and "100+" units

**Date:** 2026-08-30. **Status:** active. **Amends:** ADR-0020.

**Context.** The design's canonical aggregate shape, municipality × month ×
{sex, age band}, had never been built because no raw column holds an age in
years (`docs/history/AGGREGATE_PLAN.md` §9 deferred age bands on ADR-0020's
ground). The recipes exposed 3–5 variables of files carrying over a hundred
(`docs/history/FINDINGS.md` §3w). Built in `3599778` (2026-08-30: "The recipe
layer carries the depth: age bands, wide recipes, fast serve").

**Decision.** `_age.py` decodes age per system convention and bands it per
spec:
- SIH: `IDADE` with the unit in `COD_IDADE`;
- SIM: the unit packed into the leading digit of a 3-character `IDADE`;
- SINAN: the same packing in 4-character `NU_IDADE_N`;
- a plain column that already holds years (SINASC's `IDADEMAE`).

The decode rests on one stated fact: every unit below "years" is a sub-year
unit, so any such value lands in the "under one year" band without knowing
which unit it was. Only the "years" and "100+" units are read precisely. An
unparseable or absent age is a level ("Idade ignorada"), never a dropped row.
The row-level `IDADE_anos` column is still not derived.

**Alternatives.** Keeping age out of aggregates until the unit codelist is
found (AGGREGATE_PLAN §9).

**What would reverse it.** A system or vintage in which a code read as
"years" or "100+" means something else. The per-system conventions are stated
in the `_age.py` docstring as documented in curation, while FINDINGS §3d
recorded that no unit codelist was found; that tension is open.
