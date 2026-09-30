## ADR-0116: `info()` shows where each variable's description comes from

**Date:** 2026-09-30. **Status:** active.

**Context.**
- **Descriptions by rung** (`curation/variables`, 2026-09-30):

  | source | descriptions | meaning |
  |---|---|---|
  | `layout_doc` | 2,761 | a DATASUS record layout |
  | `def` | 899 | a TabWin `.DEF` file |
  | `web` | 200 | a published web document |
  | `inferred` | 504 | the project's inference where no document describes the field |
  | (none, or `manual`) | 263 | the project's own statement |

- **`info()` printed every description alike.** A reader could not tell a
  documented meaning from an inference.
- **An inference can be wrong.** SINAN `ORIGEM`'s inferred reading was
  contradicted by the data (EVALUATION 2026-09-30, omnisus facts verified). A
  wrong meaning that looks documented is the most expensive kind (CLAUDE.md
  §3.1). The user's challenge to the CIHA residence claim was about the same
  thing.

**Decision.**
- **Every described variable carries a `source:` line** under its
  description in `info()`, naming its rung.
- **An inferred description reads:** "INFERRED by the project: no document
  describes this field; unverified". Its reasoning is printed with it.
- **A project statement** (`manual`) prints its reasoning when there is one.
- **The JSON form** already carried `evidence.source` and `reasoning`; it is
  unchanged.

**Consequences.**
- **Nothing is re-labelled.** Status is shown; the 504 inferred descriptions
  are neither removed nor promoted.
- **Which of them are wrong is open** (OQ-64). Each is settled by a document
  or by a measurement against another field of the same record, as for
  `ORIGEM`.
