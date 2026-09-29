## 2026-08-18 — V9: DEMAS endpoint granularity

*Split from docs/history/FINDINGS.md §1 V9 on 2026-09-28; text unchanged.*

### V9 — DEMAS endpoint granularity · **resolved**

Live spec: Swagger 2.0, `DEMAS - API de Dados Abertos`, **version 1.8.32**, **87 paths**. Every
endpoint the brief names still resolves, including both Previne Brasil ones.

`/daf/estoque-medicamentos-bnafar-horus` parameters: `codigo_uf`, `codigo_municipio`,
`codigo_cnes`, `anomes_posicao_estoque`, `data_posicao_estoque`, `codigo_catmat`,
`sigla_programa_saude`, `tipo_produto`, `sigla_sistema_origem`, `limit`, `offset`.

So the answer to the brief's three sub-questions is: **municipal — yes, and finer (per
establishment); monthly — yes (`anomes_posicao_estoque`); medication identity — yes, via
`codigo_catmat`.**
