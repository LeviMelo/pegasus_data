# CLAUDE.md — pegasus_data

**`AGENTS.md` in this directory is a byte-for-byte copy of this file.**
Different agent runtimes read one name or the other, so a change to either
must be written to both in the same commit; `scripts/check_docs.py` fails
when they diverge.

How to work on this repository. Architecture, evidence and history live in the
documents listed in §9; nothing is duplicated here.

Written 2026-09-28, when development resumed after a month's pause and the
documentation was rebuilt on PHAROS's model (ADR-0001). Before that, state was
spread over fourteen overlapping Markdown files with no index; they are frozen
under `docs/history/`. If you are about to add a rule here, ask whether it
belongs in `DECISIONS.md` as a decision with its evidence instead.

---

# 1. What pegasus_data is for

Turn the DATASUS public FTP tree (about 207,000 files, twenty information
systems, 1992 to now) into data a person can use **with its meaning attached**:

```text
ftp.datasus.gov.br ─► crawl ─► catalog (what exists, its schema, its lineage)
                   ─► fetch ─► decode (DBC/DBF/…) ─► normalise ─► a table
                                                            └─► the lake (Parquet)
.CNV/.DEF/PDF/curation ─► the semantic layer (what each column and code means,
                          from which source, valid for which years)
the table + the semantic layer ─► labels, dimensions, aggregates, the HTTP API
```

The consumer that matters is **a person analysing Brazilian health data**:
in Python (`query`, `info`, `explore`), on the command line (`pegasus-data`),
or through `serve/`, which the sibling frontend `../pegasus_view` reads.

---

# 2. Run it

The runtime is the shared `pegasus` conda environment. Use its interpreter
explicitly: `python` on PATH is a bare 3.13 without the package, and conda
**base** imports a *different* project (`../PegaSUS`, also named
`pegasus_data`).

```bash
PY=C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe

PYTHONUTF8=1 $PY -m pytest -q -m "not network"   # old suite, ~5 min: rarely, in the background
$PY -m ruff check src scripts tests
$PY scripts/check_docs.py
$PY scripts/live.py --list                        # the live scenarios (§5)
```

- **Encoding.** Set `PYTHONUTF8=1`: labels are Portuguese.
- **Data homes.** The repo's own `pegasus_data_home/` (3.5 GB, gitignored) is
  adopted automatically by any command run inside the repo. Live checks run
  against a **fresh** home instead (`scripts/live.py` does this), because the
  local one hides every fresh-install defect.
- **Long runs detach.** The Bash tool caps background work at ten minutes;
  start longer builds with PowerShell `Start-Process`, logging beside them.

---

# 3. What binds

1. **Correct meaning.** A wrong label is worse than no label: it is invisible
   downstream. Every other budget yields to this one.
2. **The FTP server.** One public server, one connection's bandwidth, and it
   reorganises without notice. Bytes on the wire are the scarce resource; a
   header read (ranged) is preferred to a decode whenever it answers the
   question.
3. **Wall clock for a person.** A first `query()` for a state-year should take
   seconds to a minute, not an hour. Correct but unusably slow is not finished.
4. **Disk.** The full tree is 991 GiB as listed on the server (`explore()`,
   2026-09-28; the "183 GiB" in older documents was wrong); this machine has
   ~177 GB free. Nothing downloads the whole tree implicitly.

---

# 4. Autonomy

- **Decide.** Architectural and semantic calls are the agent's. Adjudicate,
  write the decision down with its evidence (an ADR), and proceed. Do not hand
  the user a menu.
- **Never act outward as the user.** Pushing to GitHub, publishing to PyPI or
  contacting anyone needs explicit authorisation, each time.
- **Replace, never build beside.** Before adding a mechanism, find the one that
  already does the job (`ARCHITECTURE.md`). A second mechanism for the same job
  is a defect; this project already has several (ARCHITECTURE §5).
- **Carry the whole request.** Each instruction is done or reported as not
  done, with the reason.
- **Keep `../pegasus_view` working.** Its contract is `serve/` (`/health`,
  `/datasets`, `/datasets/{a}/capabilities`, `/population`, `/geo/membership`,
  `/records`). A change there is made in both repositories, or not at all.

---

# 5. Measure on the live system

Development is driven by **live use**: `scripts/live.py` runs scenarios a real
user would run, against the real FTP server, on a fresh data home, and records
what happened (seconds, bytes, rows, labels, errors) as JSON under
`data/probes/live/`. A defect found there is fixed, and the scenario that found
it is run again.

