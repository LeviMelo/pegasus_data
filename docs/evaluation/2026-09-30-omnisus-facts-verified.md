# The omnisus facts, measured on our data

**Date:** 2026-09-30.

**Regime:**
- branch `linkage`, live FTP;
- data homes:
  - `~/pegasus_fresh` for the slices;
  - `~/pegasus_linkage` for national SIM 2022;
  - the repository catalog, read-only, for catalog sizes, schemas and recorded
    conflicts.

**Who measured.** Three measurement agents, each reporting observations apart
from interpretations. Every fix below was checked again before it was made.

**Artifacts:**
- scratch scripts: `verify_a`, `verify_b` and `verify_c` in the session
  scratchpad;
- per-fact counts: below.

**Why this was run.** The survey of omnisus
([what omnisus teaches](2026-09-30-what-omnisus-teaches.md)) routed about
twenty facts to "check before use". A fact about DATASUS enters DATA_SOURCES
only when measured here. A code a fact says is mislabelled is the most
expensive kind of defect: it is invisible downstream.

**Counted, and what was done.**

| fact (omnisus) | measured here | outcome |
|---|---|---|
| SIM age units: the structure document says 1 = minutes | our documents give the same table; the data (ADR-0070) and omnisus's DOM dictionary say 0 = minutes. **New:** the SIM TabWin `IDADE` table labelled 000–099 "Ignorado". National 2022: 2,598 unit-0 deaths, all quantities 1–59, 2,537 on the birth day. | **fixed**: curated 001–099 as minutes, so the label agrees with `IDADE_anos`. AC 2022: 12 of 12 read "N minutos" |
| TABPAIS: three codes named twice | 044 Camboja/Laos, 073 Eire/Irlanda, 081 Falkland/Malvinas, in both kits; the catalog recorded the conflicts, but the country pack kept one name each | **fixed**: `build_countries.py` labels such a code with both names; exactly three labels changed |
| hanseníase `classi_fin` set by the system | SINAN-HANS has no `CLASSI_FIN` column at all (0 of 26 files). The Anexo I quote is verified in `sources/dic_notif_indiv.txt`. `info()` claimed CLASSI_FIN carried the outcome, as it did for 21 other SINAN datasets. | **fixed**: each dataset's text now states its measured count (16 without the column, 6 partial) |
| — | `info()` read curated text without reloading a changed curation; only `fetch` did | **fixed**: `semantics.curation.ensure_current`, used by both |
| AIDABR24 half-empty | reproduced exactly: 21,096 records; 10,623 without `ID_AGRAVO`; ORIGEM 1 10,474 / 3 9,042 / 2 1,580. Our curation described ORIGEM from inference as "current vs migrated from SI-AIDS", with two rare alternates. | **fixed**: the description is now the measurement; the inference is withdrawn and a hypothesis is kept, marked unverified |
| truncated `A50.` | SINAN-SIFC 2022: 614 of 26,515; decoded as category A50, "subcategoria não informada" | recorded in DATA_SOURCES |
| RR June 2022 incomplete | SIH-RD RR 2022-06: 668 AIHs against 4,372 (May) and 4,134 (July); file 50,318 bytes against 252,712–368,638 | recorded in DATA_SOURCES; RR 2022 linkage lacks most of June |
| `ESPEC` 17, `FINANC` 00, `FINALID` 7, 15 `CO_ERRO` codes | each code list confirmed to lack the code: LEITOS 41 codes; SIH FINANC 01, 02, 04–08; FINALID 1–6; MOTERRO 581 six-digit and 60 four-digit codes. None occurred in our small-state slices. | added to OQ-61 |
| `HOMONIMO` 2 unlabelled | we label 0 "Não" and 2 "Sim" from microdatasus (`source='community'`, confidence 0.4). No DATASUS document gives the codes. RR 2024-01: 2 on 39 AIHs, as omnisus counted. | kept: a cited community transcription ranked below every primary source (ADR-0025) |
| `TPIDADEPAC`/`AP_COIDADE` bare codes | we label the unit and quantity together (`IDADEDET`); SIA-AQ AC 2024-01, 686 of 686 labelled | not applicable |
| CADMUN (0,0) coordinates, missing post-2011 municipalities | we ship IBGE's current division (5,571), no coordinates; all five 2013 municipalities checked are present | not applicable |
| `TIPPRE  ` with trailing spaces | our decoder trims the name; all 1,670 rows of PSRR2401 are labelled | not applicable |
| ER `ANO`/`MES` equal to the file's period | ERRR2206: 15 of 15 rows | consistent (one file) |
| `LERBR19`/`LERDBR19` same size | 403,871 bytes each in our catalog | consistent; not hashed |
| impossible dates (2222, 1366) | not in PSRR2401. Queries keep dates as raw strings; the linkage roles parse dates without a range check, so a year 1366 matches only the same mistake on the other side. | noted; no change |
| SINASC `CODESTAB`/`CODANOMAL` width drift | SE 2002 and 2022: `CODESTAB` 7 wide in both; `CODANOMAL` as curated (one 4-character code before 2006, up to five after). Also 2 codes 3 wide in 2002 (`Q02`). The omnisus claim itself was not located. | consistent with the curation |

**Findings.**
- **Two labels were wrong, and each was invisible downstream.**
  - SIM minutes read as "Ignorado": 2,598 infant deaths in 2022.
  - Three country codes silently lost one of their two names.
- **Two curated texts claimed what the data contradict.**
  - `CLASSI_FIN` in 22 SINAN datasets that lack it in some or all files.
  - An inferred meaning for `ORIGEM`.
  
  Both are the kind of unsupported claim the CIHA-residence correction was
  about (EVALUATION 2026-09-30, CIHA residence tested against SINASC).
- **The rest reproduced or did not apply.**
  - omnisus's counts reproduced exactly wherever measured: AIDABR24, RR June
    2022, HOMONIMO's 39 and the MOTERRO sizes.
  - Four of its defects are absent here by design: municipality source,
    trimmed names, composite ages, conflict recording.
