## ADR-0246: One home per job is declared and checked

**Date:** 2026-11-28. **Status:** active. **Request:** the author, 2026-11-28: every session "forgets architecture,
implements parallel and redundant implementations"; abnc2027_neuro `papers/TRIAL_t06b.md`, W10.

**Context.** "Replace, never build beside" (CLAUDE.md §4) was a sentence and a table (ARCHITECTURE §5) that a
session had to remember to read. It failed by forgetting: f30096aa added a fifth archive reader, a sixth spreadsheet
reader and a hand list beside IBGE's own names in one change, by a session that had the rule in its instructions.
The layers already showed what works: `scripts/layers.py` declares the order and fails on a breach (ADR-0225), and
no upward import has been added since.

**Decision.** `scripts/homes.py` declares, for each recurring job that is recognisable as a call (open a DuckDB
connection, open an archive, read a spreadsheet, make an HTTP request, open an FTP connection, fold a name, read a
curation YAML, ask the machine for its free memory, put a finished file in place of another), its **home** and its
**debts** (the modules that still do it beside the home). It fails on a module that does the job and is neither, and
on a debt that no longer does it (so the list is only what is owed). `python scripts/homes.py WORD` prints the home
of a job before one writes. A debt is never added to pass the check. It is run with `layers.py`, `check_docs.py` and
ruff before a commit (RUNBOOK).

**Consequences.** Measured at the first run: 9 jobs, 32 second implementations owed (archives 13, spreadsheets 7,
free-memory probes 5, file replacements 5, one HTTP client, one text fold), against the four rows ARCHITECTURE §5
had named for them: the register was a fraction of the debt. A job that is not a call pattern (how a written
municipality name is placed, how a field is declared) is outside the check and stays with ARCHITECTURE §5 and §6.
The six modules no layer placed (`_bounded`, `_holdings`, `_manual`, `concurrency`, `formats`, `raw_text`) are placed,
and `layers.py` passes again.
