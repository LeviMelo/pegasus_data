# SIH 2008–2010 labels: the label pack chose a vintage before a system

**Date and regime.** 2026-10-08; pegasus-core-fixes; PegaSUS's data root (`PEGASUS_DATA_HOME=C:\Users\Galaxy\pegasus_core_data`, which holds no `lake/reference`, so every label comes from the shipped pack); logs in `data/probes/p2/`.

**What was counted, and why.** SIH-RD's sex and race labels in 2008–2010. Without them PegaSUS reads nothing through a label for those years, and the linkage's sex normaliser finds no candidate, so the three SIH links of 2010 were stored as not viable (OPEN_QUESTIONS 73).

**Reproduced small.** SIH-RD 2010-01, AC: 4,412 records, codes as in 2011 (`SEXO` 1/3, `RACA_COR` 01/03/05/99), `SEXO_label` and `RACA_COR_label` null on all 4,412; 2011-01 labelled on all 4,712.

**The cause, found by elimination.**
- Missing bindings were part of it. The 2008–2010 family (`SIHSUS_RD_bc6a3d49df`) had none in that root. `pegasus-data bindings --system SIHSUS` bound SEXO (curated), but the labels stayed null, and RACA_COR came out "none of the 2 bound tables is materialised".
- `_single_lookup(…, "SIHSUS", year)` returned nothing for SEXO and RACACOR in 2008, 2009 and 2010, and the tables for 2011.
- The pack holds SIHSUS's SEXO with windows to 200712 plus an open (current) window, and RACACOR with an open window only. CIH ships both dated 200801–201012.
- `_read_packed` chose the vintage first: CIH's dated window covered 2010, so it won over SIHSUS's current rows, and system scoping then refused CIH's rows as a borrow.

**The fix.** The vintage is chosen among the requested system's own rows and the shared ones (`labelpack._read_packed`). After it:
- SIHSUS SEXO and RACACOR resolve for 1995–2011.
- CIH 2009 still reads its own window.
- SIH-RD 2008-06 and 2010-01 (AC) are labelled on every record, with the same code-to-label pattern as 2011.

The materialised warehouse was never affected: it scopes by system before window. The defect lived in the pack fallback, so in PegaSUS's root and in every fresh install. Its reach, counted on the pack: 378 system-codelists had years inside their own system's data shadowed by another system's dated window.

| system | codelists shadowed | years |
|---|---|---|
| SIHSUS | 137 | 2008–2010 |
| SIM | 85 | up to 2010 |
| SINASC | 54 | up to 2010 |
| SINAN | 36 | up to 2010 |
| others (SIASUS 26, PCE 14, CNES 13, …) | 66 | various |

**Bindings re-decided.** The 246 stored decisions of the 17 families with a "not materialised" decision in that root were cleared and re-decided:
- 203 came back the same; 4 went from none to measured: SIH 2008–2010 `RACA_COR` → RACACOR, SIA `APA_MOTCOB` ×2, SIH-SP `SP_TP_ATO`.
- 20 could not be re-sampled (PNI, PCE: `PublishedEmpty`). Of these, 11 were "none" decisions; the 9 bindings (PNI `ANO` ×8, one curated SIA binding) were restored from the snapshot (`bindings_before.json`) and marked restored.

**The 2010 links, recomputed** (`pegasus-data link … --period 2010 --geo BR --method probabilistic --refresh`; this needed a fix: the CLI passed `settings` twice into `_inherited`). The four runs stored as not viable are now viable:

| link | 2010 | 2011 | 2012 |
|---|---|---|---|
| `sih_deaths_to_sim` | 351,413 pairs, residence agreeing 93.06 % | 369,726, 93.09 % | 374,446, 93.17 % |
| `sim_maternal_deaths_to_admission` | 784 | 804 | 785 |
| `sinan_dengue_deaths_to_sim` | 356 | 288 | 161 |
| `sinasc_births_to_delivery_admission` | 37,314 | 914,551 | 1,490,604 (2013: 1,560,133) |

The delivery link rises from 2010 to 2012 on its own. 2011, untouched by the defect, is already low, so this is how a linking field fills in those years, not the label bug; which field is not yet read. The newborn link's padded scope is computed by `pegasus-core links`. The repo's own data home was not re-bound.
