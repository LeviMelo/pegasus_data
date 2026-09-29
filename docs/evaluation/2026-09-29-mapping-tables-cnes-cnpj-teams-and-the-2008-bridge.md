## 2026-09-29 — The mapping tables: CNES ↔ CNPJ checked against each record's own CNPJ, the team registry, and the 2008 procedure bridge

**Question.** The tables that link datasets are establishment registries,
identifier crosswalks and maps across a change of classification. Do they
resolve real records correctly? Are there several of them doing one job?

**Regime.**
- Branch `redesign`, commits `72d90c8` (ADR-0100), `b18448f` (ADR-0101) and
  `05604ed`.
- Fresh home `~/pegasus_fresh`; maintainer home for the registry build.
- Scripts:
  - `scripts/registry_fields.py`: inventory of register-like fields; artifact
    `data/probes/registry_fields.json`;
  - `query(..., enrich=[...])` on SIH-RD, SIASUS-PA and SIM-DO, AC;
  - registry checks inline in the session: identifier classes, `CNPJ_BR`
    validity, and identifiers left in names.

**What was counted, and why.**
- **Crosswalk.** CNES → CNPJ resolutions agreeing and disagreeing with the
  CNPJ the admission itself records (`CGC_HOSP`), and the reverse. The
  record's own field is evidence independent of the crosswalk, so agreement
  is the measure of whether the link can be trusted.
- **Registry.** Identifiers that are not what they claim to be. A CPF resolved
  to a name breaks a non-negotiable (CLAUDE.md §6).
- **Bridge.** Rows of pre-2008 data that the 2008 map reaches uniquely.

**Result.**

*Inventory* (`registry_fields.json`): 337 register-like fields.

| kind | bound | not resolved on purpose | unbound |
|---|---:|---:|---:|
| establishment (CNES) | 24 | 5 | 11 |
| legal entity (CNPJ) | 32 | 1 | 0 |
| team (INE) | 1 → 3 | 0 | 2 → 0 |
| person (CPF, CNS) | 5 | 40 | 4 |
| occupation (CBO) | 15 → 18 | 6 | 3 |
| municipality | 146 | 32 | 10 |

The unbound establishment fields are SIA's 2001–2007 APAC `*_CODUNI`, which
use the old per-state UPS codes (see Open). The person fields are
identifiers, passed through and never resolved.

*Four mechanisms answered "who is this establishment"* (ADR-0100 lists them).
Measured on the maintainer registry:

| | before | after |
|---|---:|---:|
| `CNPJ_BR` keys that are not CNPJs (zero-padded CPFs, zeros) | 158,043 of 515,946 | 0 of 357,903 |
| registry names carrying a `CPF …-`/`CNPJ …-` prefix | 180,784 | 0 |
| teams in a registry | 0 | 107,438 |

*Crosswalk, SIH-RD AC 2023-01, 4,165 admissions:*

| route | before | after |
|---|---|---|
| `enrich=["CNPJ"]` (CNES → CNPJ) | fails: required a column `CNPJ` | 4,160 resolved, **4,160 confirmed** by `CGC_HOSP`, 0 conflicts |
| `enrichment("CNES", from_field="CGC_HOSP")` | 0 resolved (punctuated keys) | 4,160 confirmed by the record's `CNES`, 0 conflicts |
| `enrich=["CNES.ESTABLISHMENT_NAME"]` | fails without a hand-built resource | 4,165 of 4,165, `current_registry` |

The 5 left in each route are one establishment (`5701929`) with no CNPJ in
the record or the registry.

*Teams, SIASUS-PA AC 2023-01:* `PA_INE` reads "SAUDE DA FAMILIA MODULO I
(0000006564)", 0 undecoded (unbound before).

*The 2008 bridge, SIH-RD AC 2005-01, 4,349 admissions:* 4,190 (96.3%)
reach exactly one SIGTAP procedure. `PROC_REA_grupo` was empty for every
pre-2008 record and now reads "Procedimentos cirurgicos (04)" for 873 of them.

*Occupations, SIM-DO AC 2000:* `OCUP` undecoded 1,778 of 1,778 → 0, from the
kit's `OCUPA` table, which its own `.DEF` names.

**Open.**
- SIA 2001–2007 APAC `*_CODUNI` use per-state UPS establishment codes; the
  table is chosen by the file's state.
- CNES's pre-2007 `CBO` could be bridged to CBO 2002 by the official
  conversion.
- `cnes_registry`, the as-of-month establishment attributes from CNES-ST,
  stays an explicit build.
