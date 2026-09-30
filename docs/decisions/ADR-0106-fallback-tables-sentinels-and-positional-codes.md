## ADR-0106: Measured sentinels and single codes, national tables behind the system's own, and positional CNV codes

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0093, ADR-0105.

**Context.** The sweep after ADR-0105 (`scripts/sweep_undecoded.py`, new home)
left 32 columns with undecoded values. Several had an answer in the data or in
a table the project already held:

- **ADR-0105's fallback fix exposed a source conflict.** SINASC `KOTELCHUCK`:
  the 2019 structure document names "Não classificados" 6; the kit's
  `KOTELCHUCK.CNV` names it 9. SINASC 2022 AC, RR and MS hold 9 on 3,697 rows,
  each with `MESPRENAT` null or 99 (3,637) or a start month beside `CONSULTAS`
  1 Nenhuma / 9 Ignorado (60), and never 6. ADR-0105 listed 9 as undocumented;
  it was documented by the kit, and hidden by the inline table.
- **Codes one column takes, proven by another column of the same record:**

  | field | measured on | finding |
  |---|---|---|
  | SINASC `CODPAISRES` | 2022 AC, RR, MS; AC 2012 | 1 on 70,754 of 70,754 filled rows, each with a Brazilian residence municipality. TABPAIS's Brasil is 800 (ADR-0093); the files use 1 |
  | SIH `GESTOR_TP` | SIH-RD 2023-01 AC (4,165), SP (210,225) | 1 exactly when `GESTOR_CPF` is filled (171; 35,223), 0 exactly when empty; no other value. The curated description ("state or municipal manager") had no source and is wrong |
  | SIH `GESTOR_COD` 00000 | same | not in `LIBGESTOR`, whose codes are combinations of the rules a manager lifted; on every AIH without authorisation and on 20,488 of 35,223 with one |
  | CNES `CNPJ_MAN` all zeros | CNES-ST AC 2023-01 | exactly the 735 `NIV_DEP` 1 (individual) establishments; all 543 `NIV_DEP` 3 hold a valid CNPJ |
  | SIA-BI `CNPJ_CC` all zeros | SIA-BI AC 2023-01 | 68,541 of 68,554 rows; the layout says zeros when no credit cession applies |
  | CNES `TP_PREST` 99 | CNES-ST AC 2008–2023 | 20/22/40/50/60/61 in 2008 and 2012; 99 on every row in 2016, 2020 and 2023 |

  The all-zero CNPJs became undecoded when ADR-0100 typed the registry: a
  string of zeros is not a CNPJ and no longer sits in `CNPJ_BR`.
- **A national table held the code the system's copy lacks.** SIA `PA_TPUPS`
  85 (151 rows): SIA's `TP_ESTAB` lacks it; CNES's unit-type table `TP_UNID`
  names it (Centro de imunização). SIA `PA_REGCT` 7114 (835 rows): the SIA
  kit's `REGRA_C`/`PA_REGCT` stop short of it; the national `REGRAS` table
  names it in full. SIH's `REGCT` also has it but is keyed by its system and
  is not visible from SIA, by design.
- **A positional CNV was mis-parsed.** `TP_DROGA.CNV` (TAB_SIA) writes the
  substances as letters in fixed places (`A  `, `AC `, `A O`, ` C `, ` CO`,
  `  O`). The token split kept 3 of 7 rows and read `A O` as code `O` labelled
  "Alcool e Outras Drogas A", the code of "Outras Drogas". The files hold the
  letters without the blanks (`AO` 312, `A` 103, `C` 11 in SIA-PS AC 2023-01;
  the DBF decoder trims only the ends).

**Decision.**
- **Measured values are curated inline with the measurement beside them**:
  `CODPAISRES` 1 Brasil (TABPAIS behind); `GESTOR_TP` 0/1 as authorisation
  recorded or not, its name and description corrected; `GESTOR_COD` 00000
  "Nenhuma regra liberada pelo gestor" (LIBGESTOR behind); `CNPJ_MAN` zeros
  "Sem mantenedora (estabelecimento individual)"; `CNPJ_CC` zeros "Sem cessão
  de crédito"; `TP_PREST` 99 "Não preenchido" (TIPOPRES behind; NAT_JUR
  carries the legal nature since).
- **`KOTELCHUCK` keeps both claims:** the layout's inline 1–6 first, the kit's
  table behind it, so 9 reads the kit's "Não Classificados (campos 33 ou 34,
  Nulo ou Ign)". The conflict is written beside the field.
- **A national table goes behind a system's copy** when the column is that
  classification: `PA_TPUPS` → `TP_ESTAB`, `TP_UNID`; `PA_REGCT` →
  `REGRA_C`, `PA_REGCT`, `REGRAS`.
- **Positional CNV codes.** When a file's expression column cannot be
  inferred and every line ends in a comma at one column after a width-w field
  with blanks inside, the code is that field without its blanks
  (`cnv_parser._positional_column`). Over the 4,474 kit CNVs under `sources/`,
  only `TP_DROGA.CNV` parses differently (3 → 7 codes, the collision gone).
  The SIA kits were re-ingested and the pack rebuilt.

**Result.** Undecoded columns 32 → 21, cells 134,293 → 48,763 on the fresh-home sweep; see EVALUATION, 2026-09-29, "Measured sentinels and national
fallbacks".
