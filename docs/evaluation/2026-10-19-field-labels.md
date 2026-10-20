# Short names for the 108 declared context fields (2026-10-19)

**Check.** PegaSUS's window lists the fields a study can relate its rates to and could show only an identifier or the
`what` sentence. Every field of `declared_fields()` (69 in `curation/fields.yml`, 39 from the sources of
`curation/intake.yml`, seven of them the `<name>_assessed` populations) now has a `label`: sentence case, 2 to 7 words
(mean 4.6), written from the field's own `what`, `unit` and keys. Fields that differ say how: SUS or all, jobs or
persons, below or above a limit, the outcome or the population assessed.

**Result.** `unlabelled_fields()` returns none and `shared_labels()` none (labels compared folded, as names are
matched), on the commit of this branch with the shipped curation, no data read. The existing curation tests pass (161).

**Where.** `fields.yml` takes `label` as any key (`declared_fields` returns each entry whole); `intake.yml` fields take it
through `intake_fields`, and an outcome field takes `population_label` for the `<name>_assessed` field it implies, which
does not inherit its outcome's label (`_with_populations`). A field added without a label shows in `unlabelled_fields()`.

**Consequence.** `declared_fields()` changed for every field, so the gateway's key of a stored context reading
(`_field_key`, a hash of the declaration) changes: readings are recomputed once from the lake files.
