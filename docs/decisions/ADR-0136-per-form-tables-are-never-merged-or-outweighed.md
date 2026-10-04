## ADR-0136: Per-form tables are never merged by the bridge, cached as curated, or outweighed by measurement

**Date:** 2026-10-03. **Status:** active. **Amends:** ADR-0080, ADR-0082.

**Context.** A fresh-home sweep of every SINAN form for 2023 (evaluation 2026-10-03 SINAN form dictionaries) left AIDA `CRITERIO` undecoded on all 41,493 rows. Three defects stacked:
- **The bridge merged alternatives.** `relations_for` exposes each curated `variable_docs.codelist` as a reviewed `label_of`, and for a `per_form` field that column holds the alternatives joined. So rung 4 served `CONFDESC,CONFDESCA,…` as one artifact for CLASSI_FIN, CRITERIO and EVOLUCAO of every form that reached it. Merging is the ADR-0080 defect; it showed as "undecoded" only because the joined name resolves to no table.
- **Curated decisions were cached.** 2,309 stored `label_bindings` rows with basis `curated` shipped in the seed, 65 of them that bridge result. A stored copy outlives the curation it came from.
- **Measurement picked another form's table.** Once the bridge was gone, weighing chose the children's `CRITAIDSC` for the adult form ("300 SINAIS MAIORES E MENORES" where the adult dictionary says Rio de Janeiro/Caracas). The two tables share codes, and measurement cannot tell them apart.

**Decision.**
1. **The bridge skips per-form fields.** Only `variable_docs` rows with `per_form = 0` are exposed as `label_of`.
2. **Curated decisions are never cached.** `stored()` reuses a decision only when it was measured; curated ones are re-derived on every call.
3. **A partial form table still outranks measurement.** The form's own dictionary, when it decodes at least half the rows (`TOO_WEAK`), is taken before the stored decision and weighing. The codes it lacks stay visibly undecoded. The 95% rung keeps its place above the hand codelist.

**Evidence**, fresh home, 2023:
- AIDA `CRITERIO`: CDC adaptado (100) 19,045, Rio de Janeiro/Caracas (300) 2,130, Critério óbito (600) 544. The 101, 601 and 902 that no source defines stay "(?)".
- AIDA `EVOLUCAO`: Vivo 18,310, Óbito por Aids 2,734.
- CHAG `CLASSI_FIN`: Descartado 4,817. DCRJ `EVOLUCAO`: Vivo 53.
- MENI `CLASSI_FIN` is unchanged: confirmado 16,649, with the undocumented 8 still "(?)".
