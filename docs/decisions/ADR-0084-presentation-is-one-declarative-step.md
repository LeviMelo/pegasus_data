## ADR-0084: How a result reads is one declarative step, applied last; the default reads "Masculino (1)" under "Sexo (SEXO)"

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0063 (raw code kept,
label as companion), ADR-0073.

**Context.**
- **The user's aim.** To de-obfuscate DATASUS data: a header should read
  `Nome da variável (CÓDIGO)`, a value `Rótulo (código)`, and the user should be
  able to change both.
- **What `query()` gave instead.** Raw codes plus `<column>_label` companion
  columns, doubling every coded column.
- **Mechanisms that already overlapped.**
  - The `report` render profile translated headers and combined values
    (`1 – Masculino`).
  - A separate `names="described"` option in the executor renamed headers again,
    by another route.
  - Only `labels=True/False` reached `query()`.

  That made three partial answers to one question.
- **Why the companion form exists.** It is the right form for machines. Codes
  join, group and filter stably across vintages, while a label's wording
  changes between editions of a table.

**Decision.**
- The engine always builds the **canonical** form (raw code plus
  `<column>_label`). One pure function, `presentation.present()`, turns it
  into what the caller asked for, as the last step of `query()`, `export()`
  and the `query`/`translate` CLI commands.
- A `Presentation` has these fields:
  - `values`: a template with `{label}` and `{code}`;
  - `unlabelled`: the template for a code no table decodes, `{code} (?)` by
    default, so it stays visibly undecoded;
  - `names`: a template with `{name}` and `{code}`;
  - `language`: `pt` for the layout document's name, `en` for the translated
    one;
  - `companions`: keep the canonical form;
  - `codes_only`.

  A label that already opens with its code (`O80.0 Parto…`,
  `120001 Acrelândia`) is not printed twice.
- **Presets.**
  - `readable` is the **default**: `Feminino (3)` under `Sexo do paciente (SEXO)`.
  - `analysis`: codes plus `_label` columns, original names.
  - `labels`: labels only.
  - `codes`: as filed.
- **How a user chooses.**
  - Per call: `query(present="analysis")`, or a mapping of overrides such as
    `present={"values": "{code} - {label}", "language": "en"}`.
  - As a default: `presentation` in `pegasus-data.toml` (a preset or a
    mapping).
  - On the CLI: `--present`, `--values`, `--names`, `--language`.
- **Removed.** The `report` profile, the `combined` render mode,
  `RenderProfile.headers`/`values`, `view._combine`, `view._apply_headers`,
  `RenderReport.renamed_headers`, the executor's `names=` and `_described`,
  and the CLI's `--no-labels`, `--described-names` and `translate --profile`.
  `query(labels=False)` is now `present="codes"`.

**Result, 2026-09-29, SIH-RD, Alagoas, 2022-01.**
`Município de Residência do Paciente (MUNIC_RES)` reads `Delmiro Gouveia, AL (270240)`;
`Sexo do paciente (SEXO)` reads `Feminino (3)`;
`Código do diagnóstico principal (DIAG_PRINC)` reads `Parto espontaneo cefalico (O800)`.
The same view shows what is not yet decoded:
- `CNES`: the establishment registry was held out of the label pack by
  design;
- `CBOR`: `000000`.

Both are addressed by the coverage work that follows.

**What would reverse it.** Users who mostly feed results into code rather
than read them. The default preset would then become `analysis`, and nothing
else would change.

**Amended 2026-09-29 (user):** a municipality shows its **7-digit IBGE code**:
"Maceió, AL (2704302)". DATASUS files the 6-digit code, which is the 7-digit
code minus its check digit, so the 7-digit code carries strictly more.
- **Which columns.** A column is treated as a municipality when its curated
  codelist is a municipality table (`presentation.documented_names`, which
  carries a `municipal` set).
- **Special codes.** DATASUS's own codes (`000000` Ignorado ou exterior, the
  per-state "município ignorado") have no IBGE equivalent and are shown as
  filed.
- **The canonical form is unchanged.** The `analysis` preset keeps the filed
  code.
