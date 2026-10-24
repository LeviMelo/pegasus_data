# The dengue project's issues 1, 2 and 8 (2026-10-24)

**Check.** `dengue-espaco-tempo/PEGASUS_ISSUES.md` items 1, 2 and 8 (ADR-0207), on `pegasus_core_data`, branch
`dengue-issues` from e7f223f (fix at 400c5f1), 2026-10-24; scripts in the session scratchpad (`repr_diff.py`,
`rebuild_exports.py`, `mnresi2.py`). What was counted and why: the file each year's rows come from (a year built from
another representation is another population of records); how many selections the representation rule changes, and
where (a rule written for SIH must not move SIH); each rebuilt partition's rows against the one it replaced; every
`ID_MN_RESI` code by what the derived column does with it.

**Item 1, the report.** `query("SINAN.DENG", period=2019, return_report=True)` read from the lake now has
`source_report.origin == "lake"` and `source_facts == {"/dissemin/publicos/SINAN/DADOS/FINAIS/DENGBR19.dbc":
("SINAN_DENG_d8842e2cc0", 2019, None)}`; every row's `_source_path` is among its keys. A fetch says `origin == "fetch"`.

**Item 2, dengue 2020.** The partition named `Dados_Abertos/SINAN/Dengue/csv/DENGBR20.csv.zip` (built 2026-10-05, mirror;
the DBC had been fetched only in another home, adopted later). `choose_representations` over the 81 families holding
exports: before the fix 2,971 files selected, after it 612 publications in 64 families change, all SINAN, all from an
export (589 CSV, 17 JSON, 4 Parquet, 2 XML) to `FINAIS/*.dbc`; no SIH selection changes. Lake partitions built from an
export: 33 (12.0 million rows), rebuilt by `build_lake` in 4 minutes, none left.

| dengue 2020 | rows | `CLASSI_FIN` 5 | `DT_DIGITA` blank |
|---|---|---|---|
| CSV export | 1,495,117 | 538,654 | 1,495,117 (all) |
| FINAIS/DENGBR20.dbc | 975,842 | 0 | 11,627 (1.2%) |

Other rebuilt partitions, export rows → DBC rows: DENG 2022-2024 9,615,975 = 9,615,975; TUBE 2014-2019 537,767 =; CHIK
2014-2015 56,964 =; ZIKA 2015 56,159 =; TOXG 2019-2023 56,079 → 56,125; TOXC 20,968 → 20,975; LEPT 2015-2024 171,756 →
171,344 (the exports' extra and missing rows not traced).

**Item 8, the residence.** `ID_MN_RESI_municipio` over SINAN-DENG 2010-2026 (22,698,346 rows):

| `ID_MN_RESI` | rows | the derived column |
|---|---|---|
| an IBGE municipality | 22,673,506 | as written |
| 530000-539999 other than 530010 (5300xx, 5399xx) | 22,958 | 530010 (13,585 in 2024, 5,529 in 2022) |
| XX0000 (state known) | 143 | null |
| another code of no municipality | 22 | null |
| no state prefix (`035`, 2016) | 1 | null |
| blank | 1,715 | null |

The report says it (`ID_MN_RESI_municipio: 8 distinct codes are no IBGE municipality and are null`, 2024). A year read
from the FTP (2013) had warned that the derived column was "absent from the schema" though its 11,958 DF rows were mapped:
derived and provenance columns are no longer checked as schema fields.
