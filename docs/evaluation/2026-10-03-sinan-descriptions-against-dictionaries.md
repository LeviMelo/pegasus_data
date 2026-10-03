# SINAN descriptions against the official data dictionaries

**Date:** 2026-10-03.

**Regime:** `scripts/audit_sinan_dictionaries.py` (Sonnet agent; parser
checked by hand on six dictionaries). It compares
`curation/variables/sinan/*.yml` with the dictionary texts in
`sources/dic_text/`.

Artifacts:
- `data/probes/curation/sinan_dictionary_audit.json`, one record per
  variable;
- `sinan_dictionary_review.json`, the hand verdicts.

**Why.** OQ-2: the SINAN descriptions had only been checked for vagueness,
never for correctness. A wrong description is invisible downstream.

**Result:** 2,250 curated variables, 1,587 found in a dictionary.

| verdict | variables |
|---|---|
| contradicts | 45 |
| incomplete (rule-based, about half false alarms when read) | 150 |
| not in dictionary | 663 |

- **Where the contradictions are:** PFA 19, diphtheria 5, `_shared` 5,
  leptospirosis 4, congenital syphilis 4, Chagas 3, cholera 2, one each in
  venomous animals, rabies care and botulism.
- **Not covered:** seven agravos have no dictionary text (espo, exan, ntra,
  pest, sdta, sifg, trac).

**Fixed.** All 45 contradictions plus the cholera pair, 46 variables:
- read against the raw dictionary lines;
- descriptions rewritten, with source `layout_doc` and the dictionary named;
- official and translated names corrected for the 41 per-agravo fields.

Examples:
- Diphtheria `CLI_CORDAO` was "cervical lymph-node enlargement"; it is
  pseudomembrane in the umbilical cord. `CLI_PARALB` and `CLI_PARALP` were
  swapped.
- Congenital syphilis `LABC_EVIDE` was radiological evidence; it is
  *T. pallidum* seen on microscopy. `TRA_DIAG_T` was "infant treated"; it is
  long-bone X-ray changes.
- PFA `CLI_A_*`: not yes/no "altered" flags, but strength, sensation and
  tone coded 1 decreased, 2 absent, 3 normal, 4 increased/paraesthesia, 9.
- Cholera `CS_ANTIB` and `CS_ANTIB_T` were swapped.
- The `_shared` fields `CS_CRISE`, `OUTRO`, `OUTROS`, `OUTRAS` and `CONTATO`
  mean different things per agravo; their descriptions now say which.
