## ADR-0100: One establishment registry with typed identifiers; the CNES ↔ CNPJ crosswalk and the name enrichment read it

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0086, ADR-0093, ADR-0094. **Corrects:** ADR-0093.

**Context.** CNES and CNPJ are what link one dataset to another: an
admission's hospital, an APAC's executing unit, a legal entity's
establishments. On 2026-09-29, four mechanisms answered "who is this
establishment", and they disagreed:

| mechanism | source | served |
|---|---|---|
| `registry` | `DBF/CADGER<UF>.dbf` in the current CNES kit, 692,004 establishments | labels, `label_via`, `CNPJ_BR` |
| `crosswalk` pack | CNPJ parsed out of `CNPJ …-NAME` label text in older kits' CADGER copies, confidence 0.6 | `enrich=["CNPJ"/"CNES"]` |
| `_enrich_cnes_name` | resource `cnes_names` (monthly history from CNES-ST) | `enrich=["CNES.ESTABLISHMENT_NAME"]` |
| `_enrich_cnes_attribute` | resource `cnes_registry` (CNES-ST scan) | legal nature, type and ownership as of a month |

Measured defects:
- **CPFs were resolved to names.**
  - `CPF_CNPJ` holds CNPJs (372,831), zeros (148,967), and **CPFs
    zero-padded to 14 digits** (170,203).
  - ADR-0093's "only 14-digit identifiers" filter let every padded CPF
    through, so `CNPJ_BR` had 158,043 non-CNPJ keys. `00098148915253` (a
    person's CPF) resolved to that person's name.
  - 180,784 registry names kept a `CPF 981.489.152/53-` prefix, which wrote a
    CPF into label columns.
- **The pack.**
  - It covers 276,540 establishments, a strict subset of the registry.
  - 1,752,853 of its 1,807,945 rows have no window.
  - 4,065 rows glue a digit of the name onto the CNPJ.
  - It writes CNPJs punctuated, so the CNPJ → CNES direction, which asks in
    digits, never resolved a row.
- **`enrich=["CNPJ"]` failed on every SIH query.** The planner required a
  column literally named `CNPJ`.
- **The name enrichment refused to run without a hand-built resource,** while
  the same names were already labelling the `CNES` column.
- **The SIA team registry was discarded.**
  - `DBF/INE_EQUIPE_BR.dbf` (107,438 teams, `CHAVE`/`DS_REGRA`) failed
    ("Must pass schema"), because the builder kept only DBFs with a `CNES`
    column.
  - `HUF_*` (federal university hospitals) was lost the same way.
  - SIA `PA_INE` and `CO_INE` were bound to nothing.

**Decision.**
- **The registry is the typed source of establishment identity**
  (`registry.build`, `REGISTRY_VERSION = 2`; an older cache is rebuilt on
  first use).
  - `id_kind` is `cnpj` (passes the CNPJ check digits), `none` (zeros) or
    `person_or_invalid`.
  - Only a CNPJ is stored. **A CPF is neither stored nor resolved.**
  - Identifier prefixes are removed from every name.
  - It also keeps the exclusion flag, the inclusion and exclusion dates, and
    the health region.
  - Plain code → name registries (`CHAVE`/`DS_REGRA`, `CNES`/`NOMEFANT`)
    are kept.
  - A national table is the kit's own, or the union of five or more state
    members. `HUF_FILIAL` is not a Alagoas member.
- **`CNPJ_BR` holds valid CNPJs only.**
- **The crosswalk reads the registry first** (`crosswalk._registry_slice`):
  CNES ↔ CNPJ with a window from inclusion to exclusion. The pack's claims are
  normalised to digits, malformed ones are dropped, and they speak only where
  no registry claim covers the record's month (`crosswalk._covering`). Two
  covering claims that disagree stay `ambiguous_crosswalk`.
- **The record's own identifier is optional evidence.** It is compared when
  the layout has one (`OWN_CNPJ_FIELDS`: `CGC_HOSP`, `AP_CNPJCPF`, …) and is no
  longer a required column.
- **`CNES.ESTABLISHMENT_NAME`** uses the monthly history when built, and the
  current registry otherwise, marked `current_registry`.
- **`PA_INE` and `CO_INE`** are bound to `INE_EQUIPE_BR`, owned by the SIASUS
  kit.
- **Left as they are:**
  - `cnes_registry` (CNES-ST as of a month) stays the only source of
    attributes as of a record's competence; that is a bounded build, and the
    user asks for it.
  - The label pack's crosswalk stays a source of historical claims.

**Result, fresh home `~/pegasus_fresh`, SIH-RD AC 2023-01 (4,165 admissions).**
- **CNES → CNPJ:** 4,160 resolved and **4,160 confirmed** against each
  admission's own `CGC_HOSP`, with **0 conflicts**. The 5 left are one
  establishment with no CNPJ anywhere. Before, the route could not run.
- **CGC_HOSP → CNES:** 4,160 confirmed against the record's `CNES`, 0
  conflicts. Before, 0 resolved.
- **Establishment name:** 4,165 of 4,165, `current_registry`, with no build.
- **SIA-PA AC 2023-01:**
  - `PA_INE` reads "SAUDE DA FAMILIA MODULO I (0000006564)", 0 undecoded;
  - `PA_CNPJMNT` has 0 undecoded.
- **Maintainer registry:**
  - `CNPJ_BR` 357,903 entries, 0 invalid (515,946 before, 158,043 of them not
    CNPJs);
  - 0 names carry an identifier (180,784 before).
