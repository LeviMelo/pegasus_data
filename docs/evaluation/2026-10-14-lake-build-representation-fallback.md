# A mismatched export no longer drops a publication from the lake (ADR-0190)

Regime: base `5f702db` (`pegasus-core-fixes`) against `cf45be3` (`fix-lake-mismatch`), 2026-10-14. Diagnosis read-only on `pegasus_core_data`'s catalog and blobs (a copy of the catalog in a scratch root for every experiment); the only writes to the real root are the two final builds below, `release=True`. Scripts and outputs: the agent's scratchpad (`diag*.py`, `run_build.py`, `final_check.py`, `snap.py`).

**The defect.** `build_lake("SINAN-ZIKA", [2016])`: `files_mismatched 1`, `partitions 0`. The catalog puts all four files of a year (CSV, JSON, XML, `.dbc`) in the family of the `.dbc` header sampled for the stratum (`SINAN_ZIKA_6a8548cac3`, 38 fields; `SINAN_CHIK_f6cef831ba`, 122); `file_schemas` has 0 rows in this catalog; `choose_representations` picks the smallest file, the CSV. Decoded, the files are:

| file | fields | signature | rows | against the family |
|---|---|---|---|---|
| ZIKA 2016 CSV | 38 | `8a200634...` | 281,464 | has `CS_SUSPEIT`, `CS_FLXRET`, `FLXRECEBI`, lacks `ID_UNIDADE`, `ANO_NASC`, `DT_DIGITA` |
| ZIKA 2016 `.dbc` | 38 | `6a8548ca...` | 273,904 | the family |
| CHIK 2016 CSV | 38 | `8a200634...` | 316,602 | 38 of the `.dbc`'s 122 columns |
| CHIK 2017, 2018 CSV | 116 | `35a5f8c2...` | 247,662; 118,779 | `.dbc`: 244,070; 116,526 |
| CHIK 2019 CSV | 116 | `d4f5efaf...` | 178,147 | `.dbc`: 178,349 |
| ZIKA 2017, 2018, 2019 CSV | 38 | `8a200634...` | 32,684; 20,584; 30,500 | `.dbc`: 31,754; 20,032; 30,536 |

ZIKA 2020 differs the same way; ZIKA 2015, 2021-2023 and CHIK 2014-2015 CSVs equal the family's signature (2014-2015 also its row counts, and every non-date column; the date text is `2015-01-04` against `20150104`, both `date32` in the lake). 67 of SINAN's 98 families hold 2,114 exports beside their `.dbc`: ADR-0135's rule that a native is read first is switched off by its own family clause for all of them.

**Built (real root, `pegasus_core_data`).** Rows are the lake file's, the catalog's and the `.dbc` header's record count (bytes 4-7 of the raw file, not the decoder): equal in all 11 years.

| year | ZIKA source | ZIKA rows | CHIK source | CHIK rows |
|---|---|---|---|---|
| 2014 | | | CSV (kept) | 4,622 |
| 2015 | CSV (kept) | 56,159 | CSV (kept) | 52,342 |
| 2016 | `.dbc` | 273,904 | `.dbc` | 310,746 |
| 2017 | `.dbc` | 31,754 | `.dbc` | 244,070 |
| 2018 | `.dbc` | 20,032 | `.dbc` | 116,526 |
| 2019 | `.dbc` | 30,536 | `.dbc` | 178,349 |

ZIKA: 4 partitions written, 1 reused, 4 representations refused (the CSVs), 6.2 s, 11.7 MB; CHIK: 4 written, 2 reused, 4 refused, 8.7 s, 31.6 MB; `errors []`. A second call of each: 0 files attempted, 5 and 6 partitions reused, 1.1 s. `release` freed 8 + 8 blobs (12.3 + 50.3 MB), the refused CSVs among them. `query("SINAN-ZIKA", period="2016")` returns 273,904 rows.

**Nothing else moved.** All 3,325 other `lake_partitions` rows (path, rows, bytes, written_at, fingerprint) hash equal before and after; the files of SINAN-LEPT (10 partitions), SINAN-TOXG (7), SINAN-TOXC (7), SIM-DO (84), SINASC-DN (28) and SIH-RD (487) have the same sizes and times. `choose_representations` over every family file of SINAN, SIHSUS, SIM, SINASC and SIASUS (119,000 rows, base and branch): the selected files hash equal in each system, so no other dataset's next build reads a different file.

**Paths not taken by the data, exercised.** With `_matches_schema` patched to refuse everything, ZIKA 2020 reads its CSV, `.dbc`, XML and JSON in that order (the `.dbc` second), builds nothing and says: `schema: no representation has the columns of SINAN_ZIKA_6a8548cac3; read ZIKABR20.csv.zip (38 fields, signature 8a20...); ZIKABR20.dbc (38 fields, signature 6a85...); ...`; the outcome row carries the reason. `retrieve.fetch` for ZIKA 2019 refuses 3 exports before the `.dbc` on the base (7.6 s) and 1 on the branch (2.0 s, same blobs and rows: 30,536). The rejected design, measured: the ZIKA 2016 CSV's signature in `file_schemas` splits `SINAN_ZIKA_8a20063414` off in `build_families` (2.3 s for the catalog), and the publication then raises `RepresentationConflictError`.

**Incidental.** A build whose partitions were all current recorded "N files decoded and matched the plan but yielded no rows"; it now says every partition was already current.
