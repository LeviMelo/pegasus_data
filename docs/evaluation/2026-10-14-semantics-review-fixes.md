# The semantics review's findings, fixed and measured (2026-10-14)

Regime: branch `fix-semantics` of `pegasus_data` (HEAD 15c1cf7 and after), read-only on `pegasus_core_data` and on the
maintainer catalog (13 GB, `mode=ro`), scratch catalogs for anything that writes. Scripts were throwaways; the figures
are what was run.

| finding | before | after |
|---|---|---|
| 1 authority | a `dbf_lookup` claim replaced a `sigtap` one (SQL ranked sigtap and community 99); a corrected `dbf_lookup` v2 was ignored | `sigtap` stays; v2 replaces v1; one table (`SOURCE_AUTHORITY`) builds the SQL |
| 2 pack, no year | 5 of 152 codelists answered with the first window: SIHSUS MARCAUTI 51 "Ignorado", SIM LOCOCOR 6 "Ignorado", SINASC RACACOR 9 "Ignorado", SINASC PRENATAL 8 "Ignorado" | the current labels ("UTI adulto - tipo II COVID 19", "Aldeia Indigena", "Em branco", "1-6 consultas"), recorded as `unscoped`; no covering window and no current run answers nothing, recorded `unresolved` (`labelpack.select_windows` is the one rule) |
| 9 pack windows | `packed_mapping_covers_interval`: CID10/SIHSUS 2013 0.33 s, MUNICBR 2010-2019 0.24 s, 2000 0.46 s | 0.00 s, 0.017 s, 0.006 s (windows read once per codelist and system) |
| 3, 26 events | `field_overlap` counted flagged duplicates and ignored weights; blank `N_AIH` collapsed to one event | read through `read_events`; counts equal where the flag was selected (SIM-DO 2025 1,534,588; SINAN-CHIK 2015 52,338; SIH-RD 2025 14,512,292, no blank `N_AIH`) |
| 13 recoded kits | `Branca`/`Não branca`, `Urbana`/`Não urbana`, `Casado`/`Não casado` "the same wording" | different. Not done: a catch-all against a category (`Ign`/`Branca`) as different: on the 662,111 conflicts it recoded 11 more (system, codelist) pairs, none a recoding (SIM ANO 00 `2000` in the CID-10 kit, `Ign` in the CID-9 kit, the older kit not covering the year). The 190 recoded pairs (152 codelists) are unchanged |
| 6 `.CNV` single codes | a code shorter than the width also emitted unpadded | padded only. A rebuild would drop at least 792 unpadded/padded pairs of the same label in 53 codelists (single-code runs; the review counted 1,236 in 63) |
| 7 SUM | an all-blank cell read 0 | null (`x_sum` null; a cell with a value sums as before) |
| 8 race reliability | 42 rows with two null CNES or DT_SAIDA raised `ArrowInvalid` | flagged `unplaced`, kept |
| 10 variable docs | 4 ms (SIHSUS), 6 (CNES), 13 (SIASUS), 31-50 (SINAN) per call | 0.02 ms after the first, per catalog connection |
| 11 curation load | two lanes loaded twice and a reader saw no manual binding 2-4 times in 0.5 s | one load, no empty read in the run |
| 19 vintages | `enrich_cnpj`, 500,000 rows: 4.10 s | 1.15 s |
| 23 YAML | 365 files read: 0.21 s with the copy; 2,279 pickles (44 MB) in a flat directory | 0.017 s shared; one pickle per file |
| 27 dataset docs | 10 empty `dataset_docs` rows, from `roles.yml` (not `declared.yml`) | skipped; 132 real rows |
| 4 flows | four hand-listed | 86 derived, the four identical edge for edge |

Not done, with the reason: 24 (`lookups.py`) and 25 (`ontology.py`) belong to the query fixer; 18 (`describe` and the
ledger deciding the labelling table) crosses `api.py`; in 10 the per-file-group docs and bindings of
`render_groups.py` are not computed once per family (the docs now cost nothing to ask again); ICD columns declare no
`missing:` yet, so an undeclared `0000` is no longer assumed a sentinel (finding 21).
