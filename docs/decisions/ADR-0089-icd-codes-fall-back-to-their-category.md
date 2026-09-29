## ADR-0089: An ICD-10 code the classification does not list is labelled by its category, and says so

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0087.

**Context.**
- After ADR-0087, SIM cause-of-death lines showed codes CID-10 does not list
  as `(?)`: `R969`, `I100`, `L899`, `C619`. These are subcategories of
  categories that are not subdivided (R96, I10, L89, C61).
- ICD-10 is a hierarchy, and the category still states what the death was.
- The user pointed out that the hierarchy was not being used.
- The general rule remains right: no prefix matching across widths (§6.2). A
  prefix of a CBO code is not its parent. In ICD-10 the prefix is the parent,
  by definition.

**Decision.**
- **Where the fallback applies.** A lookup that includes the canonical `ICD10`
  table is an `IcdLabels` mapping (`view.py`). A 4-character code missing from
  the table falls back to its 3-character category, or to the category's
  `X`-filler form.
- **The label says so.** For example: "Outras mortes súbitas de causa
  desconhecida — categoria R96 (subcategoria R96.9 não consta da CID-10)".
  The category is never passed off as the exact code.
- **The gap stays recorded.** The compile's gap record (`label_gaps`) still
  lists such codes, because they are not exact decodes.
- **No other classification falls back.**

**Result, 2026-09-29.** In the live home, SIM-DO Alagoas 2022: `R969`,
`I100` and `L899` read as their categories, and `CAUSABAS` has no undecoded
codes. At most one `(?)` remains per line, for codes whose category does not
exist either.
