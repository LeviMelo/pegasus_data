## ADR-0011: Codes are stored per codelist, bound to fields, and carry a validity window

**Date:** 2026-08-18. **Status:** active.

**Context.** Measured on 2026-08-18 (`docs/history/FINDINGS.md` §3):

- Modelling `.CNV` entries as `(system, field, value) → label`, as the brief's
  DDL suggested, produced 1,339,916 "conflicts" on two kits. Almost all were
  spurious: `SEXO.CNV`, `SIMNAO.CNV`, `REGIAO.CNV` and dozens more all define
  code `1`, and with `field_name` NULL they collided. A `.CNV` never says which
  field uses it; the `.DEF` does (FINDINGS §1 V3).
- With codelists separated, ingesting the modern `TAB_SIH.zip` beside
  `TAB_SIH_199201-199712.zip` still gave 76,115 conflicts, because one codelist
  name carries different mappings in different eras. Both kits are right for
  their own window.

Implemented in `158c6ac` (2026-08-18).

**Decision.**
- Codes are stored once per **codelist** and attached to fields through
  `field_codelists`, populated from the `.DEF` declarations.
- `valid_from`/`valid_to` are read from the kit's filename
  (`TAB_SIH_199201-199712` is 1992-01 to 1997-12; a bare `TAB_SIH.zip` is
  current) and are part of the entry's identity.
- A codelist is later keyed by its system as well (ADR-0021).

Result on the same inputs: 41 conflicts on two kits, all genuine; 5,133 on six
kits, all real disagreements inside one window. The municipality table is no
longer duplicated once per column that uses it.

**Alternatives.** The brief's field-keyed dictionary. Rejected by the
1,339,916-conflict measurement.

**What would reverse it.** Nothing foreseen.
