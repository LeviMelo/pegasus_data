# SIA APAC families: inventory, patient key and event types (AQ, AR, AN, ATD)

Scenario: header-row inventory of 41,832 APAC/PS/SAD DBCs, then live reads of AQ, AR, AN, ATD (AC and DF slices, 2012-2023) through `query`, `event_types`, `roles` and `count_events` on the core data home.
Artifacts: `data/probes/apac/` (`rows_per_file.json`, `verify.json`, `labels.json`, the raw slices; scripts `inventory.py`, `verify.py`, `labels.py`, `gen_roles.py`).
Regime: 2026-10-05, branch pegasus-core-fixes, `pegasus_core_data`, files by the mirror (FTP data channel down).

Counted and why: the number the API returns for an event type must equal an independent count of the thing it names.

| slice | file rows (DBC header) | rows read | events (`count_events`) | rows type 1 or 3 | distinct `AP_AUTORIZ` |
|---|---|---|---|---|---|
| AQ DF 2023 | 60,620 | 60,620 | 20,518 | 20,518 | 23,631 |
| AQ AC 2023 | 8,417 | 8,417 | 2,921 | 2,921 | 3,287 |
| AR DF 2023 | 1,155 | 1,155 | 1,155 | 1,155 (all type 3) | 1,155 |
| AN DF 2013 | 14,736 | 14,736 | 5,399 | 5,399 (5,345 + 54) | 6,041 |
| ATD AC 2023 | 5,088 | 5,088 | 1,841 | 1,841 | 2,101 |

- Header rows equal rows read in all five. Events equal the rows of type 1 or 3; the APACs that began in the previous year's files (AQ AC: 3,287 - 2,921 = 366) have only later-month rows and are not events of this year.
- Roles resolve: residence `AP_MUNPCN`, sex `AP_SEXO` (F, M), age `IDADE_anos`, start `AP_DTINIC`; age runs 2-103 (AQ AC; unit 5 = 100-107), 0.08-101 (AQ DF), no null age cell. Top primary codes: AQ AC C506 888, C61 516; AR DF C509 211; AN DF N180 5,399 of 5,399; ATD AC N188 1,479, `0000` 354.
- Labels (analysis profile, AC slices): every coded column that has a codelist is decoded to at least 99% of non-empty values except `AP_ETNIA` (AQ 30 of 38, ATD 45 of 48: codes like X271 are not in ETNIA.CNV), `AQ_GRAHIS`/`AR_GRAHIS` (codes 01, 02, 03, 99, 1, 2, 3 left undecoded, as before) and `AP_TPATEN` in ATD (code 03). The AN measurements (`AN_HB`, `AN_DIURES`, ...) are numbers with no label.
- **Defect found and fixed:** `AP_MNDIF` was labelled "Sim (houve invasao)" on every row, but the value is `1` on 100% of rows of every family read while the patient lives outside the facility's municipality on about half (AQ SP 2023-01: 40,935 of 80,069). The label is removed; `AP_UFDIF` agrees with the state comparison on 80,069 of 80,069.
- Patient key: `AP_CNSPCN` recurs across months, years and families (AQ AC: 203 of 882 patients of 2019 in 2023; AR vs AQ AC 2023: 280 of 413; ATD vs AM: 384 of 679).
- Brasília: residence codes 530020-530180 in AQ DF in 2008-2021 (up to 68% of rows in 2012), none in 2022 and 2023; AN's facility column also carries 530180. DATA_SOURCES §1.11 has the numbers.
- Not measured: AB, ABO, ACF, AM, AD, AMP event types; the link of `AP_CNSPCN` to other systems; a TabNet count of APACs (no independent published figure was retrieved).
