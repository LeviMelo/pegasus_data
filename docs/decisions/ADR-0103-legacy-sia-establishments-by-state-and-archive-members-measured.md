## ADR-0103: SIA's pre-2008 establishment codes are keyed by the file's state, and a multi-table archive's members are measured, not assumed

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0077, ADR-0088, ADR-0098.

**Context.**
- **The legacy fields were bound to nothing.** SIA's 2001–2007 APAC archives
  (`ACAC0501.EXE`, LHA self-extracting) carry establishment codes in
  `APA_CODUNI`, `COB_CODUNI`, `EXA_CODUNI`, `OPC_CODUNI`, `PAC_CODUNI`,
  `PAF_CODUNI`, `UDI_CODUNI`, `PAQ_CODUNI` and `UDO_CODUNI`.
- **The codes are 6-digit UPS codes, unique only within a state.** 14,187 of
  29,043 codes name different establishments in different states: `000001`
  is Hospital de Base in Acre and another unit in Alagoas. TabWin picks
  `UPS-N<UF>` (kits 1994–2003) or `CNESN<UF>` (2003–2007) by the file's state.
  A national union would label records with another state's establishment.
- **The archives' member lists were assumed.** `expand_archive_strata` gave
  every archive of a state-year the member list of ONE sampled archive.
  - For SIASUS-CO 2005-01, 22 of 27 archives were listed with a CO table they
    do not contain. The fetch called them schema mismatches and the table
    "short". The truth is that nothing was published.
  - The EX, PC and AC components reached no archive of 2003–2006, although
    the archives hold them (`ACAC0501.EXE` lists `EXAC0501.DBF`,
    `PCAC0501.DBF`, …), so a query of those years found nothing.

**Decision.**
- **The file's state is a key part.**
  - `fetch` records each source's state (`FetchReport.source_ufs`) and gives
    the table a hidden `_source_uf` column, dropped after rendering.
  - A key part `@UF` is that column (`view.compose_key`).
  - `SIA_UPS_BR` (`persist/reference`) is SIA's own `UPS-N<UF>` and
    `CNESN<UF>[1-3]` tables, keyed `UF + code`, 141,003 establishments, with
    identifiers stripped (ADR-0102).
  - The legacy fields are keyed `["@UF", <field>]`.
- **An archive's members are measured.**
  - `schemas --all-files` also lists every self-extracting archive's members
    by a ranged header walk (`inventory/schemas.list_lha_members`). Each LHA
    header gives the size of the compressed data after it, so the walk hops
    from header to header without downloading the tree's 3.9 GB. On
    downloaded archives it lists exactly what the full reader lists.
  - `expand_archive_strata` puts an archive in a component's stratum only if
    the archive holds that component. An archive not yet listed keeps the old
    assumption.
- **A listed member the archive lacks is not a gap.** `fetch` records it in
  `FetchReport.members_absent`; the answer is not short.
- **A member in another layout of the dataset is read under that layout**
  (`FetchReport.refamilied`), not dropped as a mismatch.

**Result.** See the evaluation entry of the same date.
