# SINAN undecoded sweep: every form, 2023, fresh home

**Date:** 2026-10-03.
**Script:** `scripts/sweep_undecoded.py`, with `PEGASUS_SWEEP_SLICES` listing every SINAN form for 2023 (LER 2019, ESPO 2022).
**Data home:** fresh, `~/pegasus_live/home`; the FTP data channel was down, so files came from the mirror.
**Artifacts:** `data/probes/live/sweep_undecoded_sinan_2026-10-03{,b,c}.json`.

**What was counted.** For every column with a label companion: the non-empty values left without a label, "code (?)". This is the "every code translatable" worklist, measured on what a user receives.

| run | code | rows | coded columns | columns with undecoded values | undecoded cells | errors |
|---|---|---|---|---|---|---|
| a | 8c36f19 | 4,960,031 | 2,912 | 400 | 14,539,830 | COLE, IEXO, PEST |
| b | 8ea3971 (ADR-0135) | 5,213,812 | 2,959 | 424 | 9,234,594 | COLE (2023 not published) |
| c | 645a389 (ADR-0136) | 5,213,812 | 2,959 | 398 | 7,176,079 | none |

**a to b.** Run a read Dados_Abertos exports wherever they were smaller. They strip leading zeros, drop columns (IEXO matched no family) and, for SIFA, hold bytes reprs; ADR-0135 reads the native DBC.

**b to c.** ADR-0136 stopped serving per-form tables merged by the `variable_docs` bridge, and lets a partial form dictionary outrank measurement. AIDA `CRITERIO`, CHAG `CLASSI_FIN`, AIDA and DCRJ `EVOLUCAO` now decode.

**Since c** (verified directly, not re-swept):
- CHIK and DENG `CLASSI_FIN` decode from the Sinan Online table (238,240 CHIK rows).
- `CNAE` decodes from CNAENET, keyed on its class rather than its row sequence, together with IBGE's CNAE 2.0.

**Left** (OQ-61): values no source names.
- `0` in DENG/CHIK conditional fields and in IEXO `COAGTOXMA*`.
- AIDA `CRITERIO` 101/601/902.
- ANTR `FIM_ANIMAL` 6 and `PRE_EXPOS`/`POS_EXPOS` 3.

**A false match from the CSV.** Run a's ACGR `UNI_ATENDE` values ("15369", "4294") matched `ID_ESTAB` in the kit's `UNIDINVEST.DBF`, so that column was briefly registered as the key. On the DBC the values are CNES codes ("0015369"): 365,011 of 400,352 rows match `ID_UNIDADE`, and none match `ID_ESTAB`. The stripped zeros had produced a plausible match. The registry now keys UNIDINVEST on `ID_UNIDADE`.

**Other systems.** The default 16-slice sweep (`data/probes/live/sweep_undecoded_systems_2026-10-03.json`, commit fd7ea42, fresh home) against its 2026-09-29 run:

| | 2026-09-29 | 2026-10-03 |
|---|---|---|
| undecoded cells | 560,585 | 7,251 |

- **Cleared:** SIH-SP 186,310 → 0, SIA-PA 234,724 → 0, SINASC 16,775 → 55, SIH-RD 45,415 → 0 once `RUBRICA` was reverted.
- **Left:** the OQ-61 residues (SIA-AQ/AR histology grade, SIA-PS nationality and ethnicity, CNES bank codes and area placeholders, SINAN-HANS 261).
- **CIHA AC 2023-01** could not be fetched: the FTP data channel is down and the mirror lacks CIHA.
