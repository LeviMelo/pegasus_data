## ADR-0124: A record's identity is the hash of its own fields, numbered for exact duplicates within its file

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0107. Resolves
OQ-65. Supersedes the identity `_blob_sha256:_row` of ADR-0107 for linkage;
that pair stays as provenance.

**Context.**
- **OQ-65.** A record's identity was `_blob_sha256:_row`, its position in the
  file it was read from. SINASC and SIM publish the same records in a
  national file and in per-state files, so one birth had two identities. The
  national delivery link's 1,505,192 left ids matched none of Sergipe's
  28,524.
- **The lake now stamps `_record_key`** on every row (`normalize/engine.py`,
  2026-10-03): the MD5 of the record's own fields, in name order. Labels and
  provenance are excluded, and a null is hashed as its own marker.
- **Some files publish identical rows.** Over the lake built for linkage
  (2022; SINASC also 2021):

  | dataset | rows | distinct keys | rows sharing a key |
  |---|---|---|---|
  | SIH-RD | 12,520,914 | 12,520,914 | 0 |
  | SINASC-DN 2022 (national file) | 2,561,922 | 2,561,922 | 0 |
  | SINASC-DN 2021 (national file) | 2,677,101 | 2,677,101 | 0 |
  | SIM-DO (national file + SE, AC and RR files) | 1,566,462 | 1,544,266 | 22,196 |
  | CIHA | 20,549,661 | 19,814,612 | 735,049 |

  - **SIM's shared keys are the same death read from two publications.**
    All 22,196 are in exactly two source files, the national one and the
    state's, and none falls within one file. That is the identity working.
  - **CIHA's shared keys are within one file**: 509,124 groups of identical
    rows, most in pairs, some of seven or more.
    - Outpatient records (modality 01): 337,578.
    - Modality 00: 392,203.
    - Admissions: 5,137, of which 131 are among the 98,211 that ended in
      death.
  - Whether CIHA's identical rows are repeated events or repeated filings,
    the source does not say. They are distinct published rows, and one key
    would have merged them.

**Decision.**
1. **A record's identity is `_record_key`.** When a source file holds the
   same key more than once, its n-th copy, in row order, is `key#n`.
   - `linkage/roles.py` (`record_ids`, `RECORD_ID_SQL`) is the one rule.
   - The link engine's `_prepare` uses the same SQL. It numbers before a
     side's filter, so a record's identity does not depend on the spec that
     reads it.
2. **The n-th copy of a record gets the same identity in the national file
   and in its state's file,** since both hold the same copies in the same
   order of appearance.
3. **A row without a key** (a table decoded before the lake stamped one)
   keeps `_blob_sha256:_row`.

**Evidence.**
- **Sergipe SINASC.** All 28,524 keys of the per-state file are found in
  the national file (2026-10-03).
- **The national links.** All seven were recomputed on these keys.
- **CIHA Sergipe 2022.** 21,740 rows give 21,740 distinct identities; 32
  carry a number. The link engine's ids for the CIHA deaths are a subset of
  `record_ids`.

**Consequences.**
- **Stored links computed before the numbering are relinked.** The two CIHA
  links are in the ADR-0121 relink.
- **Changing the numbering rule renames records.** It is fixed here.
