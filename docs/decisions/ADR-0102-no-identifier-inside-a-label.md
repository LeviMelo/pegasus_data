## ADR-0102: No CNPJ or CPF inside a label, wherever the label comes from

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0100.

**Context.**
- **ADR-0100 cleaned only one source.** It removed identifiers from the
  registry's names. The other label source, the reference tables from the
  kits and the label pack, carries the same habit: DATASUS's per-state
  establishment tables glue the identifier onto the name.
- **Examples:** `84.306.455/0001-20-UNIDADE BASICA PADRE TEODORO`, and
  `000.026.159/91-ARNOLDO …`, which is a **CPF**, a person's identifier, in
  the kit's own layout.
- **Measured:** 558,043 of 3,661,868 label rows in the rebuilt pack began with
  one, mostly in SIA's `UPS-N/C<UF>` and `CNESN/C<UF>` tables. A field decoded
  through them would have printed a CPF inside its label, which CLAUDE.md §6
  forbids.
- **Two copies of the identifier logic.** The check digits (`valid_cnpj`)
  lived in `crosswalk.py`, and a prefix pattern lived in `registry.py`.

**Decision.**
- **`identifiers.py` is the one place** for what an identifier is
  (`valid_cnpj`, `valid_cpf`) and for keeping it out of labels
  (`ID_PREFIX`, `strip_identifier`). The registry, the crosswalk, the label
  pack and the render path all use it.
- **Every label map strips a leading identifier** (`view._map_from_table`, in
  Arrow), so a lake or pack built before this decision is clean at read time.
  A label that was only an identifier is dropped.
- **The pack build strips too** (`labelpack.build_label_pack`), including the
  windows it carries forward. A CPF is not kept even as a crosswalk claim:
  only `CNPJ …-` labels feed the crosswalk.

**Result.**
- Rebuilt pack: **0** labels with an identifier (558,043 before), 0 codelists
  lost, 26.7 MB (was 27.9).
- Fresh home, SIASUS-ACF 2023-01, `present="analysis"`: 0 of the label
  columns' distinct values contain an identifier.
