## ADR-0081: Every file's header is read, and a publication is read once whatever its layout or tree

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0020 (header census
per stratum), ADR-0068 and ADR-0071 (representations), ADR-0078.

**Context.**
- **The failure.** The live sweep refused SINASC DNR 1995: "1 of 2 selected
  sources did not contribute — schema_mismatch".
- **What the header census showed.** Reading all 81 headers of that year: 54
  files carry `CONTADOR` and 27 carry `CODIGO`. The stratum census had read one
  sampled header per (system, series, year) and assumed the rest matched.
- **The same assumption, earlier today.** It had also produced the stale SIA-PA
  signature (ADR-0078) and the sample-selection defects.
- **A duplicate behind the refusal.** Once each file was placed by its own
  schema, Roraima 1995 was read twice: 14,040 rows where the year has 7,020
  births. SINASC publishes it as `DNRRR1995.dbc` under both `1994_1995/Dados/`
  and `ANT/` (`CONTADOR`), and again as `ANT/DNRRR95.DBC`. Their logical
  identities differed only by the raw date token, `95` versus `1995`.
- **Cost of the fix, measured.** 198,916 DBC/DBF files. A header costs 2.4 KB
  and 0.45 s, which is 474 MB in total, about 3 h on 8 FTP connections.

**Decision.**
- **Per-file census.** `pegasus-data schemas --all-files` (`run_file_census`,
  8 connections) reads every DBC/DBF header into `file_schemas(path,
  schema_signature, …)`. It is incremental: a file is re-read only when new or
  when its `modified` changes. The stratum census remains for archives and for
  files not yet read.
- **Families place each file by its own signature.** A file whose header
  differs from its stratum's sample joins the family of its own schema.
- **Logical identity uses the normalized date.** `DNRRR95` and `DNRRR1995`
  become one publication, `SINASC|DNR|RR|199500`.
- **Among same-format editions in different layouts, the majority layout
  wins.** That is the family with the most publications
  (`representations._majority_layout`). The newest edition then decides
  between same-layout revisions, as before.
- **Stored conflicts.** A stored representation conflict gates only on evidence
  measured at decode (row counts). Formats, sizes and schemas are re-derived on
  every call.

**Result, 2026-09-28:**
- SINASC: 1,784 headers in 3.7 MB; DNR 1995 split into its two families.
- `query("SINASC-DNR", period="1995", geography="RR")` returns 7,020 rows from
  one file.

**What would reverse it.** A server that lists per-file schemas (it does not),
or a cost per header that made 3 h unaffordable. The stratum sample would then
return as the only census, with this ADR's identity and majority rules kept.
