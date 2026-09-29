# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-09-28, evening.

## Where the project is

Development resumed on 2026-09-28 after a pause since 2026-09-03, on branch
`redesign`. Before the pause, 232 commits in 17 days had built:
- an ingest engine (crawl → catalog → download → decode → normalise → lake);
- a semantic layer (codelists harvested from `.CNV`/`.DEF`, curation for
  4,534 variables, a 30 MB shipped label pack);
- a query planner (`query`/`plan`);
- an aggregate layer (62 recipes, a measure algebra, `serve/` for
  `../pegasus_view`).

The code was written mostly by an earlier, less capable model and has **never
been run as a new user would run it**. The first live runs on a fresh data home
(2026-09-28) found the primary interface broken in the way that matters most:
`query()` returns codes without their meaning.

## Milestone M1: the read path delivers meaning

The ingest half works. The read half has four doors (`query`, `fetch`, `load`,
`scan`) that disagree about labels, and the metadata doors (`info`, `search`)
do not work on a fresh install. M1 makes the documented path work, measured
by `scripts/live.py`.

| # | Defect found live | State |
|---|---|---|
| 1 | `query()` stripped every label lacking a declared `label_of` relation (SIH 2 of 39 labelled) | **fixed** (ADR-0061): SIH 39, SIM 52, CNES 113 |
| 2 | every 3-character CID-10 code unlabelled (13% of SIH admissions) | **fixed** (ADR-0062) |
| 3 | the default profile replaced internal codes in place, discarding them | **fixed** (ADR-0063) |
| 4 | `info()` and `search()` fail on a fresh home | **fixed**: `info()` by the seed catalog (ADR-0067); `search()` reads the catalog and label pack (ADR-0069) |
| 5 | ~~`explore()` totals wrong~~: they are right (991 GiB); the old docs were wrong | not a defect |
| 6 | 20–60 warnings a call | **fixed**: one summary warning; the full list on the report |
| 7 | leaks: decoder workers outlived the interpreter, pipes and spools left open | **fixed** |
| 8 | a warm `query()` took 15 s against `fetch()`'s 4 s | **fixed** by #1: 2.7 s |
| 9 | SIH `SEXO` unlabelled; no age in years in any `query()` | **fixed**: SIH's own SEXO table; `IDADE_anos` in fractional years for SIH, SIM, SINAN from unit tables measured against the records' dates (ADR-0070) |
| 10 | SIA's split files (984, SP/RJ/MG) and SISCAN's annual files had no UF or date | **fixed** (ADR-0065) |
| 11 | SIH-RD 2008/10/12/14 had no family: the census sampled the `.xml` republication | **fixed**: one sample selection, header-readable first |
| 12 | a first SIA request spent 5.6 min censusing | **fixed** (ADR-0067): 339 s → 35.5 s on a fresh home |
| 13 | `CNES`, `PROC_REA`, `CGC_HOSP` refused as having more than 12 bound codelists | open: M2 |
| 14 | SIH-RD 2014–2016 refused: two editions of each publication (`MHJ_14_16/`, `200801_/Dados/`) | **fixed** (ADR-0068): the newest edition is read |
| 15 | SINAN-TUBE 2022 refused: `.csv.zip`/`.json.zip`/`.xml.zip` read as three editions of `zip`, and the stored conflict kept gating | **fixed** (ADR-0071) |
| 16 | SINAN plain-year ages (0.8% of dengue) decoded as days; SIM's unit table wrong in its own layout document | **fixed** (ADR-0070) |

All thirteen live scenarios pass on a fresh seeded home (run `m1-seed-age-1`).

## After M1

- **M2: compiled label bindings.** The renderer weighs up to twelve bound
  codelists against each file's values at read time, so two files of one
  dataset can be labelled from different tables, and every read pays for the
  weighing. Compile one binding per (system, dataset, field, vintage) ahead of
  time, from curation and measured coverage, and ship it. This is the
  `label_of` declaration the query layer wanted.
- **M3: one read path, one door per question.** `fetch`, `load` and `scan`
  become thin forms of `query`. There is one dataset identifier, a `query` CLI
  command, and one exporter of the semantic layer (today there are five:
  ARCHITECTURE §5). `tools/` moves into the package.
- **M4: every system live.** A green scenario per information system,
  aggregates and `serve/` included.

## Waiting on the user

- **Publishing.** The branch `redesign` is not pushed (CLAUDE.md §4). Two
  things need a decision: fix CI's trigger (it fires on `main`; the branch is
  `master`), and ship the DBC engine compiled in platform wheels (ADR-0074).
  Without compiled wheels, a user with no C compiler decodes 20× slower.

## Tests and checks

- `pytest -q -m "not network"` in the `pegasus` env (1,861 passed, 21 skipped,
  2026-09-28; ~9 min). It is a regression net and does not grow (CLAUDE.md §5).
- `ruff check src scripts tests`.
- `scripts/check_docs.py`.
- `scripts/live.py --all --fresh`: the live scenarios, the measure of progress.
