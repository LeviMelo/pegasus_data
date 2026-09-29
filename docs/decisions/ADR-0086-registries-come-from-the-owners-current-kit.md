## ADR-0086: Registries come from their owner's current kit, on first use; a coded column that nothing decodes is visibly undecoded

**Date:** 2026-09-29. **Status:** active. **Amends:** the `registry` role in
`curation/codelists.yml` (held out of the pack), ADR-0063, ADR-0084.

**Context.**
- **Establishments had no names.** Every establishment code was shown bare,
  e.g. SIH `CNES 4020197`. The establishment registry (`CADGER*`) had been held
  out of the label pack as "entity data", and the pack carried 32,751 stale
  rows out of about 690,000.
- **The registry was bound in the wrong places.** Only CIH's `.DEF` bound
  `CNES` to it. For SIH, `CNES` had no binding at all.
- **The registry was not where the pipeline looked.**
  - It is **not a `.CNV`**: it is `DBF/CADGER<UF>.dbf` inside **CNES's** kit
    (`TAB_CNES.zip`, 127 MB). The DBF has `CNES`, `FANTASIA`, `RAZ_SOCI`,
    `CPF_CNPJ`, `CODUFMUN`, `DATAINCL` and `DATAEXCL`.
  - SIH's kit holds one registry table and CIH's none (measured 2026-09-29).
- **Undecoded codes were invisible.** A column the curation marks as coded, but
  that nothing decodes, was rendered with no label companion. The readable
  presentation then showed `000000` as if it were a value, not `000000 (?)`.

**Decision.**
- **Registries are fetched on first use.** `registry.py` resolves a registry
  table from its **owner's** current kit (`OWNER`: `CADGER*` and `UNIDTOTAL`
  to CNES).
  - The kit is downloaded once (the download is stated), and only its registry
    members are parsed: 29 s, versus more than ten minutes for a full kit
    parse.
  - The tables go to `<home>/registries/<SYSTEM>/`. The national table is the
    union of the 27 state tables.
  - The label is the trade name, falling back to the legal name without its
    `CNPJ …-` prefix. CNPJ, municipality and dates are kept beside it.
  - `persist/reference.read_reference_table` asks the registry before the lake
    and the pack.
- **Establishment fields are bound in the curation.** 23 establishment-code
  fields across CIH, CIHA, CNES, e-SUS Notifica, Painel Oncologia, SIA, SIH,
  SIM, SINASC, SINAN and SISCAN are bound to `CADGERBR`. It is appended as a
  fallback where a system's own unit table was already bound.
  - The 2001–2007 APAC `*_CODUNI` fields are excluded: they hold 6-digit
    legacy SIA unit codes, not CNES.
- **Undecoded codes are visible.** A column the curation marks as coded gets a
  `_label` companion even when nothing decodes it (all null). The presentation
  then shows its codes as `code (?)`.

**Result, 2026-09-29, live home, SIH-RD Alagoas 2022-01 (12,854 admissions):**
- `CNES` decodes every row, e.g. `HOSPITAL GERAL DO ESTADO DR OSVALDO BRANDAO
  VILELA (2006510)`. The registry holds 692,004 establishments in 30 tables
  (32 MB).
- `CBOR` reads `000000 (?)` in every row: no DATASUS table defines `000000`.

**What would reverse it.** DATASUS publishing the registry as a dataset with a
stable key and names (CNES-ST carries no names). The registry would then be
read from it.
