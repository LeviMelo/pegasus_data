## ADR-0099: A label that restates a code, or drops its unit, is replaced by the documented meaning

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0085, ADR-0087.

**Context.**
- **The measure.** After the rebuild, `pegasus-data meaning` (catalog after
  `rebuild-cnv2`; `data/probes/coverage/rebuilt-cnv.parquet`) classes 219
  family-fields as **opaque**: their chosen table has labels with no word left
  once the code is removed (`label_bindings.is_opaque`). By field, they are:
  - SINAN `ID_REGIONA`/`ID_RG_RESI` (71): the regional table labels some codes
    only by their number (`1497` → "001");
  - SINASC `ESCMAE`, `GESTACAO`, `CONSULTAS` (63): the kit labels drop the
    unit ("01-03", "28-36", "7 e +");
  - SINAN `COUFINF` (20): `UFCSIGLA` labels "AC" as "AC";
  - SIM `GESTACAO`/`SEMANGEST` (24): SIM's grouping, "20 a 27";
  - SINAN `ID_AGRAVO` (9): `AGRAVSURT` labels "A009" as "A009";
  - smaller ones.
- **Some were the rule's fault, not the table's.** A word needed three
  letters, so "Pé", "Um" and "5 cm" counted as no word.

**Decision.**
- **A word is two letters or more** (`_WORD`), so real short words and units
  count.
- **SINASC `ESCMAE`, `GESTACAO` and `CONSULTAS`** take inline codes from the
  SINASC structure document ("1 a 3 anos", "22 a 27 semanas", "De 1 a 3
  consultas"). The kit table stays as the fallback for its own extra
  tabulation codes.
- **SINAN `COUFINF`** reads the canonical state table first (ADR-0087).
- **SINAN `ID_AGRAVO`** reads ICD-10 first. An agravo is filed by its CID-10
  code: `B659` is "Esquistossomose não especificada".
- **Left for evidence:**
  - SIM `GESTACAO` changed coding across vintages (the kit's `SEMANAS` holds
    the old "1 Menos 20, 2 20 a 27, 3 28 e mais" beside the newer grouping).
    Inline codes would impose one vintage on every year, so it waits for
    per-vintage windows.
  - The SINAN regional numbers are what the state's own table says.

**Result, fresh home, 2026-09-29.**
- SINAN-ESQU 2022:
  - `ID_AGRAVO` "Esquistossomose não especificada (B659)";
  - `COUFINF` "Minas Gerais (31)".
- SINASC-DN AC 2022:
  - `ESCMAE` "8 a 11 anos (4)";
  - `GESTACAO` "37 a 41 semanas (5)";
  - `CONSULTAS` "7 consultas e mais (4)".
