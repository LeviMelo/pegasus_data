## ADR-0075: The dictionary database and the semantic bundle are retired; the seed and `compendium()` carry the meaning

**Date:** 2026-09-28. **Status:** active. **Supersedes:** ADR-0027 (the
semantic layer packs into an offline bundle), ADR-0028 (the dictionary is one
SQLite database). **Amends:** ADR-0069.

**Context.** Five mechanisms exported the semantic layer (ARCHITECTURE §5):
- `labelpack` ships the label pack;
- `bundle.pack/unpack` moved a catalog's semantic tables between machines;
- `docsgen` wrote `docs/dictionary.sqlite`, 557 MB on the maintainer's
  machine, with per-variable Markdown pages, a full-text index, and the
  `dictionary`, `page` and `search` commands;
- `_compendium` writes a researcher's SQLite map;
- `persist/reference` writes the lake's code tables.

Since ADR-0067, every install's catalog starts from the seed:
- the files, schemas and families;
- 4,534 curated variable descriptions;
- the bindings, and after ADR-0072 the decided bindings.

The label pack ships beside it. So:
- `search()` answers from the catalog and the pack (ADR-0069).
- `pegasus-data query --dictionary` writes a table's dictionary from the same
  curation (`_dictionary.describe_table`).
- The bundle's job, moving meaning to a machine without the build, is done by
  the wheel itself.

What remained was two more copies of the same tables, one of them half a
gigabyte, each with its own schema to keep in step.

**Decision.**
- Delete `docsgen.py` and its `dictionary` and `page` commands, and delete
  `bundle.py` with `pack`, `unpack`, `read_manifest` and `BundleError`, from
  the package, the CLI and the public namespace. Delete their tests.
- `compendium()` stays: a small, researcher-facing SQLite map meant to be
  emailed, built from the catalog.
- `labelpack` (the shipped pack) and `persist/reference` (the lake's code
  tables) stay. They are the label data, not copies of it.

**What would reverse it.** A need to move a *locally curated or adjudicated*
semantic state between machines without rebuilding a seed. A bundle of the
seed tables from `catalog/seed.SEED_TABLES` would serve it; it would not need
a second schema.
