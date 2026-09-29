## ADR-0072: One label binding per (system, family, field), compiled from samples and shipped

**Date:** 2026-09-28. **Status:** active. **Supersedes:** ADR-0041 (the
declared decoder link, and refusal above a cap). **Amends:** ADR-0012
(chosen by observed coverage), ADR-0031 (bindings measured and dead ones
withheld), ADR-0061 (one labelling policy).

**Context.** A `.DEF` binds a column to every tabulation axis that mentions
it:
- 31 tables for SIH's `CNES` (`TCNESBR` and 27 per-state partitions of it);
- 34 for `MUNIC_RES` (the municipality names and their regional rollups);
- 294 for PNI's `MUNIC`.

The renderer (`view._select_codelists`) weighed up to twelve candidates
against the values of each file it read, and refused above twelve. The
consequences:
- **124 fields** were never labelled unless curated, among them `PROC_REA`,
  `CNES`, `CGC_HOSP`, every municipality column in SIM and SINASC, and SIM's
  `CAUSABAS`.
- The choice was re-made per file, so two files of one dataset could be
  labelled from different tables. A small state's file can make a per-state
  slice look perfect (FINDINGS §3k: per-UF lists applied to national data).
- The weighing was paid for on every read, and each refusal wrote an
  adjudication row during the read.
- A rollup (a municipality's health region) that was "all there is" was used
  as the label, with a warning.

**Decision.**
- **One decision per (system, family, field)** in a catalog table,
  `label_bindings`, holding the codelists, `basis` (`curated`, `measured` or
  `none`), share, grain, the distinct codes it was measured on, the candidate
  count, the reason, and the sample files. It ships in the seed (ADR-0067).
- **`pegasus-data bindings`** (`semantics/label_bindings.compile_bindings`)
  samples each family's cheapest files, two states where the family is
  partitioned by state. It reads them through `fetch(labels=False)`, so the
  values are exactly what a read normalises, and weighs every bound codelist.
- **`weigh`**, the one algorithm:
  - collapse per-state partitions `X<UF>` whenever the national `XBR` is a
    candidate;
  - measure every remaining table, with no cap;
  - drop **rollups** (grain < 0.5), which name a group and never the code;
  - among identity tables, the best share wins, within 5 points the finest
    grain, then the name closest to the field;
  - below 50% there is no label, and the reason names the best candidate and
    its share.
- **Curation still outranks everything.** A curated codelist is applied
  without weighing and is recorded as `curated` with its measured coverage, so
  the table audits every column.
- **Only conclusive decisions are stored:** curated, unbound, a complete
  decode, or at least five distinct codes measured. Two samples of an empty
  column, or 1 code of 2 decoded, do not become a permanent answer.
- **At read time** the renderer uses the stored row. A family the seed does
  not know is weighed once on the column in hand, with the same function, and
  stored when conclusive. The cap, `_choose_binding` and the per-read
  adjudication writes are deleted.

**Measured** (modern SIH-RD family, first compile):
- 75 fields: 8 curated, 37 measured, 30 with a reasoned none.
- `PROC_REA`, refused before, binds `TB_SIGTAW` at 100% of 208 codes after
  weighing 23 tables.
- `CNES` is none: its establishment directory is held back from the label
  pack by role (ADR-0037).
- `CGC_HOSP`'s only decoding table is a rollup (42% grain), so it is refused.
- The whole-tree compile is its own evaluation entry.

**What would reverse it.** A family whose files disagree about which table
decodes them, so that one decision per family is wrong for some of its files.
Per-vintage rows would then be needed. The schema allows adding the vintage
to the key.
