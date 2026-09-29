## ADR-0009: Never guess a code's meaning; an unmapped code is undecoded, visibly

**Date:** 2026-08-18. **Status:** active.

**Context.** The project's stated problem P4 is honesty: every claim carries a
source and a confidence, and "a guess with no provenance is worse than a gap,
because a gap is visible" (`docs/history/pegasus_data_ARCHITECTURE.md` §0.3).
The prior compendium's `semantic_guess` column had labelled a CNES
establishment code `municipality_code_candidate` with nothing to say how far to
trust it (ARCH §14.6). The rule was in the brief and in the first commit
(`7b9488a`); it was recorded as the first prohibition in ARCH §18.

**Decision.**
- An unmapped code is `categorical_undecoded`, with a coverage penalty, and is
  a named, countable gap (ARCH §18; `docs/history/FINDINGS.md` §4).
- A label that cannot be produced is named in a warning, or raised as
  `LabelUnavailable` under `strict_labels=True` (ARCH §8).
- The open questions the module cannot answer are recorded in the catalog's
  `open_questions` and returned by `questions()`; the undecoded columns are
  ranked by row mass by `gaps()` (ARCH §14.11). An empty answer means none was
  recorded, not that nothing is uncertain.
- `translate()` requires `system` and never infers it, because `SEXO=3` is
  Feminino in SIHSUS and undefined in SINASC (ARCH §14.2).

**Alternatives.** Heuristic labels shown with a confidence. Rejected: a
plausible label is invisible downstream, whatever confidence it carries.

**What would reverse it.** Nothing. Individual gaps close when a source is
found (curation, ADR-0018), not by relaxing the rule.
