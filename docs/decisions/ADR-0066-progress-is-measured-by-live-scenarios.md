## ADR-0066: Progress is measured by live scenarios; no new unit tests

**Date:** 2026-09-28. **Status:** active.

**Context.**
- The suite had 1,861 passing tests on 2026-09-28. The primary interface
  still returned codes without meaning on a fresh install, `info()` crashed
  there, and SIA's largest states were unselectable (evaluation 2026-09-28).
  Each of those was found in the first hour of using the package as a new
  user would.
- The tests had been written in the same sessions as the code they checked,
  against fixtures the same author built. The user's rule, stated for PHAROS
  and for this project (2026-09-28): a test written in the session that makes
  a change passes by construction, and is redundant.

**Decision.**
- Development is driven by `scripts/live.py`: named scenarios a person would
  run, against the real FTP server, on a fresh data home outside the
  repository. Each records seconds, rows, per-column label coverage and the
  warnings seen, under `data/probes/live/<run>/`.
- A defect is fixed and its scenario re-run. The output is read, not only the
  exit code.
- No new unit tests. The existing suite is a regression net, run before each
  commit and kept green. Where a deliberate behaviour change contradicts an
  existing test, that test is updated to the new decision, which is named in
  it.
- A run that informs a decision is an entry in `EVALUATION.md`.

**What would reverse it.** A class of regression the live scenarios cannot
reach, found late and more than once.
