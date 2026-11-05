# RUNBOOK.md

Operating commands, as the code has them today (2026-09-28). Every command
takes `--help`. The CLI's 46 commands and 3 sub-apps are being consolidated
(ARCHITECTURE §5); when a command changes, this file changes in the same
commit.

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
PD=C:/Users/Galaxy/miniconda3/envs/pegasus/Scripts/pegasus-data.exe
export PYTHONUTF8=1
```

---

## 1. Checks before a commit

```bash
$PY -m pytest -q -m "not network"        # ~9 min; a regression net, not grown
$PY -m ruff check src scripts tests
$PY scripts/check_docs.py
```

## 2. Live scenarios (how progress is measured)

```bash
$PY scripts/live.py --list
$PY scripts/live.py sih_rd sim_do           # named scenarios
$PY scripts/sweep_undecoded.py               # undecoded values, 16 datasets
$PY scripts/def_evidence.py data/probes/live/sweep_undecoded.json          # which .CNV the .DEF offers each
$PY scripts/measure_cbo_conversion.py AC PE BA RJ MG   # CNES's own CBO 94 -> 2002 conversion, measured
$PY scripts/build_bridges.py                     # every classification bridge -> resources/bridges.parquet
$PY scripts/registry_fields.py                   # register-like fields (CNES, INE, CNPJ, CPF/CNS, IBGE, CBO) and their bindings
$PY scripts/live.py --all --fresh           # everything, on an emptied home
$PY scripts/live.py --show <run-id>
```

- Establishment, team and CNPJ names (the registry tables) are built, never fetched by a read (ADR-0176):
  `$PD registries build CNES [--refresh]` (SIH's names need CNES's kit, 127 MB, once; `SIASUS` for `INE_EQUIPE`).
  Without it a `load`/`query` leaves those labels null and says this command in one warning.
- Decode coverage on records: `$PY scripts/decode_coverage.py --root HOME --out x.json` renders each lake family's latest partition whole, eight coded columns at a time (`--only SIM-DO,SIHSUS-RD` restricts it), and counts its coded columns (labelled, words as filed, bare, with the codes left bare and their cells). A dataset the root does not hold is measured on one small file
  landed into a scratch home, `$PD build --root HOME --family F --uf UF --years Y --limit 1` (a few hundred KB each; 111 datasets, 355 MB, 2026-10-24), and `$PD curate --root HOME` after a curation edit.
- The live home is `~/pegasus_live/home` (override: `PEGASUS_LIVE_HOME`),
  deliberately outside the repository.
- Records go to `data/probes/live/<run-id>/`. A run that informs a decision
  gets an entry in `EVALUATION.md`.
- Each scenario has a 30-minute timeout (`PEGASUS_LIVE_TIMEOUT`).

## 3. Where the data goes

```bash
$PD where                                    # which layer decided each path
$PD config set --root D:/datasus [--blobs E:/cache] [--catalog C:/fast]
```

- One home per user (ADR-0200). The per-user config file names it (here
  `C:/Users/Galaxy/pegasus_core_data`). With nothing set it is the per-user
  data directory (`%LOCALAPPDATA%/pegasus-data`), never the working directory.
  PegaSUS resolves the same root, and `PEGASUS_DATA_HOME` is the one name.
- `$PD adopt <other-home>` shows what another home holds that this one lacks.
  `--apply` moves its downloads, with their fetch history and each digest
  checked, and its registry files absent here. Its lake and semantic tables
  are recomputed here, not moved. `--remove` then deletes the other folder
  (links inside it removed as links). Crawl the adopted directories afterwards
  (`$PD crawl --prefix <dir>`).
- The label pack's build catalog is `<root>/_label_build/catalog.sqlite`
  (`config.label_build_catalog()`), read by the maintainer scripts. It is not a
  data home, and the repository holds none (ADR-0208).
- To act as a fresh user, set `PEGASUS_DATA_HOME` to an empty directory
  outside the repository, and `adopt --apply --remove` it when done.
- Decoding is admitted machine-wide (`decode/admission.py`): `PEGASUS_DECODE_SLOTS`
  (default 4 on 32 GB), `PEGASUS_MIN_FREE_GB` (default max(4, 15% of RAM)),
  `PEGASUS_ADMISSION_WAIT` (seconds, 1800). A decode that waits is queued, not hung.
  A process's decoder pool and the partitions a build makes at once number
  `PEGASUS_DECODE_WORKERS`, by default the slots.

## 4. Getting data

```bash
$PD query SIH.RD --period 2023-01 --geo AL,SE --out sih.csv     # = query(); --present/--values/--names, --dictionary FILE
$PD query SIH.RD --period 2020..2023 --geo AL --select DIAG_PRINC --out d.parquet
$PD translate <file> --system SIHSUS                           # label files you already have
$PD explore [SIH.RD]                                           # what exists, offline
$PD info SIH.RD                                                # what it is
$PD facts SIH.RD                                               # what the curation documents of it, with sources
$PD garbage-codes [GBD2017] --out garbage.csv                  # the GBD garbage codes with level and package (curation/garbage_codes.yml)
$PD price-index --years 2014-2025 --reference 2025-12 --out ipca.csv   # IPCA by month with the deflator to December 2025 (fetches SIDRA 1737 once)
$PD publications SIH.RD --years 2014..2023 --uf AL --out files.csv   # the files it was read from: size, date, digest, rows, status
$PD search raça                                                # which columns and codes mean what
$PD download --system SIHSUS                                   # maintainer: raw files into the cache
$PD extract SIASUS-PA --years 2010-2025 --filter PA_PROC_ID=0202030768,0202030873   # a dataset too large for the lake:
                                                               # the filters' records, its files read and released one by one
