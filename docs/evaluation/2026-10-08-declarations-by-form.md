# Missing codes declared by the record's own form, across SINAN

**Date and regime.** 2026-10-08; pegasus-core-fixes; `scripts/propose_missing.py SINAN-<series> 2019-2021`, PegaSUS's data root (`PEGASUS_DATA_HOME=C:\Users\Galaxy\pegasus_core_data`); logs in `data/probes/p1/`.

**What was counted, and why.** The columns of the 15 SINAN series with role files whose missing codes the proposer can declare, and the source each declaration rests on. PegaSUS reads a category column only once its missing codes are declared. A wrong declaration is a wrong label, invisible downstream.

**The rule.** The record's own form outranks the tabulation.
- The tabulation's labels (TabNet's `.CNV`) lump documented and undocumented codes into "Ign/Branco": CONJUNTVIT 5, meningitis lab results 62, CRITERIO 0.
- Where the form's dictionary is harvested (`curation/codes`, `harvested_codelist`), its not-recorded codes are declared. Each disagreement with the tabulation is written in the declaration's comment.
- Where it is not, the tabulation alone declares nothing, and the column stays undeclared.

| series | the form decides | the tabulation only (left undeclared) | they disagree |
|---|---|---|---|
| CHIK | 14 | 62 | 11 |
| HANS | 10 | 5 | 4 |
| IEXO | 18 | 11 | 3 |
| LEPT | 41 | 9 | 2 |
| MENI | 32 | 27 | 0 |
| SIFC | 18 | 12 | 7 |
| TUBE | 23 | 22 | 5 |
| VIOL | 76 | 40 | 7 |
| SIFA, SIFG, ZIKA | 0 | 24 | 0 |
| AIDA, HEPA, LEIV, LTAN | draft roles only | — | — |

- 232 columns were declared.
- Almost every disagreement is the tabulation's `0` (undocumented on the form) lumped with the form's `9`.
- Over the 23 datasets whose coverage runs (PegaSUS `fields.coverage`), columns read rose from 674 to 906; 415 still wait for missing codes and 400 are draft roles.
- The one-source columns need their form's dictionary harvested. Chikungunya's signs share the dengue and chikungunya form, but no source here says so; a declaration resting on that waits for the form.
