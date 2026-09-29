## ADR-0018: Curation in version-controlled YAML is the manual authority rung

**Date:** 2026-08-19. **Status:** active.

**Context.** Three times the design created a slot for human judgement and
left no way to write into it: `SOURCE_AUTHORITY['manual']` with nothing
emitting a manual entry; `layout_doc` declared authoritative before anything
produced one; and a prefix contradiction only a person could settle
(`docs/history/pegasus_data_ARCHITECTURE.md` §9). Added in `44380a1`
(2026-08-19: "the door that was missing").

**Decision.**
- `src/pegasus_data/curation/*.yml` holds human assertions: what each system
  is, what one row of each dataset is, and per-variable meaning, codelists and
  dependencies. YAML under version control gives each assertion an author, a
  date and a diff.
- A curated claim outranks every extracted source: `manual` is authority 0
  (ADR-0008).
- `curate --accept` settles an open question with a required `--note`.
- `vintage_note` records when a classification changed and how the right one
  is chosen for a row.
- Curation ships in the package. That was itself a fix: the path had resolved
  to the repository root, so every pip install had an empty manual rung
  (ARCH §14a).
- A corrected meaning reaches an existing catalog. The catalog stores a
  content fingerprint of `curation/` in `curation_state` and reloads when it
  changes (ARCH §9.1). Content, not mtime, because a wheel's timestamps record
  when it was unpacked.

**Alternatives.** Manual entries written directly into the catalog. Rejected:
no author, no diff, and lost on rebuild.

**What would reverse it.** Nothing foreseen. A curated `codelist:` bypasses
measurement by design, so a misspelled name decodes nothing; that consequence
is guarded by a test, not by changing this decision (FINDINGS §3k).
