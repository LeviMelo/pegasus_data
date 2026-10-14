## ADR-0177: A read never downloads: a registry is built by `pegasus-data registries build`, and a read without it says so

**Date:** 2026-10-14. **Status:** active. **Amends:** ADR-0086 (registries "fetched on first use"), ADR-0100.

**Context.**
- **A read fetched.** `load()` of SIH-RD with every column reached `registry.lookup` -> `registry.build` ->
  `Fetcher.ensure` when the establishment registry was not cached: a 1-file FTP fetch of the 127 MB CNES kit (166 s)
  inside a call that named no download (OQ 80). The same lookup serves `query`, the CNES <-> CNPJ crosswalk, the
  timeline's facility names and the name enrichment, and `query(max_download=0)` ("lake only") did not stop it.
- **It was the only such path.** Every other route from `load`/`query`/`scan`/`count_events` to the network is a
  fetch of the requested publications (`query` -> `fetch`, budgeted by `max_download` and refused at 0) or an explicit
  build. Read-only probe on the real root (SIH-RD AC 2022, 49,547 rows; sockets and `Pipeline()` trapped, default home
  empty so the registry is absent): before, `registry.build` -> `Pipeline()` reached from the lake read; after, none
  of `load`, `query` (labels and codes), `scan` reaches either.

**Decision.**
- `registry.lookup` only reads the cache. A registry that is not built (or was built by an older version) is a table
  that is not there: the read goes on, the column it would have named keeps its raw code with no label (visibly
  undecoded, §6), and one warning per process says `pegasus-data registries build <SYSTEM>`.
- `registry.build` is the one download of a registry and takes `settings`; the new command calls it
  (`registries build [CNES|SIASUS] [--refresh]`, 6 to 127 MB, once).
- SIH-RD AC 2022 with the registry absent: `CNES_label`, `CGC_HOSP_label`, `CNPJ_MANT_label` all null (49,547 of
  49,547) with the codes kept; built: `CNES_label` 0 null of 49,547 (`FUNDHACRE`).

**Alternatives.** Raise on a missing registry: refuses a 193-column read for three label columns. Keep first-use
building and count it in `max_download`: a hidden 127 MB download inside a read is the defect, whatever its budget.

**What would reverse it.** DATASUS publishing the registry as a dataset a read can plan and budget like any other.
