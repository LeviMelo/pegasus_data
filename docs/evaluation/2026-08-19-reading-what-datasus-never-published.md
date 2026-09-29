## 2026-08-19 — Reading what DATASUS never published (microdatasus)

*Split from docs/history/FINDINGS.md §3h on 2026-09-28; text unchanged.*

## 3h. Reading what DATASUS never published (2026-08-19)

CNES is the clearest gap on the tree: 163 categorical columns, a thin record
layout, and value codings that live almost entirely off the FTP tree. No crawl
closes that, and leaving it blank means columns are unlabelled that every
practitioner in the field can already read.

`rfsaldanha/microdatasus` (MIT) is an R package that recodes DATASUS microdata,
and its `process_*.R` files encode value labels as literal `"code" ~ "label"`
pairs. Parsed — never executed — it yields **4,655 code→label pairs across 582
labelled columns**, including CNES (163 fields, 726 pairs) and SIA (37 fields,
570 pairs).

It is ingested at `source='community'`, which sits below `pdf` and above
`inferred`, and two properties make that safe. It cannot outrank a first-party
table: `SOURCE_AUTHORITY` places it behind `cnv`, `def`, `sigtap`, `dbf_lookup`,
`demas_api` and `pdf`, and a test drives a contradicting community label against
a stored `.CNV` one to confirm the `.CNV` holds. And every entry carries the
repository, the **commit SHA** and the file in `source_ref` — a transcription
without a version is a rumour; with one it is a citation someone can re-run.

One parsing detail worth recording: a pair belongs to the field whose
`if ("X" %in% variables_names)` block encloses it. Scanning the file for pairs
without that bracketing would smear every column's codes across every other
column, which is worse than extracting nothing.
