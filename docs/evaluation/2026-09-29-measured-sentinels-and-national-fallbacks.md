# Measured sentinels and national fallbacks: undecoded columns 52 → 21, cells 560,585 → 48,763

**Date:** 2026-09-29. **Regime:** commit after 0e1cea6 (ADR-0105, ADR-0106),
new data home `~/pegasus_fresh`, live FTP; label pack rebuilt after
`semantics -s SIASUS` on the maintainer home.

**What was run.** `scripts/sweep_undecoded.py` (one small slice per dataset,
the user's `query` path) three times: before ADR-0105, after its curation and
the fallback fix, and after ADR-0106's curation, CNV parser fix and pack
rebuild. Each column with a label companion is counted for rows whose value
reads `code (?)`.

**Why this count.** "Every code translatable" is measured as values a person
sees undecoded; a label that decodes a value wrongly would not show here, so
each new label was also read against the measurement that justifies it
(ADR-0105, ADR-0106 tables).

**Counted.**

| run | columns with undecoded values | undecoded cells |
|---|---|---|
| before (`sweep_undecoded-fresh2.json`) | 52 | 560,585 |
| after ADR-0105 (`sweep_2026-09-29_after_adr0106.json`, taken before ADR-0106's changes) | 32 | 134,293 |
| after ADR-0106 (`sweep_2026-09-29_after_adr0106b.json`) | 21 | 48,763 |

- Label pack: 2,355 codelists before and after, 0 code keys lost; `TP_DROGA`
  3 → 7 codes; 0 labels still begin with a TabWin order mark.
- Rendered checks: SINASC AC 2022 `CODPAISRES` "Brasil (1)" 14,482;
  `KOTELCHUCK` "Não Classificados (campos 33 ou 34, Nulo ou Ign) (9)" 2,238.
  SIH-RD AC 2023-01 `GESTOR_TP` 3,994 / 171, `GESTOR_COD` "Nenhuma regra
  liberada pelo gestor" 4,137. CNES-ST AC 2023-01 `CNPJ_MAN` "Sem mantenedora
  (estabelecimento individual)" 735; `TP_PREST` "Não preenchido (99)" 1,278,
  2012 still "PUBLICO MUNICIPAL (50)" etc. SIA-PA AC 2023-01 `PA_REGCT` 7114
  named (835), `PA_TPUPS` "Centro de imunização (85)" 151.

**Findings.**
- Four columns became undecoded between runs 1 and 2: all-zero `CNPJ_MAN` and
  `CNPJ_CC`, which ADR-0100's typed registry no longer treats as CNPJs. Now
  labelled from measurement.
- What remains is OQ-61. The largest is SIH-SP `SERV_CLA` `000000` (45,511 of
  46,933 rows), unlabelled for want of a source.

**Artifacts:** the three sweep JSONs under `data/probes/live/`; the pack before
the rebuild at `data/probes/labels_before_adr0106.parquet`.
