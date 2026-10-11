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
PEGASUS_DATA_HOME=~/pegasus_live/home $PY scripts/sweep_undecoded.py   # undecoded values, 16 datasets
$PY scripts/def_evidence.py data/probes/live/sweep_undecoded.json          # which .CNV the .DEF offers each
PEGASUS_DATA_HOME=~/pegasus_fresh $PY scripts/measure_cbo_conversion.py AC PE BA RJ MG   # CNES's own CBO 94 -> 2002 conversion, measured
$PY scripts/build_bridges.py                     # every classification bridge -> resources/bridges.parquet
$PY scripts/registry_fields.py                   # register-like fields (CNES, INE, CNPJ, CPF/CNS, IBGE, CBO) and their bindings
$PY scripts/live.py --all --fresh           # everything, on an emptied home
$PY scripts/live.py --show <run-id>
```

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

- Any command run inside this repository adopts `pegasus_data_home/`
  (3.5 GB, gitignored), because the default adopts a data home at or above
  the working directory.
- To act as a fresh user, set `PEGASUS_DATA_HOME` to an empty directory
  outside the repository.
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
$PD search raça                                                # which columns and codes mean what
$PD download --system SIHSUS                                   # maintainer: raw files into the cache
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
| the lake | `build`, or `build_lake(dataset, years, root=)` from Python (no labels by default; PegaSUS's `update` calls it for a plan's datasets) | a year with a national file (SIM, SINASC) is built from it alone unless `--uf` names states; a kept partition is not rewritten |
| rewrite modelled products with the current encoding | `reencode-modelled PRODUCT [VERSION ...]` | floats in BYTE_STREAM_SPLIT; each row group read back equal before the file is replaced |
| free the downloaded files | `prune [--dry-run]` | deletes blobs whose every path is in a verified lake partition; refetched only for a rebuild. The DBC bytes cannot be regenerated from the lake |
| population | `population` | IBGE series |
| curation into the catalog | `curate` | 4 s |
| the seed and the manifest | `python scripts/build_resources.py pegasus_data_home/_catalog/catalog.sqlite` | 20 s; after `crawl`, `inventory`, `schemas`, `families`, `curate` (ADR-0067) |
| re-read unchanged kits | `pegasus-data semantics --system X --force` | otherwise a kit is skipped when its blob and the parser are unchanged (OQ-24) |
| describe large zipped DuckDB exports | `pegasus-data schemas --system DADOS_ABERTOS --whole-up-to-gb 8` | fetches each export whole into the blob store (FTP or mirror) to read its tables (OQ-54) |
| an aggregate artifact as an Excel workbook | `pegasus-data workbook sih_rd_municipality_month --out book.xlsx` | each sheet its own aggregation; stocks reduced by their declared rule |
| proximity graphs | `python -c "from pegasus_data.proximity import build_proximity_graphs, build_regic; ..."` with the cached IBGE sources under `registries/ibge_points/` and `registries/regic/` | 75 s; contiguity, population distance, areas, then REGIC links and cities |
| care-flow graph and its products | `pegasus-data graph SIH-RD --period 2022 --root <home> [--to establishment] [--by COMPLEX] [--derive profile\|catchments\|communities\|regions] [--resolution 4] [--against health_region_current] --out x.parquet` (`pip install pegasus-data[network]` for communities and regions) | national year: a few minutes after the files are cached; run `BR`, not a state (SIH files are by hospital state) |
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
| link a state against the nation (scope-invariant, ADR-0120) | `pegasus-data link sih_deaths_to_sim --period 2022 --geo SE --right-geo BR --method probabilistic` (needs the national run stored first: its channels and calibration) |
| merge stored links into persons | `pegasus-data link-entities --period 2022 --geo BR` |
| discover which fields two datasets share people through (ADR-0119) | `pegasus-data link-discover SINASC-DN SIH-RD --period 2022 --geo RR [--top 10]`; every pair: `python scripts/link_discovery.py 2022 BR` (roles cached under `data/probes/linkage/discovery/cache/`) |
| national measurements | `python scripts/linkage_study.py bits|channels|flows <dataset> <period>`, `coverage <period>`, `joins <period> <uf>` |
| serve link reports and timelines | `python -m pegasus_data.serve --port 8000 --allow-records` (timelines are microdata) |
