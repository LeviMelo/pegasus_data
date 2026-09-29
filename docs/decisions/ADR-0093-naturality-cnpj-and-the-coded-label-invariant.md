## ADR-0093: Naturality and CNPJs decode from canonical tables; every coded column leaves with a label companion

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0086, ADR-0087.

**Context.**
- **Naturality.** SINASC `NATURALMAE` (and SIM `NATURAL`) code a person's
  naturality in 3 digits: 800 Brasil, 8xx a state (812 Acre), others a
  country. Two DATASUS tables disagree on the same codes:
  - SIM's `TABPAIS` is the real list (`105` GUYANA, `045` CANADA);
  - SINASC's `NATURAL` is a TabWin **grouping** that maps every foreign
    country to "Ignorado". Using it would call a foreign-born mother's
    birthplace unknown.
- **Undecoded codes still slipped through.** A column the curation marks as
  coded could leave the renderer with no label companion through several
  refusal branches ("nothing matched", "one value throughout", "the table
  contradicts itself"). The readable form then showed a bare code that reads
  like a value: SINASC `CODPAISRES` `1`. ADR-0086 patched one branch.
- **CNPJ fields were undecoded.** CIH, CIHA and SIH `CGC_HOSP`, the maintainer
  CNPJs (`CNPJ_MAN`, `CNPJ_MANT`, `*CNPJMNT`), SIA's credit-assignment CNPJs
  and the APAC entity CNPJs carried legal entities with no names.

**Decision.**
- **`NATURALIDADE` is canonical** (`scripts/build_countries.py`, 289 codes from
  SIM's `TABPAIS`). It is bound to SINASC `NATURALMAE` and `CODPAISRES` and to
  SIM `NATURAL`.
- **The invariant is enforced once.** After the render loop, every column the
  curation marks as coded gets a `_label` companion, null where nothing
  decoded it (`view.render_table`), so it shows as `code (?)`.
- **`CNPJ_BR`, a legal entity's name by CNPJ,** is derived from the
  establishment registry (`RAZ_SOCI` without its `CNPJ …-` prefix). It is
  built with the registry cache: 515,946 CNPJs, only 14-digit.
  **Corrected 2026-09-29 (ADR-0100):** the 14-digit filter was not enough.
  158,043 of those 515,946 keys were not CNPJs: `CPF_CNPJ` holds CPFs
  zero-padded to 14 digits, so persons' CPFs were resolved to their names.
  `CNPJ_BR` now keeps only identifiers that pass the CNPJ check digits
  (357,903).
  - An 11-digit **CPF is never resolved to a name**: it is a person's
    identifier, passed through unmodified (CLAUDE.md §6).
  - Mixed CPF/CNPJ fields (`PA_CNPJCPF`, `CPF_CNPJ`) stay unbound.
  - 28 pure-CNPJ fields are bound to it.
- **SINASC `SEXO`.** The structure document's "M- Masculino F- Feminino I-
  Ignorado", with the kit's `0` → "I", gives `0` = Ignorado.

**Result, 2026-09-29, live home.**
- SINASC-DN AC 2022:
  - `NATURALMAE` reads "Acre (812)", with 0 undecoded;
  - `CODPAISRES` reads `1 (?)` (undocumented; the field is documented as 3
    digits);
  - `KOTELCHUCK` `9` (2,238 rows) and `TPDOCRESP` `0` (54 rows) read `(?)`:
    neither is in the structure document.
- CIH-CR AL 2010-01: `CGC_HOSP` reads "SANTA CASA DE MISERICORDIA DE SAO MI
  (12737680000100)", with 0 undecoded.
- SIH-RD AL 2022-01:
  - `CGC_HOSP` reads "SECRETARIA DE ESTADO DA SAUDE (12200259000246)";
  - `CNPJ_MANT`: 5,393 rows `(?)`.

**Open.** A **maintainer's** CNPJ is usually not itself an establishment, so
it is absent from the registry's CNPJ key; the registry holds the maintainer's
name (`RSOC_MAN`) on each establishment row. Naming it means following the
row's own establishment (`CNES` → `RSOC_MAN`), which is a different relation
from a code table.
