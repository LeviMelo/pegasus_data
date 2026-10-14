## ADR-0181: Provenance is a public, read-only call: files from the lake rows, facts from the shipped curation, a series described with its numbers

**Date:** 2026-10-14. **Status:** active.

**Context.**
- A paper written from an Alagoas study folder (SIM-DO and SIH-RD, 2014-2023) could not say which files it was read from,
  what the population denominator is, or what a row is, though pegasus_data knows each.
- **`info("SIH.RD")` omitted what one row is** (read-only copy of `pegasus_core_data`'s catalog): the catalog's `dataset_docs`
  row is keyed `SIHSUS_RD`, `info` compared the ontology's system `SIH` with the row's `SIHSUS`, and nothing was found. The
  files hold `IDENT` 1 (157,005) and 5 (8,429) in Alagoas 2014.
- **The lake rows are the record of what was decoded.** Every row carries `_source_path` and `_blob_sha256`; the
  catalog's `decode_attempts` is empty for SIH-RD, so no catalog table holds the digest decoded or the rows per file.

**Decision.**
- `publications(dataset, years, ufs)` (CLI `publications`): one row per published file, from the provenance columns of the
  lake partitions (counted from the row groups' dictionaries: 119,005,606 SIH-RD rows of 3,240 files, nation 2014-2023, in
  7 s) joined to the catalog's listing (`files`, `file_facts`) and fetch history (`fetches`), plus the files listed and not
  held with the reason (the national file that holds the same records; another directory or format of the same
  publication; a partition that cannot be read). Preliminary or final is what the curation declares: the server's `PRELIM`
  tree, or the event types' `final_after_years`; neither: `undeclared`, never final by default.
- `dataset_facts(dataset)` (CLI `facts`): what the shipped curation documents of a dataset (row, biases, gotchas, dates
  and places, event types with their `source_notes`), read from the YAML, not the catalog's copy. `info` takes its
  documentation from it, which restores SIH-RD's.
- `load_population` returns the series' description in the table's schema metadata (`pegasus.series`) from
  `curation/populations.yml`; `Catalog.population_series()` lists it; an undocumented series says so.
- The curated texts of SIH-RD and SIM-DO state what was measured: the AIH types, the competence against the admission and
  discharge dates, the year of death.

**Alternatives.** A build-time catalog table of the files each partition was decoded from: a second record, absent for the
lake already built. Reading `dataset_docs` with a corrected key: keeps a copy that is only as current as the last write to
the catalog.

**Not decided.** `info()` still refreshes the catalog's curated text on read (`ensure_current` writes the catalog it
reads); `publications` and `dataset_facts` do not write.

**What would reverse it.** A lake row without provenance columns (the call reports the partition as unreadable, not as absent).
