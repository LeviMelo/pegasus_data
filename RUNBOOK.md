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

## 4. Getting data

```bash
$PD get SIH-RD --uf AL --years 2023 --months 1 --out sih.csv   # = fetch()
$PD translate <file>                                           # label files you already have
$PD explore [SIH.RD]                                           # what exists, offline
$PD info SIH.RD                                                # what it is
```

`query()` has no CLI command yet (M3).

## 5. Maintainer builds

| step | command | notes |
|---|---|---|
| crawl the tree | `crawl` | listing only; 80k files took 8 s on 2026-08-30 |
| filenames → strata | `inventory` | no network |
| column census | `schemas` | ranged header reads |
| harvest meaning | `semantics` | TAB kits, `.CNV`/`.DEF`, SIGTAP, curation |
| families | `families` | |
| code tables | `reference` | `lake/reference/` |
| the lake | `build` (`normalize` is an alias) | |
| population | `population` | IBGE series |
| the shipped snapshot | `labelpack`, `scripts/build_resources.py` | writes `src/pegasus_data/resources/` |
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
