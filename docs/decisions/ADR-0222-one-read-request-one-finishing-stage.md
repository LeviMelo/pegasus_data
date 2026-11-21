## ADR-0222: a read is one request, two sources and one finishing stage

**Date:** 2026-11-21. **Status:** active. **Extends** ADR-0073 (`query` is the one door; `load` and `fetch` are
engines). **Request:** the architecture review of 2026-11-21 (author: assess the architecture; then "it's yours now").

**Context.** `query()` called `load()` for the lake's years and `fetch()` for the fetched ones. Each of the two
normalised the row filter, prepared the condition, derived which columns a projection must bring and which to drop
again, rendered per (family, vintage) and trimmed its result; `query` steered them with private switches
(`_preserve_internal`, `_leave_out`, `_condition_state`, `_record_key`). The two derivations had drifted before
(2026-10-03: a `select=` labelled a column for fetched years and not for lake years) and differed still: under a
projection `load` dropped a derived column nobody asked for and `fetch` returned it.

**Decision.**
1. What a read asks is one object, `ReadRequest` (`_query_engine/request.py`): the columns, the row filters, the
   prepared condition, the rendering. It derives by one rule what each source must bring (`lake_columns`,
   `lake_optional`, `source_columns`) and which helper columns go after rendering (`helpers`).
2. The sources differ only in how they find and open files: `api.read_lake` and `retrieve.read_source`. Both return the
   engine's form (the engine's columns and each record's answer to the condition still on the rows).
3. One stage finishes either source: `finish` renders the groups under the label policies and drops the helpers.
4. `load` and `fetch` are a source plus `public_form` (the condition settled, the engine's columns dropped). They take
   no private switch; `fetch`'s `_only_paths` is `only_paths`.
5. Under a projection neither source returns a derived column that was not asked for (`load`'s rule).

**Evidence** (evaluation 2026-11-21-architecture-review). `scripts/read_equivalence.py`: thirty real reads (the lake,
published files, a hybrid, rows, conditions, provenance, dimensions, through-key columns, four refusals) recorded on
97f9b6d and after: every table equal, every report equal but the cache counters; one deliberate difference, item 5
(`fetch(columns=[..., "MUNIC_RES"])` no longer returns `MUNIC_RES_municipio`).

**Consequences.** A rule about what a read brings is written once. `scan()` and `export()` keep their own parameters
(they stream; not folded in). The script stays as the gate of any change to the read path (RUNBOOK).
