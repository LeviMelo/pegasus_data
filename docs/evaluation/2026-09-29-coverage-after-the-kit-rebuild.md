## 2026-09-29 — Description and decoding coverage after the kit rebuild: undecoded 240 → 34, missing descriptions 441 → 130

**Question.** Across every family-field in the maintainer catalog, how many
are described from a source, and how many coded fields decode meaningfully?
Measured before and after the day's parser fix, rebuild and curation.

**Regime.**
- Maintainer home `pegasus_data_home`.
- Command: `pegasus-data meaning`. The unit is one row per (family, field):
  22,714 rows.
- Artifacts under `data/probes/coverage/`:
  - `2026-09-29-bindings.parquet`: morning, before this work;
  - `rebuilt-cnv.parquet`: after the kit rebuild (`data/logs/rebuild-cnv2.ps1`);
  - `final.parquet`: after re-curating and recompiling CNES, SINAN, SINASC
    and SIHSUS (`data/logs/rebuild-final.ps1`), commit `b9989a3`.
- Opacity (a label with no word once the code is removed) was first measured
  in the second run, and the rule was loosened for the third (ADR-0099).

**What was counted, and why.** A family-field is the unit a user meets. It is
**documented** when a curated description cites a source, and **inferred**
when the description is the curator's reading. For coding, the classes are
decoded, partial, opaque, undecoded, unmeasured, unknown and not coded. The
standing instruction is that every variable be described and every code
translate into a meaningful label.

**Result.**

| | morning | after rebuild | final |
|---|---:|---:|---:|
| documented | 20,787 | 21,074 | 21,074 |
| inferred | 1,486 | 1,510 | 1,510 |
| **missing description** | **441** | **130** | **130** |
| decoded | 8,139 | 8,190 | 8,354 |
| partial | 1,443 | 1,694 | 1,696 |
| **opaque** | — | 219 | **120** |
| **undecoded** | **240** | 34 | **34** |
| unmeasured | 2,843 | 2,845 | 2,778 |
| not coded | 9,608 | 9,602 | 9,602 |

**What remains.**
- **Opaque (120):**
  - SINAN `ID_REGIONA`/`ID_RG_RESI` (71): the state's own regional table
    labels some regions only by number;
  - SIM `GESTACAO`/`SEMANGEST` (24): a coding that changed across vintages,
    left until windows are per vintage (ADR-0099);
  - SIA `PA_DOCORIG` "A.P.A.C.", CNES `CONSELHO` `99` "-", and smaller ones.
- **Undecoded (34):** codes no source lists. Examples: SINAN `LAB_TGO`/
  `LAB_TGP` result codes, CNES `ID_SEGM` placeholders, SIA `APA_MOTCOB`.
  After this measure, `AN_PESO` (a weight), SINAN `UNI_ATENDE` (a CNES code)
  and `CON_DESCAR` (a CID-10 code) were bound correctly.
- **Missing descriptions (130):** mostly the fields in OQ-60 (SIA UO and PQ,
  BASE_AIH1), for which no layout document was found.

**Also found.** `pegasus-data bindings -s …` without first clearing the
systems' rows compiled nothing: it revisits only families with no binding,
and reported 17 failures with exit 0. The command now exits 1 when nothing
compiled.
