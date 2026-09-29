## ADR-0001: Documentation follows the PHAROS model; the old documents are frozen

**Date:** 2026-09-28. **Status:** active.

**Context.** Development resumed after a month's pause (last commit
2026-09-03). The project's state was spread over fourteen Markdown files
(about 530 KB) with no index:
- `pegasus_data_ARCHITECTURE.md` (129 KB) and `docs/FINDINGS.md` (124 KB, a
  chronological lab notebook) were the most current.
- `RESUME.md`, `HANDOFF.md` and `DEFECTS.md` were closed logs that still read
  as current. `HANDOFF` and `RESUME` both named ARCH §21 as the only place for
  state, yet all work after 2026-08-27 was tracked only in FINDINGS §3r–3y
  and commit messages.
- Test counts disagreed across the documents: 601, 714, 837, 1025, 1131, 1184,
  1213 and 1227. The suite had 1,861.
- `FINDINGS` reused section numbers 3n–3q, so a cross-reference such as
  "§3q" was ambiguous.
- `README` and `CONTRIBUTING` were stale by weeks and described features by
  counts that no longer held.

The owner, returning, could not reconstruct what had been built. The same
owner's other project, `../pharos_project`, keeps its record in a form that
survived a much longer and faster development: an operating manual
(`CLAUDE.md` = `AGENTS.md`), a `STATUS.md` rewritten in place, one file per
decision and per measurement behind two indexes, an open-questions table, and
a checker that fails when the documents contradict themselves.

**Decision.**
- Adopt that model: `CLAUDE.md`/`AGENTS.md`, `STATUS.md`, `ARCHITECTURE.md`,
  `HOW_IT_WORKS.md`, `RUNBOOK.md`, `DECISIONS.md` + `docs/decisions/`,
  `EVALUATION.md` + `docs/evaluation/`, `OPEN_QUESTIONS.md`,
  `DATA_SOURCES.md`, `GLOSSARY.md`, and `scripts/check_docs.py`.
- Move every earlier planning, review, handoff and status document to
  `docs/history/`, unchanged. They are read for reasoning, never for
  instructions.
- Backfill the decisions already taken (ADR-0002 onwards) and split the
  August lab notebook into dated evaluation entries, with the text of each
  section unchanged, so that the history is indexed rather than rewritten.
- `tests/test_architecture_is_current.py`, which checked the old architecture
  document against the code, is replaced by rules 6 and 7 of
  `scripts/check_docs.py` (every module named in `ARCHITECTURE.md`, every
  public name documented).
- Code comments citing "§N" keep pointing at the frozen
  `docs/history/pegasus_data_ARCHITECTURE.md` (CLAUDE.md §9). They are
  rewritten when the code around them is.

**Alternatives.**
- *Refresh the existing documents in place.* This was rejected because the
  documents had no rule deciding which one was current. Refreshing them would
  have reproduced the drift.
- *One large architecture file.* This was rejected because the 129 KB file is
  the thing that went stale. Entries that are written once and indexed do not
  go stale; they are superseded, and the index says so.

**What would reverse it.** A period of development in which the indexes fall
behind the entries, or `check_docs.py` is bypassed, would show that the model
costs more than it returns here.
