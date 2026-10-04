## ADR-0135: The native file is read before an open-data export of the same publication

**Date:** 2026-10-03. **Status:** active. **Amends:** ADR-0133.

**Context.** ADR-0133 ranks equivalent representations by bytes on the wire. A fresh-home sweep of every SINAN form for 2023 (evaluation 2026-10-03 SINAN undecoded sweep) showed that a Dados_Abertos export is not equivalent to its DBC:
- **Leading zeros are stripped.** ACBI `TIPO_ACID`, `SIT_TRAB` and ACGR `PART_CORP1` read "8", "1", "5" from the CSV and "08", "01", "05" from the DBC. 39,343 + 75,058 + 401,301 cells went undecoded.
- **Columns are missing.** IEXO 2023's CSV has 66 columns against 80–82 in the DBC families, so it matched no family and the query returned nothing.
- **Values are corrupted.** SIFA 2023's CSV holds Python bytes reprs as values (`b'2',b'A539',b'20230729'`), published that way.
- **Editions are older.** ACBI 2023's CSV is the January edition (78,242 rows); the PRELIM DBC is from September (80,094).

The smaller CSV won the byte ranking in 469 SINAN publications.

**Decision.**
- **Natives first.** When a publication has a native DBC/DBF and an export (CSV, JSON, XML zip), the export is dropped, and ADR-0133's ranking applies among what remains.
- **Export as fallback.** An export is read only when no native exists, or when every native has an open `fetch` gap: both the FTP and the mirror failed for it.
- **The fallback is temporary.** A later successful fetch resolves the gap, and the native is read again.
- **One rule.** This replaces the date rule tried the same day (exports dated before the native dropped), which could not see stripped zeros or missing columns.

**Consequences.**
- **Higher cost.** A fresh install fetches the DBC even when an export is smaller: 4.1 against 2.9 MB for ACBI 2023.
- **Unchanged cases.** SIH 2008–2014 keeps its DBC, the smallest file anyway.
- **One failed attempt.** A native the mirror lacks costs one failed attempt before the export is used.

**Evidence.** On the fresh home, `plan()` picks the DBC for ACBI, SIFA and SIH-RD AC 2008-01. With a simulated fetch gap on `ACBIBR23.dbc` it picks the CSV (2,952,960 bytes), and the DBC again once the gap is resolved.
