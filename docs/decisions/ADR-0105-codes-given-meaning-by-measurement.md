## ADR-0105: Undocumented codes are given a meaning when the data proves it, inline codes keep their fallback, and TabWin's order marks leave labels

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0079, ADR-0102.

**Context.**
- **Codes no document defines.** After ADR-0099/0103 the sweep's undecoded
  values were codes the layouts name without a table, or omit: SIH's `TPDISEC1–9`
  value 0, `SP_DES_HOS`/`SP_DES_PAC`/`SP_U_AIH`, SIA's `PA_UFDIF`/`PA_MNDIF` value
  9, `PA_TIPPRE` value 00, and `PA_CODOCO`, whose kit table `CODOCO.CNV` is keyed
  by two characters (`1K`) while the column holds one.
- **Each can be settled by another column of the same record.** A meaning is
  asserted only when it holds on every row measured, or where the exceptions are
  counted and negligible:

  | field | measured on | finding |
  |---|---|---|
  | `TPDISEC1–9` 0 | SIH-RD AC + SP 2023-01, 214,390 admissions | 0 exactly when `DIAGSEC` is `0000`; 1/2 are TP_DIAGSEC's Preexistente/Adquirido |
  | `SP_DES_HOS` | SIH-SP SP 2023-01, 3.47M rows | 1 exactly when the state of `SP_M_PAC` differs from that of `SP_M_HOSP` |
  | `SP_DES_PAC` | same | 1 when the **municipality** differs (77 exceptions). The layout gives it `SP_DES_HOS`'s name; the data says otherwise |
  | `SP_U_AIH` | same | every AIH has a row with 1; 210,105 of 210,161 exactly one ("contabiliza a AIH sem repetições", IT SIH 2016-03) |
  | `PA_UFDIF`/`PA_MNDIF` 9 | SIA-PA AC 2023-01 | 9 exactly when `PA_MUNPCN` is `999999` (21,398 of 21,398) |
  | `PA_TIPPRE` 00 | SIA-PA AC 2008, 2012, 2016, 2023 | filled with 20/40/50/61 through 2012, 00 on every row in 2016 and 2023 |
  | `PA_CODOCO` | SIA-PA AC 2023-01 | `PA_CODOCO` + `PA_FLQT` is a `CODOCO` key on 95,414 of 95,414 rows (`1K` 93,863) |

- **Inline codes dropped their fallback.** ADR-0079 says a column's inline
  `codes:` come first and a table it was also bound to stays behind them;
  `curation.py` built that chain, but `label_bindings.decide` returned the inline
  table alone. Writing `PA_UFDIF`'s measured 9 left its 0 and 1 undecoded.
- **TabWin's pick-list marks are in labels.** 98,667 rows of the label pack
  begin with a row number and indent dots: `2 .... Acrelândia`,
  `099 .. Outros transtornos do ouvido`, `..Dezembro/2017`,
  `02 ..APROVADO TOTALMENTE (K)`. They order TabWin's list; they are not the
  code's meaning.

**Decision.**
- **The measured meanings are curated inline** with the measurement in a
  comment beside them, and the kit table behind: `TPDISEC1–9` (0 Sem diagnóstico
  secundário, then `TP_DIAGSEC`), `SP_DES_HOS` (UF), `SP_DES_PAC` (município;
  its translated name and description corrected), `SP_U_AIH`, `PA_UFDIF` and
  `PA_MNDIF` (0/1 as the layout defines them, 9 Município de residência
  ignorado, then `INVASAO`), `PA_TIPPRE`/`AP_TIPPRE`/`TIPPRE` (00 Não
  preenchido, then the kit's tables), `PA_CODOCO` (`codelist: CODOCO`,
  `key: [PA_CODOCO, PA_FLQT]`).
- **Inline codes carry the curated chain.** `decide` returns the inline table
  followed by the column's other curated codelists; the first table that
  defines a code wins (`_merged_lookup`).
- **One label-prefix pattern.** `identifiers.LABEL_PREFIX` is ADR-0102's
  identifier prefix or TabWin's order mark (`NNN ..`, `....`, a number only
  when whitespace separates it from the dots, so `1..4 anos` stands). Every
  label map (`view._map_from_table`) and the pack build (`strip_label_prefix`)
  strip it. On the shipped pack it matches 100,243 labels and empties none.
- Not given a meaning, for want of evidence: SIH `GESTOR_TP`, SINASC
  `CODPAISRES` 1, `KOTELCHUCK` 9, `TPDOCRESP` 0 (neither the structure document
  nor microdatasus defines them; no pattern against other columns). They stay
  visibly undecoded (OPEN_QUESTIONS).

**Result, new home (`~/pegasus_fresh`), commit after 9679c8a.**
- SIA-PA AC 2023-01 (95,414 rows): `PA_CODOCO` "APROVADO TOTALMENTE (K)"
  93,863; `PA_UFDIF` Mesma UF 72,654 / ignorado 21,398 / UF diferente 1,362;
  `PA_TIPPRE` Não preenchido 95,414. 2012-01: `PA_TIPPRE` falls through to the
  kit ("Esfera Estadual (40)" 46,935), prefix gone from "Estabelecimento
  Privado com Fins Lucrativos… (20)".
- SIH-RD AC 2023-01: `TPDISEC1` Sem diagnóstico secundário 3,793 /
  Preexistente 355 / Adquirido 17.
- SIH-SP AC 2023-01: `SP_U_AIH` = 1 on 4,165 rows, the number of AIHs in
  SIH-RD for the same month.
- Artifact: `data/probes/live/2026-09-29-measured-codes.txt`.
