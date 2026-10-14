# ADR-0174: a projection reads what its labels need, a row filter runs before rendering, a lake from a superseded edition is incomplete

**Date:** 2026-10-14. **Status:** accepted. **Amends:** ADR-0164 (undated records), ADR-0172 (year 0), ADR-0090 and ADR-0094 (the rule moved).

**Context.** The query review's second round found one projection rule written twice and kept right only on the fetch path.
`select=` on the lake dropped the columns a label is made from (a composite key's parts, ADR-0088; the sibling or establishment a
label reads, ADR-0090/0094) while `fetch()` kept them: SIH-RD AC 2024 `columns=["COD_IDADE"]` (keyed by `COD_IDADE + IDADE`) came
back with 57,272 of 57,272 labels null from the lake and labelled from a fetch, and the renderer's fallback matched the bare column
against a different key of the same table. `rows=` on the fetch path ran after the whole year was rendered (a label render mode
would have tested the prefix on label text) and each path spelled the prefix test its own way (`extract` stripped dots and upper-cased,
the scan did not). A partition built from an older edition of a publication counted as the publication (`(family, logical id,
member)` is shared by both editions), so corrected data were not served until a rebuild. `_is_multi_valued` read the default
home's catalog, swallowed every error and cached the answer, so a roll-up over `CODANOMAL` could double-count.

**Decision.**
- **One projection rule.** `semantics.curation.required_columns(docs, columns)` is what a read brings for the columns asked: the
  derived columns' inputs, `depends_on`/`modifies`, a key's parts, `label_from`, `label_via` columns, what modifies a column. `load()`
  and `fetch()` both read it, render, and drop what was not asked (`view.drop_helper_columns`, with the derived columns the extra
  reads made possible). A key with a missing part leaves the column undecoded and says so; `@UF` parts read the lake's `uf`.
- **A row filter runs on the decoded codes, before anything is rendered, on every path.** `fetch(rows=)` filters the decoded year;
  `api.normalise_prefix` and `api.prefix_match` are the one prefix test of the scan, the fetched year and the extracts (dots
  stripped, upper case).
- **Coverage is by edition.** A source file proves its publication built unless it is another edition of the selected one
  (`representations.other_edition`: the same kind of file at another path and another size); another format and a mirror still prove it.
- **The multi-valued flag is read from the catalog of the settings in use and an unreadable catalog raises.**
- **A state build whose files are published by another geography than its cells' key says so** (`uf_basis_note`: SIH-RD, files by
  hospital state and cells by residence). `uf` selects publications, never records (ADR-0043), so the build is not filtered.
- **Undated intake records (year 0) are a listed lake partition**, never a publication: `load()` of every year returns them,
  a named year does not, and rendering never drops them (`render_groups` keeps them against no vintage).
- A reader waits up to a second for a partition file that a rebuild's two renames have not yet put back, and only then calls the lake
  partial (`PartialLakeError`); an `OSError` other than not-found is no longer read as absent.

**Evidence.** `docs/evaluation/2026-10-14-query-review-round-two.md`.

**Not decided here.** `describe`, the ledger and the normaliser still choose "the table that labels a field" by dictionary statistics
(`most_granular_codelist`) while the renderer uses `label_bindings.decide`; one choice needs the ledger to have the lake handle and
`normalize/engine.py` to stop computing labels it discards (OPEN_QUESTIONS).
