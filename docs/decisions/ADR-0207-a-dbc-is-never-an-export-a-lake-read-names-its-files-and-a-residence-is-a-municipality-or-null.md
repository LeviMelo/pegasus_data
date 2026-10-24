# ADR-0207: A DBC is never an export, a lake read names its files, and a residence is a municipality or null

2026-10-24. Status: active. Amends ADR-0135 (native files before exports) and the `remap` recipe of derived columns.

## Context

The dengue spatio-temporal project (`dengue-espaco-tempo/PEGASUS_ISSUES.md`, items 1, 2 and 8) found:

1. `query(..., return_report=True)` answered with a `FetchReport` carrying `source_facts` for a year read from the FTP
   and a `RenderReport` without them for a year read from the lake, so the same code broke by year.
2. SINAN-DENG 2020 held 538,654 discarded notifications (`CLASSI_FIN 5`) and no `DT_DIGITA`, unlike every other year.
   Its partition had been built on 2026-10-05 from `Dados_Abertos/SINAN/Dengue/csv/DENGBR20.csv.zip`, not from
   `SINAN/DADOS/FINAIS/DENGBR20.dbc`. ADR-0135 reads a native file first, but `_exports_behind_native` took every file of
   a family that also holds exports for an export copy (a guess written for SIH's `/SIHSUS/DBF/*.dbf`), so for SINAN the
   rule was off and "cached, then smallest" chose: the 44.6 MB CSV over the 47.7 MB DBC, or whichever was cached. 33
   SINAN partitions (12.0 million rows; DENG 2020 and 2022-2024, LEPT, TUBE, TOXG, TOXC, CHIK, ZIKA) came from exports.
3. `ID_MN_RESI` holds codes no municipality list has: Federal District region codes, a state with no municipality, a
   three-character code.

## Decision

1. **A `.dbc` is DATASUS's own file and never an export copy.** Only an uncompressed `.dbf` in a family that holds
   exports is suspected of being one (no `.dbc` lies under `Dados_Abertos`). SINAN's selection no longer depends on what
   is cached: 612 publications in 64 families read `FINAIS/*.dbc`; nothing outside SINAN changes.
2. **A lake read's report says where its rows came from as a fetch's does:** `RenderReport.source_facts` (source file ->
   family, year, competence) from the partitions read, and `origin` (`lake`; a `FetchReport` says `fetch`).
3. **A residence becomes a municipality or null.** The `remap` recipe takes `ranges` (a declared code range to one code,
   with its evidence) and `municipalities_only` (a code that ends as no IBGE municipality is null and the report counts
   it). SINAN's `ID_MN_RESI_municipio`: 530000-539999 to 530010 (DATASUS's AGLBR and BR_CAPITAL map the range to Brasília,
   the Federal District's one municipality), other codes as written when they are a municipality, null otherwise
   (`XX0000`, "Município ignorado" in BR_DIVADM; a code of no municipality). `ID_MN_RESI` is never changed.
4. A derived or provenance column is no schema field, and the fetch path no longer reports it structurally absent.

## Evidence

Evaluation 2026-10-24-dengue-issues: DENG 2020 from the DBC holds 975,842 rows, no `CLASSI_FIN 5`, `DT_DIGITA` blank on
1.2% (the CSV: 1,495,117, 538,654 discards, `DT_DIGITA` blank on all); every other rebuilt partition has the DBC's rows
(DENG 2022-2024, CHIK, ZIKA, TUBE equal; TOXG +46, TOXC +7, LEPT −412); `ID_MN_RESI` 2010-2026: 22,958 region-coded rows
to 530010, 143 `XX0000`, 22 other codes of no municipality, 1 of no state (`035`, 2016), 1,715 blank.

## Consequences

* A partition built from an export while its DBC exists is stale by its fingerprint and is rebuilt on the next build.
* `care_flows` reads SINAN's residence through `ID_MN_RESI_municipio` (the derived remap of the residence column).
