# Health pass: 1990s SIH diagnoses, warnings about out-of-period tables, and code lists that exist nowhere

**Date:** 2026-09-30. **Regime:** branch `linkage`, fresh home `~/pegasus_fresh`,
live FTP. Plan workstream C.

**What was run and counted.**
- **Undecoded diagnoses in SIH-RD AC.** `query(..., present="analysis")`,
  counting `DIAG_PRINC` values with no label:
  - 1995-01 (1,971 admissions): 7 undecoded. `205400` (6) and `205842` are
    ICD-9 supplementary V-codes (V54.0, V58.4), present in `CID9_SUP`, which
    was not bound. `618080` is in DATASUS's `CID9XINV` ("Código inválido -
    fora da CID").
  - 1997-06 (2,938): 5 undecoded, all V-codes.
  - Both tables are now bound after the ICD-9 chapters: **0 undecoded** in
    either month; 618080 reads as the invalid code DATASUS says it is.
- **Warnings on every modern SIH query.** "labelled from 2 of 19 bound
  tables; missing CID9_01 … CID9_17": the chapter files end in 1997, so they
  have no version for 2023. A table with no version for the period is no
  longer reported. A table that exists in no window at all still is.
- **What that exposed.** SIH `PROC_REA` / `PROC_SOLIC` (and base_aih1's two
  procedure fields) bound a code list `PROC` that exists in neither the label
  pack nor the maintainer catalog. A scan of every `codelist`/`codelists`
  name in `curation/variables/**` against the pack, the canonical
  classifications and the registries:
  - 429 names referenced; 2 found nowhere;
  - `PROC` removed: procedures decode fully without it (SIH AC 1995-01 and
    2005-01: 0 undecoded);
  - `SIA_UPS_BR` is built at run time from the legacy SIA kits (ADR-0103),
    as designed.
- **Live scenarios for linkage.** `scripts/live.py linkage timeline` both
  pass: the three spine links viable on RR 2022 with both methods, and a
  timeline with a linked event (`data/probes/live/20260930-031959/`).

**Why these counts.** An undecoded code and a warning that fires on every
query are both things a person sees. The first hides meaning; the second
teaches them to ignore warnings, so the real one, a dangling table, went
unnoticed.
