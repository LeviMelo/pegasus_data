## 2026-09-29 — A fresh-home sweep of undecoded values: 1.23 million undecoded cells to 0.56 million

**Question.** On a new install, how many coded values in a small slice of
sixteen datasets come back undecoded (`code (?)`)? After today's parser,
binding and label-pack work, did anything get worse?

**Regime.**
- Scenario: `scripts/sweep_undecoded.py`, one slice per dataset: a state-month
  or state-year, AC where the dataset has states.
- Artifacts, all under `data/probes/live/`:
  - `sweep_undecoded-1.json`: live home `~/pegasus_live/home`, morning, commit
    `abe2137`, the August label pack;
  - `sweep_undecoded-fresh.json`: new home `~/pegasus_fresh`, first rebuilt
    pack;
  - `sweep_undecoded-fresh2.json`: the same home, commit `34afaee`, pack with
    per-window carry-forward.
- Evidence per column: `scripts/def_evidence.py`.

**What was counted, and why.**
- For every column with a label companion, the rows whose value is present
  but has no label. An undecoded value is what the user sees as `code (?)`, so
  this is what the standing instruction "every code translatable" is measured
  on.
- New undecoded columns relative to the morning run count as regressions.

**Result.**

| dataset | columns with undecoded values | undecoded rows | seconds (files cached) |
|---|---|---|---:|
| SIH-RD AC 2023-01 | 15 → 11 | 58,296 → 45,415 | 7.6 |
| SIH-SP | 8 → 4 | 328,665 → 186,310 | 1.7 |
| SIM-DO AC 2022 | 1 → 0 | 4,159 → 0 | 1.6 |
| SINASC-DN AC 2022 | 4 → 4 | 16,775 → 16,775 | 1.5 |
| CIHA | 2 → 2 | 166 → 166 | 1.5 |
| CNES-ST | 3 → 2 | 2,560 → 1,282 | 2.7 |
| CNES-PF / SR | 0 → 0 | 0 → 0 | 1.3 / 0.7 |
| CNES-EP | 4 → 3 | 996 → 502 | 1.1 |
| SIASUS-PA | 8 → 7 | 330,171 → 234,724 | 6.4 |
| SIASUS-AQ / AR / AM | 4/3/1 → 4/2/1 | 3,248 → 3,228 | ~0.9 |
| SIASUS-BI | 9 → 2 | 479,917 → 68,563 | 2.9 |
| SIASUS-PS | 7 → 4 | 7,742 → 3,359 | 0.8 |
| SINAN-HANS 2022 | 6 → 6 | 261 → 261 | 3.1 |
| **total** | **75 → 52** | **1,232,956 → 560,585** | |

**Regressions found, and fixed before this was recorded.**
- **The first rebuilt pack lost 3 decoding columns on a fresh home:** SIH
  `COBRANCA` (discharge reason `12` "Alta melhorado") and `NACIONAL` (`010`
  Brasil), and CNES `NAT_JUR` (`3301`).
  - The first two tables' current windows came from a source the rebuilt
    catalog no longer holds, and carry-forward worked per codelist, not per
    window (ADR-0095).
  - `3301` (2021) is newer than the detailed CONCLA table; it now falls back
    to the kit's grouping, "3. Entidades sem Fins Lucrativos".
- The final run has **no** new undecoded column in any dataset.

**What remains is mostly values no source documents** (ADR-0098):
- SIA `TIPPRE` `00` (every row);
- `PA_CODOCO` (its `.CNV` is keyed by a two-character code that the column
  does not hold);
- SIH-SP `SP_DES_HOS`/`SP_DES_PAC`/`SP_U_AIH`;
- SIH `TPDISEC*` `0`;
- SINASC `CODPAISRES` `1`, `KOTELCHUCK` `9`, `TPDOCRESP` `0`;
- CNES `TP_PREST` `99`.

**Also measured.** A first query on the empty home (SIASUS-ACF 2023-01) took
132 s. It includes downloading the month's files and the one-time 127 MB CNES
kit for establishment names (ADR-0086).
