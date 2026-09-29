## ADR-0087: A standard classification is one canonical table for every system, and a label must say what the code means

**Date:** 2026-09-29. **Status:** active. **Amends:** the rule that a codelist
is keyed by its system (CLAUDE.md §6), ADR-0079, ADR-0080, ADR-0085.

**Context.**
- **What the user saw.** "Decoding" that pointed to another undecipherable
  code.
- **What a scan of real queries found** (SIM-DO Alagoas 2022, SIH-RD Alagoas
  2022-01, CNES):
  - **ICD-10.** Each system decoded ICD from its own TabWin `.CNV`, whose labels
    are abbreviations that lean on an unstated category: `N039` → "N03.9 NE",
    `O800` → "O80.0 Parto espontaneo cefalico".
    - SIM writes an undivided category with a filler (`I64X`). No table carried
      that form, so every cause-of-death line (`LINHAA`–`LINHAII`) echoed the
      code back as its "label".
    - CIHA's secondary diagnosis was bound to the ICD **group** tables,
      labelling a diagnosis with its group.
  - **SIM's own tables were terse.** `SEXO` read `M`/`F`; `FONTEINV` read
    `S V O`, `I M L`; `OBITOPUERP` read `00-42`; `GESTACAO` read `22 a 27`,
    with no unit.
- **Why the system-keyed rule did harm here.** "A codelist is keyed by its
  system" exists because DATASUS's **own** codes differ between systems (SEXO 3
  is Feminino in SIH). A published standard is the same everywhere, so keying
  it by system only meant each system carried a worse copy.

**Decision.**
- **Standard classifications are canonical.** A published standard is served
  from ONE table for every system (`persist/reference.CLASSIFICATIONS`). The
  first is `ICD10`: `resources/icd10.parquet`, built by
  `scripts/build_icd10.py` from these sources, in order:
  - DATASUS's official CID-10 tables (V2008, `www2.datasus.gov.br/cid10`) with
    full descriptions: 2,045 categories and 12,188 subcategories;
  - 26 later codes found in the kits;
  - four WHO 2020–2021 emergency codes (U07.1, U07.2, U09.9, U10.9), marked as
    such;
  - the filler form `<category>X` for every category.

  71 ICD fields across CIH, CIHA, SIA, SIH, SIM, SINAN and SINASC are bound
  to `ICD10`, with ICD-9 tables kept after it for 1990s records. Group and
  chapter tables are no longer bound as a diagnosis's label. Seven `.DEF`
  bindings of ICD to non-diagnosis fields (`IDADE`, lab results) are left
  unbound.
- **Each system's data dictionary is harvested.** SIM's
  (`dicionario-de-dados-SIM-tabela-DO.pdf`, svs.aids.gov.br) gives 34 code
  tables across its 8 series, for example `SEXO` (M,1 masculino; F,2
  feminino; I,0,9 ignorado), `OBITOPUERP` and `GESTACAO`. The harvester now
  reads three table layouts, and handles code aliases ("M,1") and codes split
  or glued across lines.
- **Acronyms are expanded** where the same document names the service. For
  SIM `FONTEINV`: SVO (Serviço de Verificação de Óbitos), IML (Instituto
  Médico Legal).
- **Opaque labels are measured.** A label with no real word once the code and
  placeholder runs are removed ("05", "A1", "3 .. 5") is **opaque**
  (`label_bindings.is_opaque`). The compile records such codes in
  `label_gaps` with `kind='opaque'`. `pegasus-data meaning` reports a field as
  `opaque`, not `decoded`, when any observed code has one.
- **Multi-valued fields read like single ones.** Each token is shown as
  `label (code)`, and an undecoded token as `code (?)`, never bare.

**Result, 2026-09-29, live home.**
- SIM-DO AL 2022:
  - `CAUSABAS` reads "Infarto agudo do miocárdio não especificado (I219)";
    `LINHAII` reads "Hipertensão essencial (primária) (I10X) | Diabetes
    mellitus não especificado - sem complicações (E149)".
  - `SEXO`, `LOCOCOR`, `OBITOPUERP`, `GESTACAO` and `FONTEINV` read in full
    words.
  - Codes outside ICD-10 (`R969`, `I100` for the undivided I10) read `(?)`.
- SIH-RD AL 2022-01: `DIAG_PRINC` reads "Parto espontâneo cefálico (O800)",
  with 0 unlabelled rows.

**Still open** (the next `meaning` run lists them):
- SIM `ORIGEM` has no table.
- 262 SIM `OCUP` rows hold codes outside the CBO table.
- Other standards (CBO, SIGTAP, CNAE, municipalities) need the same canonical
  treatment.
