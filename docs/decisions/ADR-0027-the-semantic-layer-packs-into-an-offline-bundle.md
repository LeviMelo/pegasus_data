## ADR-0027: The semantic layer packs into an offline bundle, restored additively and by column name

**Date:** 2026-08-19. **Status:** superseded (2026-09-28, by ADR-0075).

**Context.** Everything the module can say about a value derives from an FTP
server that is often slow, sometimes unreachable, and not under anyone's
control, while the data's meaning does not change when the server does
(`docs/history/pegasus_data_ARCHITECTURE.md` §10). Measured on the full
catalog: 19,905,196 dictionary rows; 9,544,839 bound to some field (48.0% of
rows, 19.5% of codelists); 7,481,170 after de-duplication. Added in `586cade`
(2026-08-19); batched restore in `e87d4c9`.

**Decision.**
- `pegasus-data pack` writes a bundle holding the dictionary, field bindings,
  curated meanings, schema catalogue and parsed layout documentation. It holds
  no inventory, no profiles and no data: it is the means to interpret data
  someone already has. 153 MB for all sixteen systems, about 10 MB for one.
- Only codelists bound to a field are packed. Rows are de-duplicated on
  `(system, codelist, code, label)` with the validity span carried, so a
  reworded code keeps both readings.
- `--max-codelist-rows` names in the manifest what it dropped.
- **Columns are matched by name, never by position.**
- **Unpacking is additive by default**; `--replace` is for a bundle that is
  the source of truth.

**Alternatives.** Requiring a crawl on every machine. Rejected: a module that
can only translate while DATASUS is up cannot be relied on.

**What would reverse it.** The shipped label pack (ADR-0037) covers the
fresh-install case. The bundle stays as the transport format for a full
semantic catalog, distinct from the dictionary read model (ADR-0028).
