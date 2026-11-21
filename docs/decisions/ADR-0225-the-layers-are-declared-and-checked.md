## ADR-0225: the package's layers are declared and checked; the study builders are a subpackage

**Date:** 2026-11-21. **Status:** active. **Request:** the architecture review of 2026-11-21.

**Context.** 62 modules sat flat at the top of the package and more than half of the internal imports (1,154 of
2,131) were written inside functions, which read as a tangled graph. Measured against an order (`scripts/layers.py`),
it is not: placed module by module, one module-level import and 41 function-level ones went upward. The order existed;
it was written nowhere and nothing kept it. The function-level imports are mostly downward, written to keep a
command's start fast or by habit.

**Decision.**
1. The layers, lowest first, are declared in `scripts/layers.py` (`LAYERS`) and described in ARCHITECTURE section 1a:
   base, ingest, meaning, read, derive, describe, studies, entry. A module is placed by the longest prefix that names
   it (`persist.reference` is meaning, the rest of `persist/` ingest).
2. A module-level import goes to the same layer or a lower one. The script fails otherwise, and on an unplaced module;
   CI runs it. An upward import inside a function is a declared two-way relation, listed by `--lazy`.
3. Modules are not moved into one folder per layer: the names are imported by PegaSUS and cited in 221 decision
   records, and the order, not the folder, is what was missing.
4. The seven builders of modelled products are `studies/` (`population_account`, `population_tensor`,
   `population_backcast`, `population_forecast`, `modelled_race`, `completeness`, `sus_dependent`): nothing below
   imports them; `products.yml` names their build functions.
5. What `intake.yml` declares is read in the meaning layer (`semantics/intake_declarations.py`); `intake.py` lands the
   records.
6. A function-level import is hoisted to module level where that changes nothing at import time (the target is
   already imported when the importer is, no cycle, no name clash). The others stay: they keep a start fast, guard an
   optional dependency, or are one of the upward relations.

**Left as declared two-way relations.** `semantics.event_types` offers `read_events` and `count_events`, which run the
query engine: PegaSUS imports them from that module, so they stay (6 + 2 imports). `intake` builds fields on request
(5). The rest are single imports (the profiler deferring to declared roles, the registry's build stage, the
compendium listing the commands).