```

## 5. Maintainer builds

| step | command | notes |
|---|---|---|
| crawl the tree | `crawl` | listing only; 80k files took 8 s on 2026-08-30 |
| filenames → strata | `inventory` | no network |
| column census | `schemas` | ranged header reads |
| harvest meaning | `semantics` | TAB kits, `.CNV`/`.DEF`, SIGTAP, curation |
| families | `families` | |
| label bindings | `bindings` | one decision per family and field (ADR-0072); ~2 h for the tree |
| code tables | `reference` | `lake/reference/` |
| the lake | `build`, or `build_lake(dataset, years, root=)` from Python (no labels by default; PegaSUS's `update` calls it for a plan's datasets) | a year with a national file (SIM, SINASC) is built from it alone unless `--uf` names states; a kept partition is not rewritten; the downloads a verified partition holds are released after the build (`--keep-downloads` or `keep_downloads = true` keeps them; ADR-0208) |
| rewrite modelled products with the current encoding | `reencode-modelled PRODUCT [VERSION ...]` | floats in BYTE_STREAM_SPLIT; each row group read back equal before the file is replaced |
| free the downloaded files | `prune [--dry-run]` | deletes blobs whose every path is in a verified lake partition; refetched only for a rebuild. The DBC bytes cannot be regenerated from the lake. A build does the same for its own files; `prune` releases what was built before ADR-0208 |
| population | `population` | IBGE series |
| curation into the catalog | `curate` | 4 s |
| the seed and the manifest | `python scripts/build_resources.py` (the label build catalog; another catalog as argument) | 20 s; after `crawl`, `inventory`, `schemas`, `families`, `curate` (ADR-0067) |
| re-read unchanged kits | `pegasus-data semantics --system X --force` | otherwise a kit is skipped when its blob and the parser are unchanged (OQ-24) |
| describe large zipped DuckDB exports | `pegasus-data schemas --system DADOS_ABERTOS --whole-up-to-gb 8` | fetches each export whole into the blob store (FTP or mirror) to read its tables (OQ-54) |
| an aggregate artifact as an Excel workbook | `pegasus-data workbook sih_rd_municipality_month --out book.xlsx` | each sheet its own aggregation; stocks reduced by their declared rule |
| Grade Estatística 2022 | `pegasus-data grade` (then `pegasus-data grade-cells --municipality 2704302 --resolution 1000 --out x.gpkg`; Python `grade_cells(...)`) | 711 MB of zips once, 13 min; checked against IBGE's published totals (ADR-0203) |
| Census 2022 tracts | `pegasus-data tracts`; Python `census_tracts(uf="27")`, `tract_population(municipality="2704302")` (sex × 11 bands, `suppressed`), `pegasus_data.sources.ibge_tracts.tract_mesh(...)` | 38 MB once, 21 s; prints what suppression leaves out per municipality (ADR-0203) |
| CNEFE 2022 and CEP places | `pegasus-data cnefe [--uf AL ...] [--keep-raw\|--delete-raw] [--force] [--no-check] --json` (lands `lake/cnefe_2022` and `lake/cnefe_2022_cep`, checks against IBGE's aggregate by CEP into `registries/ibge_cnefe/manifest.json`); read `pegasus-data cep-points [--uf AL] [-m 270430] [--cep 57160000] [--tracts --out x.parquet]`, Python `cep_points(...)`; scenario `scripts/live.py cnefe_cep` (SIH-RD against the CEP table) | 3.9 GB download, 3.5 GB lake, about 45 min for all 27 (run detached); idempotent; a zip is deleted only under 15 GB free (ADR-0205) |
| proximity graphs and points pack | `pegasus-data geography` (builds the geography pack, then the points and proximity packs from the grade); or `python -c "from pegasus_data.proximity import build_proximity_graphs; ..."` with `grade_root=<root>`, and `build_regic` with `registries/regic/` | 60 s from the grade; REGIC links in the pack are kept |
| mobility layers between municipalities (ADR-0211) | `pegasus-data mobility [--layer census_commuting\|ibge_links\|anac_air]`; read `pegasus-data graph air_passengers --period 202401-202412 --out x.csv`, Python `proximity_graph("commute_work_2010")`, `graph_kinds()`; re-run `--layer anac_air` to take a new ANAC release: it compares the held file with the server's (size and 16 sampled windows) and downloads again only when the data changed | Census microdata ~3 GB of zips; ANAC 361 MB at ~0.3 MB/s |
| daily climate (MERGE, SAMeT) | `pegasus-data climate-update [--variable tmax] [--start 2000-01-01] [--end ...]` daily (it re-reads a file the server lists with a new time: SAMeT's provisional days come back final about 7 days later); read `pegasus-data climate --municipality 2704302 --start 2024-01-01 [--weight area] [--as-of 2024-03-01] [--weekly] --out x.csv`, Python `climate_daily(...)`, `climate_weekly(...)`; one day's grid, read now and not kept, `pegasus_data.sources.cptec.day_grid("tmax", "2026-10-20")` (sample it at `grade_cells` for a sub-municipal reading); validate `python scripts/cptec_validation.py --root <root> --year 2023` | backfill 2000 on: about 39,000 files, 63 GB read and not kept, 4 h; 2.4 GB stored (ADR-0204) |
| care-flow graph and its products | `pegasus-data graph SIH-RD --period 2022 --root <home> [--to establishment] [--by COMPLEX] [--measure admission.length_of_stay] [--derive profile\|catchments\|communities\|regions] [--resolution 4] [--against health_region_current] --out x.parquet` (`pip install pegasus-data[network]` for communities and regions) | national year: a few minutes after the files are cached; run `BR`, not a state (SIH files are by hospital state). `--measure ROLE` (repeatable; a role of `pegasus-data roles`, never a column) adds `<role>_n` and `<role>_sum` to each edge (ADR-0201); Acre 2023 in 14 s |
| the canonical ICD-10 table | `python scripts/build_icd10.py [catalog]` | seconds; reads `sources/cid10csv_v2008.zip` and `sources/cnvs_cid10_v2019/` (`CNVS_CID10_v2019.rar` from `SIM/CID10/TAB/`, extracted), the catalog for the kit codes it carries, and refreshes its manifest entry; then `build_code_structures.py` (ADR-0087) |
| code trees, concept lists and ICD-10 attributes | `python scripts/build_code_structures.py` | after the ICD-10, SIGTAP, CBO and CNAE tables and the label pack; then `build_resources.py` registers the files |
| the canonical CNAE 2.0 table | `python scripts/build_cnae.py` | seconds; IBGE API responses cached in `sources/ibge_cnae/` (ADR-0087) |
| the label pack | `labelpack` (`--carry-from <old pack>` when the default, the shipped pack, is not the last good one) | after `semantics`; keeps windows the catalog lacks (ADR-0095) |
| an aggregate | `aggregate-build <recipe>` | base cuboid under the data home |
| everything | `all` | empty directory to lake |

## 6. The frontend

`../pegasus_view` reads `serve/`:

```bash
$PY -m pegasus_data.serve --help
powershell ../pegasus_view/start-pegasus.ps1 [-Records]   # both services, waits until ready
```

`-Records` exposes `/api/v1/records`, which serves unmodified microdata
including personal identifiers. It is off unless asked for.

## 7. Releasing

Frozen procedure: `docs/history/RELEASING.md`. Publishing to PyPI is an
outward action and needs the user's explicit go-ahead (CLAUDE.md §4). CI
(`.github/workflows/checks.yml`) triggers on pushes to `main`, but the branch
is `master`, so pushes currently run no CI (STATUS).

## 8. Snapshots of files DATASUS rewrites (ADR-0141)

```bash
$PD snapshot --dry-run                 # observe, report what would be fetched (files, bytes), fetch nothing
$PD snapshot [--only sinan_prelim ...] # fetch what changed since each file's last kept version
$PD snapshot --versions DENGBR26       # the kept versions of matching paths (mtime, size, sha256, observed)
$PD query SINAN.ZIKA --period 2026 --as-of 2026-09-30   # the files as they were kept on that date
```

- Declared series and their disk budget: `curation/snapshots.yml` (SINAN/SIM/SINASC preliminary in full;
  SIH-RD, SIA-PA, CNES-ST of the last 14 competences, SIH and SIA for a few states). The first run on a
  home fetches the whole declared set; a run after that fetches only what changed, and the report gives
  `bytes_downloaded`, `versions_kept` and `store_bytes`.
- It refuses to start under 4 GiB free RAM, if it would leave under 10 GiB of disk, or above `--max-gb`.
- Versions are never pruned (`prune` skips their blobs). One run holds one FTP connection.
- While the FTP data channel is down (ADR-0122) it observes by `MDTM`/`SIZE` and takes bytes from the
  mirror only when the mirror's size and original mtime equal DATASUS's.

**Daily schedule** (not created yet: the session that built this could not register a task; run the first line once, as the user; current user, no admin rights; the task runs `scripts/snapshot_task.cmd <data home> <log>`):

```bat
schtasks /Create /TN PegasusSnapshotDaily /SC DAILY /ST 04:00 /F /TR "C:\Users\Galaxy\LEVI\projects\pegasus_data\scripts\snapshot_task.cmd C:\Users\Galaxy\pegasus_core_data C:\Users\Galaxy\pegasus_core_snapshot.log"
schtasks /Query /TN PegasusSnapshotDaily /V /FO LIST
schtasks /Run /TN PegasusSnapshotDaily     # once, by hand
schtasks /Delete /TN PegasusSnapshotDaily /F
```

The log is `C:\Users\Galaxy\pegasus_core_snapshot.log`: per run a date line, the JSON report and an `exit=` line
(0 fine, 1 errors or failed listings, 2 refused).

## 9. IBGE SIDRA (ADR-0142)

```bash
$PD sidra scan [--all]                       # registry from IBGE's metadata: curated and municipal tables first, resumable, about 1 table a second
$PD sidra search esgoto --level N6           # find tables; then: sidra show 6805 [-c 11558]   sidra survey   sidra rank
$PD sidra plan 9606 -v 93 -p 2022 -c 86=all -c 2=all -c 287=all    # the requests under SIDRA's limits; nothing is fetched
$PD sidra fetch 9606 -v 93 -p 2022 -c 86=all -c 2=all -c 287=all   # into <lake>/sidra/facts/; resumable
$PD sidra facts 9606 -p 2022 --out f.parquet # read back with labels, units and Total flags joined on
$PD sidra curated --group housing_sanitation [--fetch]   # the author's compendium: its cost first, then fetch
$PD sidra series population_age_sex --fetch --validate   # stitched series (curation/sidra/series.yml); cells checked against totals
$PD sidra series literacy_15plus --report              # its comparability, gaps and the places with a figure per census; fields: `$PD fields --name persons_15_plus`
$PD sidra check                              # compendium and axis maps against IBGE's names
$PD sidra rebuild 9606                       # re-derive a table's parts from the cached responses, no request
$PD fields --name climate_monthly --name temperature_months --name air_temperature --name air_temperature_monthly_max --name air_temperature_monthly_min --name precipitation_months --name precipitation_mm   # BR-DWGD climate (ADR-0178): latest Zenodo release of the municipal means (v3.2.3), 3 x 0.5 GB by byte range into `registries/brdwgd`, ~30 min the first time, ~20 s after; then `python scripts/climate_validation.py --root <root>` against INMET's station-months. INMET's own base: `$PD fields --name climate` (offline from `registries/inmet`)
$PD fields --years 2018,2025 $(python -c "from pegasus_data.fields import declared_fields as d; print(' '.join('--name '+k for k,v in d().items() if v.get('intake')=='sisagua_surveillance_basic'))")   # SISAGUA surveillance (ADR-0192): the Portal's yearly zips (85-212 MB each) landed as records, then the 19 fields by municipality and month; any `--years` span, 2014-2026 is 1.79 GB. An intake source's fields are named one by one (`--name`), the source's other families by their own names (`sisagua_surveillance_other_analyses`, `sisagua_surveillance_cyano_analyses`, `sisagua_control_counts`)
$PD intake-periods [--source sngpc_industrialized] [--dry-run]   # date the catalog's publications of the declared file sources by their units' periods (a `months:` pattern is one publication per month: SNGPC, ANS), landing nothing; once for units registered before a month was a fact of the unit (EVALUATION 2026-10-24), idempotent; `--dry-run` counts
```

- Every response is kept under `<root>/registries/sidra/http/` (gzip, with URL, size, SHA-256, time); the
  facts are derived from it. A request is one Parquet part; a stopped fetch resumes at the next missing part.
- The server is shared: one process, one request at a time, 0.3 s apart. A change to the planner changes the
  URLs, so a re-run after it fetches again; the facts of the old plan stay valid and duplicates are dropped on read.
- Measured throughput: about 8,000 values a second at 48,000 values a request (EVALUATION 2026-10-05).

## Record linkage (ADR-0107 to ADR-0112)

| task | command |
|---|---|
| list the declared links | `pegasus-data link` |
| run one (reused from the lake when already run) | `pegasus-data link sih_deaths_to_sim --period 2022 --geo RR [--method probabilistic] [--out pairs.parquet] [--refresh]` (`--refresh` recomputes past a stored run) |
| follow a diagnosis' admissions to the death certificate of any cause (a cohort link, run per codes; ADR-0194) | `pegasus-data link sih_admissions_to_sim --period 2018..2022 --geo AL --codes I21,I22 [--match any]`; in Python `pegasus_data.linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023), geography="AL")`: 46 s a run for Alagoas, then read from the store |
| link a state against the nation (scope-invariant, ADR-0120) | `pegasus-data link sih_deaths_to_sim --period 2022 --geo SE --right-geo BR --method probabilistic` (needs the national run stored first: its channels and calibration) |
| merge stored links into persons | `pegasus-data link-entities --period 2022 --geo BR` |
| discover which fields two datasets share people through (ADR-0119) | `pegasus-data link-discover SINASC-DN SIH-RD --period 2022 --geo RR [--top 10]`; every pair: `python scripts/link_discovery.py 2022 BR` (roles cached under `data/probes/linkage/discovery/cache/`) |
| national measurements | `python scripts/linkage_study.py bits|channels|flows <dataset> <period>`, `coverage <period>`, `joins <period> <uf>` |
| serve link reports and timelines | `python -m pegasus_data.serve --port 8000 --allow-records` (timelines are microdata) |
