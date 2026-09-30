## ADR-0118: Seven-digit IBGE municipality codes decode against a seven-digit table

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0087.

**Context.**
- **Every DATASUS municipality table is six digits** (`BR_MUNICIPALFA` and
  the per-state tables). IBGE's code has a seventh, check digit.
- **Older SINAN files write the seven-digit code.** Exact-width matching (§6)
  therefore left these columns undecoded:
  - SINAN-LTAN 2003 `CON_MUNICI`: 11 of 28,715 decoded;
  - SINAN-MALA 2004 `CON_INF_MU`: 0 of 1,909;
  - SINAN-HANT 2004 `CLI_MUNICI`: 0 of 183.
- **They are IBGE codes.** Among the seven-digit values, the share that are
  current IBGE codes:
  - LTAN 2003: 28,338 of 28,441 (99.6%), with 28,327 passing IBGE's check
    digit (a random seven-digit number passes about one time in ten);
  - MALA 2004: 1,792 of 1,909;
  - HANT 2004: 150 of 150.

**Decision.**
- **`MUNIC_BR7`:** IBGE's seven-digit code → "Name, UF". It is built from the
  shipped municipality resource (`municipalities.parquet`, IBGE localidades)
  and served like `UF_BR`.
- **Chained after `BR_MUNICIPALFA`** on the measured columns: SINAN
  `CLI_MUNICI`, `CONF_INF_M` (HANT), `CON_MUNICI` (LTAN), `MTRANSFU` (MALA),
  `CON_INF_MU`. Each value matches only a table of its own width, so no code
  is padded or truncated.
- **Current division.** A municipality renamed since the record reads its
  current name. One whose code no longer exists stays undecoded, visibly.

**Evidence** (after the change, same slices):
- LTAN 2003 `CON_MUNICI`: 28,349 of 28,715 decoded;
- MALA 2004 `CON_INF_MU`: 1,792 of 1,909, and `MTRANSFU` 21 of 21;
- HANT 2004 `CLI_MUNICI`: 150 of 183; the other 33 are the 1-digit value
  `0`.

**Not done.** Other columns that carry seven digits were not searched for. A
column is bound to `MUNIC_BR7` only after a measurement like the one above.
