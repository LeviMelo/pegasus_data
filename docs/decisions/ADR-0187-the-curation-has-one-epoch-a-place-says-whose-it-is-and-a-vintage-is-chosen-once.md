# ADR-0187: the curation has one epoch, a place says whose it is, a vintage is chosen once

**Date:** 2026-10-14. **Status:** accepted. Amends ADR-0166 (it declined the attribute added here) and ADR-0165 (the one
reader also serves records).

**Context.** The semantics review's structural section named conventions kept in several places that had drifted. The fix round
had done three (one authority ranking, `describe` and the ledger deciding the labelling table with the renderer, the curation
load as one transaction). Left: (1) sixteen loaders of curation each kept a memo of their own: `maxsize=1` with no key (a process
that changed its curation directory kept serving the old one), a root, a text, or the `stat` of 190 files on each call
(`Ontology.load`); `declared_fields`, `captures` and `treatments` parsed on every call. (2) Whose place a place column is
(the person's, the event's or only the record's) was the model plus a property's name, read by consumers' string matching; the
loader accepted a registry office typed `where`. (3) The warehouse chose a reference table's validity windows with its own
Arrow code beside `labelpack.select_windows`, which the pack followed. (4) PegaSUS re-implemented `read_events` to read an
event type's records (duplicate flag, retry without it, status, weights).

**Decision.**
- **One epoch.** `semantics/epoch.py`: `curation_epoch()` (the directory in use and the digest of its content, once per
  process and directory), `@curated` (a loader built once per epoch; the value is shared and never copied; `rooted=True` when
  its first argument is the directory) and `forget_curation()`. It replaces the memos of the roles, grids, event types and
  declarations, inline and harvested codelists, dataset semantics, relations, the ontology, the declared fields, captures and
  treatments, the care flows, the ledger's unit table and linkage's roles and links. A loader that fills a catalog
  (`load_curation`, `seed_relations`) reads the files as they are, not the epoch's copy. Editing the YAML inside a running
  process is seen after `forget_curation()` only (the ontology used to notice an edit by file times; nothing else did).
- **A place says whose it is.** `place_of: subject | event | record`, required of every `kind: place` column (1,067 columns in
  166 role files) and validated in `column_roles._column`: a stratum is the subject's, a `where` is the event's (so a registry
  office, a managing authority or a laboratory the record names cannot be one), and only a place has it; `roles()` carries it.
  *Subject*: where the person lives, was born or works. *Event*: where the event the role's entity names, its care, notification,
  infection or exposure happened (travel, risk, accident, transfusion, prenatal, delivery and transfer places are event places
  and stay marks: no model changes). *Record*: where the record was made, kept or managed (registry office, death-verification
  service, manager, reporting state, a laboratory, provider or partner service it names). The notifying unit stays an event's
  place, as ADR-0166 said: the form names it the unit that sees and notifies the case, and typing it a record's place would drop
  the 55 SINAN flows. `proximity.flows()` is unchanged in output.
- **One window rule.** The warehouse applies `labelpack.select_windows` (a covering window; else the open-ended one, recorded;
  else with no period the newest, recorded; else none, recorded unresolved), as the pack does. The newest-window answer of a
  table with no open-ended window was silent and is now recorded.
- **One reader of events.** `read_events(consolidate=False, prepare=)` reads an event type's records: duplicates and status, not
  consolidation (the key is not read); `prepare` adds a column before the rule (the record identity). PegaSUS's `_records` is
  that call; its copy of the flag, retry, status and weight code can go.

**Consequences.**
- 122 real calls give equal tables before and after; 5,736 warehouse reads give identical rows and 64 added notes
  (evaluation 2026-10-14-semantics-structure). `Ontology.load` and `declared_fields` cost 6 µs warm (1.7 and 1.8 ms); the
  first curated read of a process adds 83 ms once.
- `events_of`, `count_events`, `event_weights`, `grid_events` and `_integers` are byte-identical, so PegaSUS's stored counts keep
  their keys; only `read_events` changed.
- For PegaSUS: `declared_flows`, `facility_column` and the outbreak's place can read `place_of` in place of `model` plus the
  property's name (the `municipality` property stays the level selector).
- Not done: the normaliser's own labelling path and `coverage_for_field` still use `most_granular_codelist` (hashed by
  `plan_fingerprint`, ADR-0173; OQ 79); `_aggregate.py` reads events through `events_of` with its own projection.
