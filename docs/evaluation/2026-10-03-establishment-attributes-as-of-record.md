# Establishment attributes as of the record

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`.
- The FTP data channel was down; CNES.ST came from the mirror (ADR-0122).
- In-session query:
  `query("SIH-RD", period="2022-01", geography="SE", select=["N_AIH", "CNES"], enrich=[enrichment(...)])`.

**What is counted and why.** Each enrichment's resolution status per
admission, and the most common values. An attribute must resolve at the
admission's own competence month, and an empty one must not read as a value.

**Before.**
- Every attribute request raised
  `FileNotFoundError: query requires missing local resource(s): cnes_registry`.
- With that requirement removed, it raised
  `NothingPublished: no lake data for system='CNES' series='ST'`.
- With CNES.ST read through `query()`, `CNES.OWNERSHIP` returned null for
  all 8,512 admissions with status `matched`.

**After (ADR-0125)**, 8,512 admissions:

| enrichment | status | most common values |
|---|---|---|
| `CNES.TYPE` | 8,512 matched | general hospital (05) 7,383; specialised hospital (07) 798; general emergency (20) 271 |
| `CNES.MANAGEMENT` | 8,512 matched | state (E) 5,585; municipal (M) 2,927 |
| `CNES.SUS_LINK` | 8,512 matched | with SUS link (1) 8,512 |
| `CNES.SURGICAL_BEDS` | 8,512 matched | 229 (1,717), 40 (1,304), 0 (727) |
| `CNES.HAS_OBSTETRIC_CENTRE` | 8,512 matched | no 4,809; yes 3,703 |
| `CNES.HAS_NEONATAL_UNIT` | 8,512 matched | no 5,837; yes 2,675 |
| `CNES.OWNERSHIP` (`ESFERA_A`) | 8,512 not_recorded | empty in 2022 |
| `CNES.CARE_LEVEL` (`NIV_HIER`) | 8,512 not_recorded | empty in 2022 |

**Checks.**
- Every SIH hospital has a SUS link, as it must.
- Ownership and care level are genuinely empty in CNES.ST 2022, and now say
  so.
- Time: 101.5 s with the first CNES.ST fetch, 16.5 s with it cached.
