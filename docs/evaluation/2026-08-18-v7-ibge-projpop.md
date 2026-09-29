## 2026-08-18 — V7: IBGE/projpop is UF-level projections, 2000-2070

*Split from docs/history/FINDINGS.md §1 V7 on 2026-09-28; text unchanged.*

### V7 — `IBGE/projpop` · **resolved**

71 files named `PROJUF00.dbf` … `PROJUF70.dbf`, 93,560 bytes each — IBGE population **projections**
keyed by projection year 2000–2070, at UF level.

They do **not** supersede POPSVS: POPSVS is municipal and projpop is not. They complement it for
projected years and for national age structures.

A trap fell out of this. The usual two-digit-year pivot (≤ 40 → 2000s, else 1900s) reads `70` as
1970 and scatters a contiguous series across a century. `naming.infer_two_digit_epoch` chooses the
reading whose expanded years form the tightest contiguous span, per directory — which gives
2000–2070 here and 1996–2023 for SIM.
