## ADR-0024: Every schema is catalogued by a header census from ranged fetches

**Date:** 2026-08-19. **Status:** active.

**Context.** The brief asked for several samples per stratum to fix defect D2
(schema conclusions drawn from one file). Decoding one file per stratum costs
183 GiB, and 63% of strata hold a single file, so there is no cheaper member
(`docs/history/FINDINGS.md` §3g). A DBF declares its whole schema in a header
of a few hundred bytes, and a `.dbc` stores that header **uncompressed** ahead
of the compressed payload. Measured on `RDAC9201.dbc`: all 35 fields from the
first 1,153 of 91,967 bytes. Over the tree: 3,701 strata examined, 2,813
schemas read for 19.23 MB, about 9,750× less. Validated two ways: 571 files
parsed from their prefix and decoded in full gave identical field lists; 100%
of catalogued schemas' widths sum to the declared record length. Built in
`fd8a9e9` (2026-08-19).

**Decision.**
- Schemas come from a **census** of every stratum's header, read by a ranged
  prefix fetch (`retrieve_prefix()`: `transfercmd` + `ABOR` + a drained
  reply). The parser refuses rather than guesses when the prefix is short, and
  widens once when the file's own `header_length` says to.
- Census results land in `schema_header_facts` and mark the stratum
  `sample_status = 'header'`, **never** `'ok'`. Knowing the columns must not be
  mistaken for knowing what is in them.
- Census and profile share `schema_signature`, so both land on the same family
  (ADR-0006).
- CSV schemas are read from their first line too (`bca5693`).

**Alternatives.** Better sampling, as the brief asked. Rejected: a census
covers every stratum for about 0.01% of the cost
(`docs/history/pegasus_data_ARCHITECTURE.md` §19 item 1).

**What would reverse it.** Nothing foreseen. Archives, Parquet (footer at the
end) and LHA `.exe` still need a different reader (FINDINGS §3i).