- **No new unit tests, and no time spent on the old ones** (user,
  2026-09-28). A test written in the session that makes the change passes by
  construction. Verify a change by running the live scenario it affects and
  reading its output. The old suite takes ~5 minutes: never wait on it before
  a commit. Run it rarely, in the background, and when it contradicts a
  deliberate decision, delete the test rather than port it.
- **Read the output, not the exit code.** Open the table; look at the labels;
  count the rows against an independent figure (TabNet, the file's own row
  count). Earlier sessions declared bugs fixed without reading the output and
  were wrong (docs/history/HANDOFF.md §6).
- **Check a fact before stating it.** A count, a date, what a document says.

---

# 6. Semantic non-negotiables

These are cheap to violate and expensive to discover. Rationale in
`ARCHITECTURE.md` (invariants) and the ADRs.

```text
Never guess a code's meaning; an unmapped code is undecoded, visibly.
Missing is not zero; a file that would not open is a recorded gap, not an absence.
A missing column raises; an empty result must never look legitimate.
Labels are joined by validity window, never frozen into the lake.
Widths are matched exactly; never pad or truncate a code to make a join succeed.
A system's own codelist is keyed by its system; a standard (ICD-10) is one canonical table.
Sentinels are per field; there is no global sentinel rule.
Never discard the raw value when writing a label.
Never resolve a source conflict silently; record both claims.
Period and geography select DATASUS publications; they never filter record variables.
Never recompute what the source publishes officially (epidemiological week).
Personal identifiers pass through unmodified, and stay flagged.
Stored aggregates are sums and counts, never finished means.
```

---

# 7. Code, tests and documentation

- **Replace, never add beside.** When a method misses the goal, redesign it,
  remove what it replaces, and check for dead code (`scripts/codehealth.py`).
  New capability goes in `src/` behind the API and a CLI command, not in
  `scripts/` or `tools/`.
- **Documentation ships with the change, in the same commit.**
  - A decision is a new `docs/decisions/ADR-NNNN-<slug>.md` and a row in
    `DECISIONS.md`.
  - A measurement or live run is a new `docs/evaluation/YYYY-MM-DD-<slug>.md`
    and a row in `EVALUATION.md`, including one that changed nothing.
  - `OPEN_QUESTIONS.md` holds unresolved questions only.
  - `ARCHITECTURE.md` changes when a module boundary or a persistent object
    does; `STATUS.md` when the state of the work does; `RUNBOOK.md` for new
    commands; `DATA_SOURCES.md` for a new fact about DATASUS.
  - `scripts/check_docs.py` stays green.
- **An evaluation entry names** the scenario or script, its artifact under
  `data/probes/`, what was counted and why it is the thing that matters, and
  the regime (commit, data home, date).
- **When a documented number is found wrong,** correct it where it was written
  and say so there.
- **Commits.** Work on a branch; the user merges and pushes.

---

# 8. The repository

- `src/pegasus_data/` — the package. `curation/` (YAML) and `resources/`
  (the shipped label pack) are data, reviewed like code.
- `scripts/` — maintainer and live-check scripts. `tools/` — presentation
  exporters (being folded into the package; ARCHITECTURE §5).
- Gitignored and local: `pegasus_data_home/` (catalog, blob cache, lake),
  `sources/` (2.5 GB of harvested DATASUS documentation), `data/probes/`.

---

# 9. Where to look

| Need | Read |
|---|---|
| how the system runs, end to end | `HOW_IT_WORKS.md` |
| current state and what is next | `STATUS.md` |
| the plan of the branch in progress | `docs/plans/` (`linkage.md`: record linkage; `linkage-theory.md`: the proposed unified theory) |
| module boundaries, what overlaps, and the invariants | `ARCHITECTURE.md` |
| accepted decisions and their evidence | `DECISIONS.md` (an index; one file per ADR under `docs/decisions/`) |
| measurements and live runs | `EVALUATION.md` (an index; one file per entry under `docs/evaluation/`) |
| open questions | `OPEN_QUESTIONS.md` |
| facts about DATASUS, IBGE and the other sources | `DATA_SOURCES.md` |
| operating commands | `RUNBOOK.md` |
| terminology | `GLOSSARY.md` |
| the user-facing manual | `README.md` |

Read an index, then the entries a task needs; never a whole folder.
`DATA_SOURCES.md` beats assumptions about DATASUS. `STATUS.md` beats old
plans. `docs/history/` holds the superseded architecture document, briefs,
reviews, handoffs and the 2026-08 lab notebook (`FINDINGS.md`): frozen, read
for reasoning, never for instructions. Code comments that cite "§N" or "D-N"
refer to `docs/history/pegasus_data_ARCHITECTURE.md` unless they name another
file.
