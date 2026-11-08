# The one map, and the 733 open questions (2026-11-08)

**Scenario.** What does an agent find when it asks pegasus_data what it holds? `pegasus-data compendium`, `search` and
`info` were run on the real home `C:\Users\Galaxy\pegasus_core_data` (master 009e129, then this change). The open
questions were audited against the catalog, the lake and `sources/`. The research notes are in the session's scratch file;
the verdicts are below. ADR-0216.

**Before.**
- **The map** was 6.1 MB: 30 systems, 173 datasets, 4,755 variables.
  - **No columns** for 24 datasets: SISAGUA ×8, SRAG, FA ×2, SNGPC ×2, INEP, ANS, S2ID, REGIAO, SIES and others.
  - **No context fields, roles, links or SIDRA tables.**
  - **"No codelist"** for 1,489 internally coded columns. A query labels them anyway: SIH-RD AC 2023 `COBRANCA` renders
    "Alta melhorado", from `label_bindings` (13,899 decisions).
- **Search.** `search voos` found nothing, and `search precipitação` found ICD-9 E957 (a suicide code).
- **733 open questions.**

| key family | n | verdict |
|---|---|---|
| `reference.mixed_code_widths` | 676 | not a hazard: labels join on the exact code string; generator removed |
| `inventory.prefix_system_changed` | 49 | no reorganisation: prior files all current (3 PRELIM promoted to FINAIS); SINAN in two trees, SIM/SINASC shared kits, POP two series; CM a true collision, refiled (47 files to SIHSUS) by `inventory` |
| `semantics.cod_idade_units` | 1 | answered: 0 unknown, 2 days, 3 months, 4 years, 5 = 100 + IDADE; measured on SIH-RD 2023, 13.36M rows |
| `semantics.unlabelled_codelist` (COMPLEX, FAECAIHS) | 2 | stale: TabNet recodes of PROC_REA; COMPLEX decodes from COMPLEX2.CNV; FAECAIHS is no column |
| V2, V6, V8, V9 | 4 | answered in their 2026-08/10 evaluations; V8 was re-noted by `build.py` on every population run |
| `discovery.uploads_directory` | 1 | a directory refused to anonymous users (550 on CWD/LIST/NLST/SIZE/MDTM; curl -v); accepted gap |

**After.**
- **Questions.** None open in the home catalog, the label-build catalog or the rebuilt seed (742 resolved).
- **The map** builds in 22 s, 25 MB. It holds:
  - 173 datasets, 43 of them with rows held (1,568,910,208 rows, read from the lake's Parquet footers; SIH.RD 194,154,506,
    as the catalog's partition table). *Corrected the same day: first written as 41 and 1,085,164,531, because the lake
    walk matched the ontology's system codes (SIH) and not the crawled names the folders carry (SIHSUS), and missed SIH
    and SIA;*
  - 5,166 variables and 10,502 dataset columns, each with its query-time codelists and its fill where held;
  - 122 context fields, 11,003 roles, 127 event types, 16 links, 60 aggregates, 9,336 SIDRA tables and 213 operations;
  - 19,452 search entries, each with its call.
- **Columns still unknown:** five datasets. SIH.CM and SIASUS.IMPBORL have no decoded schema; the other three are the
  TabNet, TabWin and TabDOS tooling.
- **Search answers:**
  - `escolaridade mae` returns six columns across SINAN, SIM and SINASC, each with `query("…", select=[…])`;
  - `link deaths` returns the link specs and `linked_deaths`;
  - `age standardised` returns `age_standardised_rates`.
- **Still missed by word matching:**
  - "rainfall" (the field says precipitation);
  - "voos" (the layer says air passengers);
  - "oftalmolog" (the field says ophthalmologists).

  **Tried and dropped: retrieval by meaning.** Qwen3-Embedding-0.6B over the 19,792 entries put the answer to each of
  ten such questions in its first three, rainfall and "oftalmologistas" included. The cost was:
  - torch and a 1.2 GB model;
  - 8 minutes of GPU to embed the entries;
  - 2 s to load the model for each search.

  The readers are people and language-model agents, and they lack the list of what exists more than they lack a matcher.
  So `info()` with no target prints that list whole instead (366 lines, 45 KB): 170 datasets, 122 fields, 16 links,
  60 aggregates and the operations by area.

**Settled on the way.** Dados_Abertos' `Populacao_SVS/POP22` is POPSVS: all 902,340 municipality × sex × age cells equal
`IBGE/POPSVS/POPSBR22` (210,862,983). Recorded in DATA_SOURCES §6.1.

**Products, and the stores nothing described.** The map had described datasets and fields only. ANAC's flights, census
commuting, coach and boat links, the grid, tracts, CEP points, daily climate, code trees and the modelled tier were each
visible only as a function name: "air passengers", "biome" and "POPSVS" occurred 0 times in the overview.
- **Declared:** 46 products in `curation/products.yml`, each read from its module, with source, grain, period, call and
  stores:
  - codes 9, index 8, modelled 7, mobility 6, geography 6, places 3;
  - care, population 2 each; climate, prices, register 1 each.
- **Read as members** from their own files: population series 6 and geography memberships 22.
- **The overview** is 422 lines and 57 KB.
- **The claim check** lists every home folder that nothing describes. Before the declarations it listed 31. After, it
  lists 4:

  | store | size | what |
  |---|---|---|
  | `lake/records` | 8,715 MB | SI-PNI per-dose records 2023, an interrupted October probe (a `.tmp` part): no reader |
  | `registries/tse` | 73 MB | TSE electorate profile 2022: held, no reader (needs a TSE-IBGE crosswalk) |
  | `registries/pni` | 1 MB | that probe's dictionaries and code tables |
  | `lake/demas` | 0 | empty |
- **Counts in `info`.** `info <dataset>` and `info <system>` now read files, years, columns described and rows held from
  the map. SRAG.NOTIF shows 194/194 columns and 4,666,910 rows held, where the FTP-header count had shown none.
