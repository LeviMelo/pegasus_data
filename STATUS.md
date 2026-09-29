# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-09-28, late evening.

## Where the project is

Development resumed on 2026-09-28 after a pause since 2026-09-03, on branch
`redesign`. The first day of live use (ADR-0061 to ADR-0082) changed the
project in three ways:
- it made the read path deliver meaning;
- it collapsed the four data doors into one, `query()`;
- it replaced three sampling assumptions with measurements: one header per
  stratum, one codelist per column name, and one layout per publication.

## Done (live-verified)

- **One door.** `query()` returns the raw code and its label as a companion
  (ADR-0063, ADR-0073). It states its download in `plan()` and refuses more
  than 1 GiB of new files by default (ADR-0076).
- **Labels.**
  - One binding decision per (system, family, field), compiled and shipped in
    the seed (ADR-0072). It is decided by one evidence ladder shared by query
    and compile (ADR-0082):
    1. inline curated `codes:`;
    2. the form's own data dictionary;
    3. a curated codelist;
    4. adjudication;
    5. measured weighing.
  - 1,264 SINAN code tables are harvested from the 41 official data dictionary
    PDFs (ADR-0079, ADR-0080). Codes belong to their form: meningitis
    `CLASSI_FIN 2` is "descartado", no longer another form's "Só Exposição".
  - Curation review: inferred descriptions went from 1,799 to 505, all
    document-backed, with the sources cited per entry.
- **Age.** `IDADE_anos` in fractional years for SIH, SIM and SINAN (ADR-0070).
- **Coverage.**
  - SIA APAC 2001-2007: 1,457 multi-table LHA archives, now nine datasets
    (SIA.AC/CO/EX/OP/PC/PF/PQ/UD/UO), including dBase 7 (ADR-0077).
  - Parquet and small archives are censused without full downloads.
- **Republications.**
  - A file that gained columns is read, with a warning.
  - A republished stratum is re-censused (ADR-0078).
- **Identity.**
  - A publication is read once across trees and layouts: normalized-date
    identity, and the majority layout wins (ADR-0081). SINASC-DNR Roraima 1995
    returns 7,020 births, not 14,040.

## In progress

- **Per-file header census** (ADR-0081): all 198,916 DBC/DBF headers, about
  0.5 GB and 3 h on 8 connections, incremental afterwards. The run is
  `pegasus-data schemas --all-files`, log `data/logs/file-census.log`. When it
  finishes:
  1. `families`;
  2. `bindings` (recompile, since the ladder changed);
  3. `scripts/build_resources.py` (seed);
  4. the full live sweep.

## Open fronts

- **Harvest the other systems' layout documents** (SIM, SINASC, SIH, CNES,
  SIA) the way SINAN's dictionaries are harvested. There are ten SINAN
  dictionary PDFs with no series mapping yet.
- **Undescribed exports.**
  - The 12 DuckDB databases (`Dados_Abertos/APAC_SIA/*.duck.zip`,
    `SIHSUS/base_aih1.duck`). A ranged-read schema probe of the 12 GB
    `.duck` works over FTP `REST`; it still needs to be finished and wired in.
  - The header-less SISCAN 2015 CSV.
- **Harness.** The live sweep now budgets on `plan()` and counts
  `PublishedEmpty` as a result; its SIA.AC and TABDOS.APP failures still need
  a rerun after the census.
- **Carried from before:**
  - distinct-count and known-values-only measures, age-standardised rates;
  - the health macroregion and geography vintage;
  - moving stock time reducers from `tools/` into `measures.py`;
  - mypy (157 findings);
  - splitting the large modules (`cli`, `retrieve`, `view`).

## Waiting on the user

- **Publishing.** The branch `redesign` is not pushed (CLAUDE.md §4). The
  compiled DBC engine should ship in platform wheels (ADR-0074); without
  them, a user with no C compiler decodes 20× slower.

## Tests and checks

- `scripts/live.py --all --fresh`: the live scenarios, which measure progress.
- `ruff check src scripts tests` and `scripts/check_docs.py`.
- `pytest -q -m "not network"` is a regression net that does not grow
  (CLAUDE.md §5); tests contradicting a decision are deleted.
