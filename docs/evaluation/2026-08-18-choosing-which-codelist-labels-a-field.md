## 2026-08-18 — Choosing which codelist labels a field

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### Choosing which codelist labels a field

TabNet binds several codelists to one field on purpose: `DIAG_PRINC` binds to the full CID table
*and* to `CID10CAP` (21 chapters), `CID10GRUPO` (blocks) and per-chapter lists; `MUNIC_MOV` binds
to `MUNICBR`, `REGIAO`, `UF`, `CAPITAL` and the health-region roll-ups. These are not conflicts —
they are alternative aggregation levels.

Two rankings were tried and rejected before one worked:

- **By row count** — picks a grouping CNV that maps 14,000 codes onto 275 labels, silently
  relabelling every diagnosis as its chapter.
- **By distinct-label ratio** — picks `GCARDIO` (221 cardiac procedures, ratio 1.00) over `TPROC`
  (7,717 procedures, ratio 0.61), leaving 97% of procedures unlabelled; and `DISTRFEDERAL`
  (21 Brasília regions) over `MUNICBR` (5,653 municipalities).

What works is **observed coverage**: the codelist covering the most of the field's actual value
mass wins, with granularity breaking ties. That is a measurement, not a preference. The other
codelists stay reachable and `describe()` lists them as roll-ups.

Separately, `bind_by_semantic_type` attaches a reference table where the detectors measured
membership in it but no `.DEF` names it — the CID-10 table is bound to `DIAG_PRINC` this way,
recorded as `source='semantic_match'` so the weaker basis stays visible.
