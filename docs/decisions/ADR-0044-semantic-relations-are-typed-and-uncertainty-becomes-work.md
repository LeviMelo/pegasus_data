## ADR-0044: Semantic relations are typed, and unresolved uncertainty becomes an adjudication item

**Date:** 2026-08-23. **Status:** active.

**Context.** One field takes part in several true relations. `MUNIC_RES` has
an identity label, rolls up to a health region, and has an attribute saying
whether the municipality is a capital. Treating every `.DEF` transformation as
a competing label is how a roll-up came to replace a municipality's name
(`docs/history/FINDINGS.md` §3k;
`docs/history/PEGASUS_NEXT_ARCHITECTURE_BRIEF.md` §7–§8). Built in `efbc7c1`;
made temporal and authority-aware in `64cb3b5` and `61199c7` (2026-08-23).

**Decision.**
- `semantics/relations.py` models `label_of`, `rollup_to`, `attribute_of` and
  `crosswalk_to`, seeded from `curation/joins.yml` and persisted in
  `semantic_relations` (`docs/history/pegasus_data_ARCHITECTURE.md` §9.3).
- Only an effective `label_of` becomes an automatic `*_label` beside a raw
  code. Roll-ups and attributes are produced only by an explicit
  `dimensions=` request.
- Each row is a temporal assertion with a stable `relation_id` that includes
  its validity window and authority. Overlaps within one authority and slot are
  rejected. Local adjudication outranks shipped curation, which outranks the
  legacy bridge (FINDINGS §3o–§3p, first).
- An overlarge unresolved candidate set creates a stable `adjudication_items`
  key. `pegasus-data adjudicate show|export|apply` packages its evidence and
  records a reviewed decision in one committed transaction, visible to new
  connections at once (FINDINGS §3n, first).
- Re-seeding replaces the curated snapshot transactionally and never mutates
  local assertions.

**Alternatives.** A truncated ranking, or a silent guess. Rejected: both let
cost decide meaning (ADR-0041).

**What would reverse it.** Nothing foreseen.
