# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-09-29, night.

## Where the project is

Development resumed on 2026-09-28 on branch `redesign`. The first day made the
read path deliver meaning, with one door (`query()`) and measured sampling
(ADR-0061 to ADR-0082). The second day (ADR-0083 to ADR-0099) went after the
standing instruction that every variable be described and every code
translatable, by meaningful labels rather than one opaque code standing in for
another.

## Done (live-verified)

- **Presentation** (ADR-0084).
  - Headers read "Variable name (CODE)" and values "Label (code)"; an
    undecoded value reads `code (?)`.
  - Presets `readable` (the default), `analysis`, `labels` and `codes`, plus
    templates and pt/en.
  - Every coded column leaves rendering with a label companion (ADR-0093).
- **Canonical classifications,** one table for every system (ADR-0087):
  - ICD-10, falling back to the category when a subcategory is not listed
    (ADR-0089);
  - SIGTAP, with group, subgroup and form as dimensions (ADR-0092);
  - CBO 2002, banks, naturality/countries, states and health regions.
- **Establishments and legal entities.**
  - Registry names come from the CNES kit (692,004 establishments,
    ADR-0086).
  - CNPJ → legal name; a CPF is never resolved (ADR-0093).
  - A maintainer is named through the row's establishment (ADR-0094); the
    documented all-zeros is "Sem mantenedora" (ADR-0097).
- **Relations between columns.**
  - A composite key (`CLASS_SR`, `PA_CLASS_S`, `SUBFIN`), whose parts can carry
    the record's width: age unit + age via `IDADEDET` reads "3 dias"
    (ADR-0088, ADR-0098).
  - A sibling that names the code (ADR-0090).
  - Path tables whose unlisted codes are named by their deepest listed level
    (`VINCULO`, `S_CLASSEN`, ADR-0096).
- **Municipalities** show the 7-digit IBGE code.
- **The kits are read correctly** (ADR-0095). 43,916 `.CNV` lines had codes
  glued to their labels (`PACIENT15`); a re-read now supersedes the old
  reading.
- **Speed** (ADR-0097). One year of SIASUS-ACF, files cached: 104 s → 16.7 s
  (35 s in a fresh process).
- **Descriptions.**
  - DADOS_ABERTOS inherits SIASUS's curation (ADR-0095).
  - Curated: BASE_AIH1 (60 fields), SIA PQ (7), SIA UO (4) and the SI-PNI
    exports (22).
- **Sweep tools.** `scripts/sweep_undecoded.py` lists undecoded values over 16
  datasets. `scripts/def_evidence.py` lists what each `.DEF` offers for them.

## Linking datasets (ADR-0100 to ADR-0103)

- **One establishment registry.** Typed identifiers: only a valid CNPJ is
  stored, a CPF is never stored or resolved, and no identifier appears in any
  name or label (ADR-0102). The registry also holds maintainers,
  inclusion/exclusion dates, 107,438 health teams (INE) and the federal
  university hospitals.
- **CNES ↔ CNPJ** reads the registry first, then older kits' claims.
  - SIH AC 2023-01: 4,160 of 4,165 resolved, and every one confirmed by the
    admission's own `CGC_HOSP`.
  - The reverse direction works; it resolved nothing before.
- **The 2008 procedure break is bridged** by the official Tabela Unificada
  map, one-to-one only. 96.3% of SIH AC 2005 admissions reach a SIGTAP
  procedure, and the SIGTAP group/subgroup dimensions are continuous.
- **Pre-2006 occupations** decode from SIM/SINASC's own `OCUPA` table.
- **SIA's 2001–2007 establishment codes** are keyed by the file's state
  (`SIA_UPS_BR`).
- **In progress:** the ranged census of every legacy APAC archive's members,
  then inventory → strata → families → seed (`data/logs/rebuild-members.ps1`).
  Membership was assumed from one archive per state-year. It listed tables
  that most archives lack, and missed EX, PC and AC for 2003–2006.

## Coverage now

- **Kits and pack.** The maintainer catalog was re-read with the fixed parser.
  The label pack and the seed are rebuilt from it; the pack no longer loses a
  window the catalog lacks (ADR-0095).
- **Per family-field** (`pegasus-data meaning`, 22,714 rows):
  - missing descriptions: 441 → 130;
  - undecoded: 240 → 34;
  - opaque: 120.
- **Per cell, fresh home, 16 datasets:** undecoded 1.23 M → 0.56 M, with no
  regressions. What remains is mostly values that no source documents
  (EVALUATION, 2026-09-29).

## Open fronts

- **Undecoded because no source names them:**
  - SIH `TPDISEC*` `0`, `GESTOR_TP`, `SP_DES_*`, `SP_U_AIH`;
  - SIA `TIPPRE` `00`, `AP_TPATEN` `12`, `PA_CODOCO`;
  - CNES `TP_PREST` `99`, bank codes `71X`/`002`, `ID_AREA`/`ID_SEGM`
    placeholders;
  - SINASC `CODPAISRES` `1`, `KOTELCHUCK` `9`, `TPDOCRESP` `0`;
  - SINAN meningitis quadros (OQ-59).

  Each reads `code (?)`.
- **Undescribed:**
  - SIA UO's 74 modality fields and PQ's 14 name-only fields (no layout
    found);
  - BASE_AIH1's 11 fields without an RD/SP twin;
  - its age pairing, unverified until a sample of the 12 GB file is read.
- **Renamed columns** across layouts (OQ-57).
- **Speed.** A cold process still spends most of its time in per-group
  binding decisions and catalog reads.
- **Carried:**
  - distinct-count measures and age-standardised rates;
  - health macroregions;
  - moving `tools/` into the package;
  - mypy;
  - splitting `cli`, `retrieve` and `view`.

## Waiting on the user

- **Publishing.** `redesign` is not pushed (CLAUDE.md §4). Platform wheels for
  the compiled DBC engine (ADR-0074).

## Tests and checks

- `scripts/live.py --all --fresh` and `scripts/sweep_undecoded.py` on a fresh
  home.
- `ruff check src scripts tests` and `scripts/check_docs.py`.
- `pytest -q -m "not network"` is a regression net that does not grow
  (CLAUDE.md §5).
