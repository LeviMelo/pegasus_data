# Intake landing: replaced units, unfinished API units, classed transport errors (2026-10-14)

Scenarios of the review's findings 8-11, 22 and 23, run before (`15c1cf7`+`a539314`) and after on synthetic units under a scratch
data home (`pegasus_data` has no network-free source with real records, and the defects are in how a re-landing treats what it
replaced). The scripts are throwaway; the counts are the evidence. Regime: this commit, Windows, DuckDB/SQLite, `file://` and loopback.

| Scenario | Before | After |
|---|---|---|
| unit `a` (3 rows) and `a-b` (2 rows) landed, then `a` re-landed after a column gained `type: integer` (new signature) | 8 rows readable (`a` twice), 2 families | 5 rows, 2 families until `a-b` follows, then 1 family; the old family folder and its catalog rows gone |
| the independent line count disagrees with the landed rows | records registered, then the error | `_LostRecords`, lake, catalog and sidecar byte-identical to before |
| API table of 5 rows read (pieces of 4), then grown to 9 | lake stays at 5 rows; the grown piece is cached as complete | 9 rows; the short last piece is `incomplete` and read again (4 requests on growth, 2 on a plain re-run) |
| an answer `{"erro": ...}` where the list `items` is expected | read as the end of the data | `ValueError` naming the keys it has |
| a month not yet published (HTTP 404) in a 3-month pattern | 195 s of retries, then the source stops | 0.02 s, recorded as `{"absent": 404}`, the other two months landed, fields derived |
| a partial download, then the server serves another version | spliced onto the new tail | `If-Range` mismatch: whole body re-read; an old `.part` with no validator is discarded |
| CNES-PF aggregate after a group gains a CBO prefix | stale, or 3.8 GB again | re-grouped from the kept (municipality, CBO) and (municipality, CBO, CNS) tables, no file read; equal to the previous aggregator on a 400-row PF file |

## Second round: the extract filter, the second DEMAS reader, one fold, `explore`, `info`, `suggest`, placement

Read against the real catalog of `pegasus_core_data` (read-only; 208,239 data files) or the synthetic scratch home; regime: branch
`fix2-intake`, same machine, warm cache.

| Scenario | Before | After |
|---|---|---|
| `extract SIASUS-PA --years 2010-2025 --filter PA_CIDPRII=B58` (a typo; 5,578 files) | every file fetched and decoded, then an "complete" extract of 0 rows | `ValueError` in 0.06 s from the header census (62 fields, 16 years), naming the closest field `PA_CIDPRI`; a column only some years' layouts lack is reported, not refused |
| `explore()` over the 208,239 files | 1.78 s (2.76 s on the review's day): every file into a dict, every file bound | 0.28 s: the store counts by (system, series), each pair bound once; `SIHSUS` 0.95 -> 0.35 s, `SIH-RD` 0.49 -> 0.19 s; 11 calls (all four levels, `role=None`, an unknown system) equal row for row |
| `info(field_name="SEXO")`, no target | the CIH definition as "what SEXO is", datasets of every system, 200 at most | 9 definitions (CIH, CIHA, FA, IBGE, PAINEL_ONCOLOGIA, RESP, SIHSUS, SIM, SINASC), each with its source and datasets, and a note; 0.63 s; `info("SIM", field_name="SEXO")` lists SIM's 8 datasets only |
| `load_settings(root=X)` with `PEGASUS_LAKE_DIR` set | `lake` from the environment, `catalog` from X | all four places X's; `origins['lake']` = "derived (from the explicit root; not used: PEGASUS_LAKE_DIR=...)" |
| `aggregate-suggest` on SINASC-DN | 20 columns "structural" by substring (`CODANOMAL`, `IDANOMAL`, `ACIDTRAB`, `NUM_FILHOS`, `CONTRACEP1`... among them) | 15 by the declared roles (identifiers, dates, the event's place, link and excluded columns); the skipped names and reasons printed; `--root` honoured |
| `_fold` in `intake`, `bnafar`, `geography` | three punctuation rules | one (`textenc.fold`: accents, case, hyphen and apostrophe between words). On the 1,901 CATMAT names 3 of 2,729 test terms differ, all leading or trailing hyphens of my term generator; on the geography pack the contested classifications stay 359 and one label class merges (`Centro Sul` / `Centro-Sul`) |
| IBGE mesh | URL defined in `inmet.py`, `geography.POINT_SOURCES` and `geography.mesh`, three cache files | `geography.mesh_file`, one URL, one file per (level, quality) in `registries/ibge_mesh` (`state_minima.json`: 98,502 bytes, as before); an existing `registries/inmet/mesh_max.json` (56 MB) is no longer read |
| `pegasus-data demas` | 500-row samples of two declared sources landed in `lake/demas`, own HTTP client | the OpenAPI document (113 paths) persisted through `intake.get_json` in 4.4 s; the 5 endpoints `intake.yml` declares are checked against it (all served); no sample, no `lake/demas` |

`roles`, `events` and `structure` read the shipped declarations and resources, never a data home, so they take no `--root` (review finding
25 was right only for `aggregate-suggest`). `origin.static` and `cache_empty` are documented in `intake.yml` and set on no source: SIES grows
monthly, and one BNAFAR-wide `cache_empty` would freeze its current month as empty.
