# ADR-0190: a publication whose chosen representation has other columns is read from its next one, never dropped

**Date:** 2026-10-14. **Status:** accepted. **Amends:** ADR-0135 (what counts as an export), ADR-0133 (the choice is re-made after a refusal). **Origin:** `build_lake("SINAN-ZIKA", [2016])` returned `files_mismatched 1, partitions 0`, and a PegaSUS study of 2014-2019 wrote one partition of five.

**Context.** Three links, each measured on the real catalog and blobs (2026-10-14):
- **The family is the DBC's schema, the exports hang on it.** A SINAN stratum is sampled by its `.dbc` header; the year's CSV, JSON and XML exports are members of the same stratum, so all four land in the DBC's family. The per-file census (ADR-0081) reads `.dbc` and `.dbf` only: `file_schemas` is empty here, and nothing measures an export's columns.
- **The export is not the DBC.** The CSVs of ZIKA 2016-2020 and CHIK 2016-2019 carry other columns: ZIKA 2016 has `CS_SUSPEIT`, `CS_FLXRET`, `FLXRECEBI` and lacks `ID_UNIDADE`, `ANO_NASC`, `DT_DIGITA`; CHIK 2016 has 38 of the DBC's 122 columns, 2017-2018 have 116. The rows differ too (ZIKA 2016: 281,464 against the DBC's 273,904). The 2014-2015 CSVs (columns and row counts) and ZIKA 2021-2023 (columns) are the DBC's.
- **The native is not preferred, so the export is read first.** ADR-0135 reads the DBC before an export, but its amendment makes a native file "an export copy" when its family holds exports. That is true of 67 of SINAN's 98 families here (2,114 export files beside the `.dbc`), so for them the rule never fires and the smallest file wins: the CSV.

So the build read the CSV, found its tables did not fit the plan, counted a mismatch, dropped the rows and went on. `retrieve.fetch` had the remedy (read again without the refused path); the build did not, and a mismatch beside built years was counted and not said (`reason` is written only when the whole family has no rows).

**Decision.**
- **A refusal is followed by the next representation.** When no table of the chosen file fits the family's plan, the build reads the publication's other representations of that family, one at a time, until one fits. The next is chosen by the same call that made the first choice (`choose_representations(..., refused=)`): refused files are not candidates, and an export among them is the measurement that the family's layout is the native files', so the family clause of ADR-0135 no longer applies to that publication and its `.dbc` is read before its other exports. `retrieve.fetch`'s retry passes its refusals the same way (ZIKA 2019: three refused exports before the DBC, 7.6 s, became one, 2.0 s).
- **A publication none of whose representations fits is said.** One `errors` entry per publication (exit 1) names every representation tried and the signature it measured; `files_mismatched` counts publications, not representations; the partition is not written from it.
- **What was refused is counted.** `representations_refused` and `refused_examples` in the build counts; `build_lake(release=True)` releases the refused files with the rest.
- **A family whose partitions are all current says so** instead of "decoded and matched the plan but yielded no rows" (the check in `verify` still reads it as explained).

**Not done.**
- *Placing the refused export in a family of its own from the schema decode measured.* Measured on a copy of the real catalog: with the ZIKA 2016 CSV's signature in `file_schemas`, `build_families` splits `SINAN_ZIKA_8a20063414` off, and `choose_representations` then refuses the publication (`RepresentationConflictError`: its JSON and XML, never read, stay in the DBC's family). Making it hold needs a header census of every export (2,114 files of three formats in 37 diseases), and the family would be a lossy copy that no rule reads while the DBC exists. It stays the answer if a publication has no native file (no publication of SINAN's 3,214 family files lacks its `.dbc`).
- *Narrowing the family clause to `.dbf`.* The 39,840 SIH candidates sit in families holding `.dbc`, `.dbf` and XML together; the choice for SIH, SINASC, SIM and SIASUS is byte-identical before and after this change (selection hash), and it stays so.

**Consequences.**
- A first build of a SINAN publication whose export differs from its DBC costs one download and decode of the export before the DBC is read. The partition's fingerprint is that of the chosen file, so a second build finds it current.
- Provenance says which file the rows came from (`lake_partitions.source_paths`): the DBC for ZIKA 2016-2019 and CHIK 2016-2019, the CSV for ZIKA 2015 and CHIK 2014-2015, whose columns, row counts and (apart from the date text, `2015-01-04` against `20150104`, which both land as `date32`) values equal the DBC's.
- Build and `retrieve._select_files` still each query a family's files and call `choose_representations`: one job in two places (`ARCHITECTURE.md` §5).

**What would overturn it.** A publication whose export is the better edition and carries the family's columns while the DBC does not: the choice would then be by edition, not by native-first, and the refusal list would be the evidence.
