# One transport, three declared sources, population series as data (ADR-0188)

Regime: base commit `2e09a61` (`pegasus-core-fixes`) against branch `struct-intake`, 2026-10-14. Network probes and landings into a scratch root
(never the real one); the real root `pegasus_core_data` and the repo's `pegasus_data_home` read only. Artefacts: the probe scripts and their JSON
under the agent's scratchpad (`s_intake/`: `probe_sources.py`, `probe_population.py`, `run_b.py`, `t_transport.py`).

**Transport** (same call, base then branch; sha256 of the bytes or of the parsed answer):

| call | base | branch |
|---|---|---|
| TabNet `br_macsaud.cnv` (383,336 B), IPEA AMC 2000 (22,654,976 B), IBGE state mesh (98,502 B), INMET stations API (261,414 B) + NOAA history (2,914,601 B), DEMAS OpenAPI (113 paths), SIDRA table 1737 metadata, SIDRA 500 on an unknown table | answers | **identical bytes / payloads**, same status |
| S2iD events (86,323,744 B) | 127.6 s | identical sha256, 137.2 s |
| IBGE `/localidades/municipios` (5,571) | **fails after 77.5 s** (`CERTIFICATE_VERIFY_FAILED`: httpx used `certifi`) | 1.4 s |
| BR-DWGD release (Zenodo 7824919 -> 13906834) and ranged reads of its 2,007,739,347 B file | **fails after 53.6 s** (403 over IPv6) | 1.4 s, 4,096 B head and 8 B tail |
| `build_source("health_regions")` (27 DEMAS requests, 5,570 rows) | 31.1 s | 32.0 s, **identical table** (sha256 of the rows) and files |

`t_transport.py` against a local server: 404 raises `SourceAbsent` after 1 request; 500 x2 and 503 x2 retried; a cut body resumed with
`Range: bytes=30000-` and the validator; another version's validator not spliced; an old partial file without validator discarded; 416 with the
same length accepted, with another length restarted; the interval enforced across threads.

**S2iD, INEP, ANS landed from the raw files the real root caches, fields against the real root's** (built 2026-10-04 by the old readers):

| source | records landed | independent count | field rows | field vs real root | first landing, old reduction -> records |
|---|---|---|---|---|---|
| S2iD events | 76,190 (0 undated, 0 unallocated) | 76,190 (pyarrow, quoted line breaks) | 76,190 | **equal on every column** (0 rows differ either way) | 3.2 s -> 15.0 s |
| INEP 2023 (408 columns) | 217,625 schools | 217,625 (lines - 1) | 83,550 | **equal** (municipality, municipality7, margin, category, value); total 47,304,632 | 1.0 s -> 26.9 s (a rerun: sidecar, 3.1 s) |
| ANS Dec 2022 (28 files) | 14,070,694 | equal in each of the 28 files | 352,501 | **equal on the 352,501 placed rows**; the real root's 353,283 held 782 more (see below) | 11.9 s -> 120.0 s |

`query("S2ID-EVENTOS")`, `query("INEP-EDBASICA")` and `query("ANS-ICB")` on that root return 76,190, 217,625 and 14,070,694 rows.

ANS: 41,879 of 50,530,569 medical-hospital links (0.08 %) are in no IBGE municipality (`XX` file 38,186 + 3,693 in the states' `...0000` codes);
the old field carried them under their raw code, the records keep them and the report counts them (`unallocated` 14,874 rows). Placed medical
links: 50,488,690 = the old total less those. `sus_dependent.load_ans`: `medical_total` 50,530,569 as before, `municipality_unknown` 38,186 -> 41,879,
`age_incorrect` 187 -> 184 (3 in the dropped codes), 385 of 170,482 cells gone (all in non-IBGE codes). Disk: the three record sets are 159 + 39
+ 21 MB; the raw caches they replace are 1.9 GB + 118 MB + 86 MB in the real root and are no longer read. The records cost a first landing 5-10 x
the old reduction because every column of every row is kept.

**Population series** (repo home, read only; 5 `load_population` tables, 2 serve bodies, the descriptors): every table **equal** to the base's (POPSVS
2005 + 2024 1,804,680 rows; POPTCU 2010 + 2020 11,135; POP 2005 367,224; projpop 2010 4,914), serve bodies identical (sha256), refusals identical.
New: `municipality_code_widths` (POPSVS [7], POPTCU [6, 7], POP [6]); the legacy `censo` folder is no longer read as `CENSO`; `load_population` refuses
a year the files do not hold. `Builder.population` rebuilt POPTCU (33 files) and the covariates (15 files) into a scratch root from the FTP:
the parquet files carry the same names and rows as the repo home's (181,102 and 2,189,622 rows, 0 differing).

**Size.** Python: 720 lines added, 909 removed (net -189, with `transport.py` 267 new and the three readers and builders gone); YAML +240
(three declarations, the series). Whole suite on the final commit (`-m "not network"`): 1,731 passed, 28 skipped, 1 deselected, 7 min 52 s.
