## ADR-0047: One global selector chooses a representation per logical publication; a conflict refuses

**Date:** 2026-08-23. **Status:** active.

**Context.** DATASUS publishes the same data in several physical forms: `.dbc`
and `.csv.zip`, legacy trees and `Dados_Abertos`, `.duck` backups. On the
recovered full catalog, `scripts/audit_representations.py` found 4,422 logical
publications with alternatives, covering 14,446 files, of which 10,024 reads
can be avoided by a deterministic decode-cost preference
(`docs/history/FINDINGS.md` §3m). Grouping must keep archive-member identity;
suffix similarity alone is not proof of equivalence. Representation decisions
had been family-local, so two schema families could each contribute one form
of the same publication (DEFECTS, source-contract closure). Built in
`efbc7c1` and `7bbd076` (2026-08-23).

**Decision.**
- `representations.py` groups candidates globally by logical publication and
  archive member **before** family execution, and chooses the cheapest directly
  readable form (Parquet, DuckDB, CSV before compressed or archive decoding).
  `fetch()` and the lake builder both use the global result
  (`docs/history/pegasus_data_ARCHITECTURE.md` §5.4).
- Archive members remain separate datasets.
- If cheap metadata contradicts equivalence, a `representation_conflicts` row
  is recorded, and runtime and build execution refuse, including for a
  singleton family call. Two same-format objects claiming one publication are
  evidence of a revision, collision or stale mirror, not a reason to prefer the
  smaller file (FINDINGS §3n, first).
- `on_conflict="all"` is the explicit diagnostic escape hatch.
- Same format and same size across two trees is a **mirror**, not a conflict
  (FINDINGS §3w, 2026-08-30: SINASC published byte-identically into two trees
  during a transition).

**Alternatives.** Exhaustive content equivalence. Rejected by the brief as
unaffordable (`docs/history/PEGASUS_NEXT_ARCHITECTURE_BRIEF.md` §5.2).

**What would reverse it.** Nothing foreseen.
