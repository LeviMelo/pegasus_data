## ADR-0012: The codelist that labels a field is chosen by observed coverage

**Date:** 2026-08-18. **Status:** active. **Amended by:** ADR-0041.

**Context.** TabNet binds several codelists to one field on purpose.
`DIAG_PRINC` binds to the full CID table and to `CID10CAP` (chapters),
`CID10GRUPO` (blocks) and per-chapter lists; `MUNIC_MOV` to `MUNICBR`,
`REGIAO`, `UF`, `CAPITAL` and the health-region roll-ups. These are
alternative aggregation levels, not conflicts (`docs/history/FINDINGS.md` §3).
Two rankings were tried on 2026-08-18 and rejected:

- *By row count*: picked a grouping CNV mapping 14,000 codes onto 275 labels,
  relabelling every diagnosis as its chapter.
- *By distinct-label ratio*: picked `GCARDIO` (221 cardiac procedures) over
  `TPROC` (7,717), leaving 97% of procedures unlabelled, and `DISTRFEDERAL`
  (21 Brasília regions) over `MUNICBR`.

**Decision.** The codelist covering the most of the field's actual value mass
wins, with granularity breaking ties. The other codelists stay reachable, and
`describe()` lists them as roll-ups. Bindings are ranked deterministically
(family-specific first, then confidence, then name affinity, then codelist
name), because SQLite once returned six equally confident CNES `NAT_JUR`
bindings in arbitrary order (ARCH §8, commit `71c5bcf`, 2026-08-19).

**Alternatives.** Row count and distinct-label ratio, both rejected above.

**What would reverse it.** It was amended, not reversed. With 145 candidates
at one confidence and a 12-candidate measurement cap, the correct
municipality table sorted 118th, was never measured, and a 24-row health-region
table won (FINDINGS §3k). ADR-0041 declares the link in curation for the
columns that matter and refuses an uncurated set above the cap.
