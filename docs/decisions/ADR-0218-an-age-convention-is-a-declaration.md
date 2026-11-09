# ADR-0218: An age convention is a declaration, not a system named in code

2026-11-09. Status: active. Amends ADR-0070 (how an age is written); closes defect 4 of the 2026-11-08 principles audit.

## Context

`_age.py` decoded ages by system name: `sih`, `cih`, `sim`, `sinan`, `sivep`, each a branch with its own unit table in
code. Every aggregate repeated its system's name and columns (`encoding: sinan, fields: [NU_IDADE_N]` in 55 SINAN
files). A new system needed a code change, and the convention lived in two places: the variables' `IDADE_anos` recipe
and each aggregate.

## Decision

- **Five forms, the unit table as data.** An age is `unit_column` (value and unit columns), `packed` (the leading
  character is the unit), `years`, `dates` or `band`. Its `units` map a unit code to `minute`, `hour`, `day`, `month`,
  `year`, `hundred_plus` (100 + value) or `decade` (10 × value). `unknown` lists codes that are no age (SIM's `000`).
  `plain_below` says a shorter value has no unit digit (SINAN's 1–3 character ages are years).
- **Declared once per system**, on the derived variable: `IDADE_anos`'s `age:` block in `curation/variables/<system>`
  (and SRAG's in `intake.yml`). The measured unit tables of ADR-0070 moved there unchanged.
- **An aggregate names the variable** (`age_dimension: {of: IDADE_anos}`), resolved through the dataset's variable
  docs (`_age.resolve_age`). It keeps only its own bands and label. Two declarations of one name refuse.
- A negative value is no age in every form (it was SIVEP's rule alone).

## Evidence

The old module, frozen, against the new forms on real records (`scratchpad/age_equiv.py`): SIM-DO AC 2022 4,159 rows,
SIH-RD AC 2022-01 3,977, SINAN-DENG 2022 1,405,095, CIH-CR AC 2010-01 180, CIHA AC 2021-01 240, SRAG 2022 566,133.
Every value is equal, nulls included.

## Consequences

70 curation files changed, no system name is left in the decoder, and a new system's age is a YAML block. The
aggregates resolve their age from the catalog's variable docs, so they read it after `pegasus-data curate`.
