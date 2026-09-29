## ADR-0077: Archives are censused, and each table inside a multi-table archive is its own publication

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0071 (representations), the census (ADR-0020's header-only schema read).

**Context.** After the full crawl, the census read headers from `.dbc`, `.dbf`
and `.csv` only. That left 1,694 data files with no known schema, so they
belonged to no family and no query could reach them:
- **SIA APAC 2001-2007.** 1,457 LHA self-extracting archives, one per state and
  month (`ACAC0201.EXE`, about 2.4 MB each). Each holds up to seven dBase
  tables named by the archive's own coordinates: `ACAC0201.DBF`,
  `PCAC0201.DBF`, `COAC0201.DBF` and so on.
  - The 2007 tables are **dBase level 7**: version byte 0x04, a 68-byte header
    and 48-byte field descriptors. The reader only knew the 32-byte layout.
  - From 2005 the "AC" archives hold only the CO table.
  - 2002 holds 266 archives beside two loose `.dbf`.
- **Small zips and Parquet** (`Dados_Abertos`, SINAN, SISCAN): the schema sits
  inside a zip member or in a Parquet footer at the end of the file.

**Decision.**
- **Small archives.** A zip of 20 MB or less is fetched whole, and its first
  dbf/dbc/csv/parquet member's header is read. The same applies to an LHA
  `.exe` (`schemas._header_in_archive`, `_header_in_lha`). An LHA census
  records every member in `archive_members`.
- **Parquet.** The census reads a ranged tail (FTP `REST`, 256 KB), then the
  footer, refetched at its exact size when it is larger. No prefix is
  downloaded.
- **dBase 7.** It is read by one shared layout rule in `decode/header.py`
  (`descriptor_layout`, `descriptor_widths`) that both the census and the
  decoder use.
- **Member strata.** `inventory/strata.expand_archive_strata` turns every other
  member kind of a stratum's sampled archive into a child stratum
  `<stratum>#<kind>` (series = kind) that spans all the parent's archives. Each
  archive's own member is derived by name: `ACSP0411.EXE` holds `PCSP0411.DBF`
  (`naming.member_name_for`).
- **Naming and sampling.** A family is named for the table actually read
  (`naming.member_kind`), so a 2005 "AC" archive holding only
  `COAP0511.DBF` joins SIA.CO. A stratum that is mostly archives samples an
  archive. A loose file beside the archives belongs to the own-kind family
  only.
- **Datasets.** The members are declared in the ontology as SIA.AC
  (authorisation header), SIA.CO, SIA.EX, SIA.OP, SIA.PC, SIA.PF, SIA.PQ,
  SIA.UD and SIA.UO, named from their columns. No layout document has been
  found for them.

**Result, measured 2026-09-28:**
- 0 of the 1,459 APAC files are unfamilied, across 12 families.
- `query("SIA-PQ", period="2007-06", geography="AP")` returns 51 oncology
  patients, with procedure, unit and ICD labels (`C50.9 Mama NE`).
- The census of all APAC strata moved about 0.1 MB.

**Still unfamilied:**
- 12 DuckDB exports (`.duck`, `.duck.zip`);
- 3 SINAN json-only zips;
- 1 header-less SISCAN 2015 CSV.

**What would reverse it.** A layout document naming the APAC blocks
differently would change the ontology names, not the mechanism.
