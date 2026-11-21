# SIGTAP across all monthly exports: when a procedure exists and what it paid (2026-11-21)

**Regime.** Branch `sigtap-history`, data home `pegasus_core_data`, `pegasus-data sigtap --history` (`sources/sigtap.build_history`), all 227
exports 200801 to 202611 read on 2026-11-21 (0.34 GiB, kept nowhere). Artifacts: `registries/sigtap/procedure_history.parquet` (25,985 rows)
and `procedure_windows.parquet` (5,785 rows).

**Why.** SIGTAP codes had no validity window (OPEN_QUESTIONS #95): a 2023 code labelled 2015 records. Studies also need each
procedure's reimbursement over time (VL_SH hospital, VL_SA outpatient, VL_SP professional).

**Counted.** 227 files for 227 months, no month missing and no month with two versions (from 201301 each file carries a
`_v<yymmddhhmm>` stamp; the build takes the greatest stamp if a month ever repeats). 5,785 distinct codes; 1,595 first appear after 200801
and 717 are absent from the newest export. One code leaves and returns (0405040121: 200801-200803, 201312-201603; 68 months absent).
Three `tb_procedimento` layouts: 200801-201208 (no `QT_TEMPO_PERMANENCIA`), 201209-202505 (adds it), 202506-202611 (money columns widen from
10 to 12 characters, so every later column moves); each read by its own layout file, and every row's `DT_COMPETENCIA` equals its export's
competência. Money is filed in centavos: `0000041589` is R$ 415.89, checked against 0301010072 (consulta especializada) = R$ 10.00 in
200801 and in every run after.

**Runs.** 25,985 runs over 5,785 codes; 5,027 codes have more than one. Many are not economic: 3,962 transitions change only a name
or group name (accents appear in the 201209 and 201308 vintages: ATENCAO to ATENÇÃO), 3,368 transitions change a value, in 2,513 codes.
A reader that wants price changes only should compare the VL columns, not trust the run boundaries.

**Known answers.**
- 0403070171 (tratamento do AVC isquêmico): first competência **202312**, present to 202611, no gap. The 202311 export (reissued 2024-01-19)
  does not hold it; the Portaria SAES/MS 1.996 of 24 Nov 2023 itself was not read, only the effective month. The name is not
  "thrombectomy": the mechanical-thrombectomy catheter is 0702040126 (a material, present since 200801).
- 0403010020 (craniotomia descompressiva): 200801 to 202611, no gap. VL_SH R$ 415.89 throughout; VL_SP 261.24 until 201104, 391.86 from 201105.
- 0403070155 (embolização de aneurisma cerebral < 1,5 cm): first 201012. VL_SH R$ 1,238.88 throughout; VL_SP 448.00, then 784.00 from 201105.
  Nominal SUS neurosurgical payment is almost frozen across 15 years; the real value falls with the IPCA.

**Reading cost.** About 4 s per export; the FTP stalls a session after some twenty transfers, so the build opens a new connection every
eight exports (a login per export, or one connection throughout, took tens of minutes). `cache_dir=` keeps the zips for a resumable run.

**Not done.** Label gating by window in `view.py` (another session, on this registry); the relations (`rl_procedimento_*`) over time.

**Labels joined by the window (same day, OPEN_QUESTIONS #95 resolved).** The view drops from a column's lookup every
10-digit SIGTAP procedure whose window does not meet the period read, and reports how many. `levels("SIH-RD",
"PROC_REA", ...)`: 0403070171 labelled in 2024, not in 2009, 2015 or 2020; 0403070023 (8-15 mm coiling, to 201105) in
2009 only; 0304010219 (radiosurgery, to 201906) in 2009 and 2015, not 2020; 0403010020 in every year. Periods before
200801, the first export, are not judged.
