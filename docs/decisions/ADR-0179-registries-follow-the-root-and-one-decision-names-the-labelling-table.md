## ADR-0179: Registries follow the root in use, one decision names the labelling table, and the SIDRA registry folds with `textenc.fold`

**Date:** 2026-10-14. **Status:** active. **Amends:** ADR-0176 (where a registry is read), ADR-0082 (one ladder of evidence), ADR-0173 (what stays a plan input).

**Context.**
- **A registry was read from the default home (OQ 81).** `registry._cache_dir` and the cache stamp of `lookups._reference_version`
  took `load_settings().root`, while `build` wrote to the settings it was given. A consumer that passes `root=` (PegaSUS passes
  `C:/Users/Galaxy/pegasus_core_data` to every call) got no establishment names once ADR-0176 made a read stop downloading. Read-only
  on that root, default home empty, SIH-RD AC 2022-01 (3,977 rows): `CNES` rendered `2001586 (?)` and 12 warnings ("no reference
  table for 'CADGERBR'"); now `FUNDHACRE (2001586)`, no warning (8.8 s -> 28.2 s: the 692,004-row registry is read, which is the cost of a name).
- **Two choices of the labelling table (OQ 79).** `describe`, the ledger and `rollups_for` picked it from dictionary statistics
  (`most_granular_codelist`), the renderer from `label_bindings.decide`. On the maintainer catalog (dictionary, no profiles) `describe`
  named the table a query decodes with for 9 of 33 fields of SIM-DO, SIH-RD, SINAN-CHIK and -LEPT, a member of the rendered chain
  but not its lead for 4, and a table outside it for 20 (CAUSABAS `CID10_20` for `ICD10`, SEXO `SEXOC` for the curated table, PROC_REA
  `TB_SIGTAW` for `SIGTAP`, a SINAN form's `CLASSI_FIN` by dengue's `CLASSDENG`, `EVOLUCAO` by `EVOCANCE`, `CRITERIO` by `CRITAIDS`);
  on the shipped catalog (no dictionary rows) it named none.
- **A last folding (left by the merge fixer).** `sidra.registry.normalise_text` (lower case, accents) wrote the persisted `search`
  column and `survey` compared lower-case vocabularies with it, beside `textenc.fold`.

**Decision.**
- `Settings.registries_dir` (`<root>/registries`) is the one place; `registry.lookup(codelist, system, registries)` has no default,
  `read_reference_table(..., registries=)`, the lookups chain, `render_table`/`render_groups`/`codelist_levels`, the CNES<->CNPJ
  crosswalk (`settings=`), the name enrichment, `label_bindings` and `describe` pass the root in use's. A caller that names none finds
  no registry (the read goes on as for one not built), never the default home's. The timeline is served from the default home only
  (`serve` refuses another `--root`) and says so.
- `label_bindings.field_decision` is the catalog-level entry to the renderer's ladder (curated codes, the form's dictionary, curation,
  adjudication, stored or measured weighing; the renderer's exits for `label_from`, `label_via`, `code_system: none`). `describe`
  (`reference.table`/`tables`/`decided_by`/`observed_codes`, the labels of `top_values`, `rollups[].used_for_labels`) and the ledger's naming use it;
  `build_ledger` takes `lake_root` and `registries` for a decision that must be measured, and nothing is written by it. Read-only on
  `pegasus_core_data`: the rendered labels of the 33 fields are identical before and after (SIH-RD `CNES` apart: 49,547 null, now
  named), and `describe` names the rendered lead table for 32 of 33; the 33rd (CHIK `CLASSI_FIN`) differs because a catalog
  with no `value_frequencies` has no values to weigh the form's dictionary against, which `observed_codes: 0` says. No catalog held
  has `ledger` or `variable_profiles` rows, so the ledger's naming runs on the tests only.
- The SIDRA registry's `search` column is `textenc.fold` text, re-folded on open (`PRAGMA user_version` 1; idempotent,
  `fold(normalise_text(x)) == fold(x)` for all 9,336 stored values); `infer_kind`, `survey` and `search` compare folded vocabularies.
  `normalise_text` is gone. On a copy of the real registry: `rank` (N6, N3), `survey` and `infer_kind` (49,338 variables) identical;
  `search("pós-graduação")` finds 5 tables where it found 1 (the hyphen is folded like the stored text); `vintage_families` lists
  the same 31 families, its key text now upper case.

**Left as it was, and why.** `dictionary.most_granular_codelist` still picks the table that measures dictionary coverage
(`coverage_for_field`, a best-case figure) and the opt-in stored `_label` columns of `normalize/engine.py` (`--labels`, off, ignored by the
renderer). Their `labels`/`codelist` are inputs of `plan_fingerprint`: dropping or changing them changes the fingerprint of every
partition built (ADR-0173 keeps the 2,924 current), so they are not a dead path and stay until a rebuild is decided (OQ 79).

**Alternatives.** Derive the registries beside the lake: wrong when the lake is placed apart (`lake_root`). A process-wide "home in
use" set by the entry points: implicit state a thread does not inherit.

**What would reverse it.** A single place object (lake, registries, catalog) passed instead of its parts.
