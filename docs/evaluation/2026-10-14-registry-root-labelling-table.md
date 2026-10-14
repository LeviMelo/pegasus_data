# Registries follow the root, one labelling table, one folding (2026-10-14)

Regime: branch `fix4-data` (from 09abb3b), read-only on `pegasus_core_data` (catalog, lake, registries) and on the maintainer catalog
(`mode=ro`), the default home empty, sockets trapped; the SIDRA registry on a copy. Throwaway probes; the figures are what was run.
Decision: ADR-0179.

| what | before | after |
|---|---|---|
| SIH-RD AC 2022-01 (3,977 rows), `root=pegasus_core_data`, `CNES` labels | `2001586 (?)`, 12 warnings "no reference table for 'CADGERBR'", 8.8 s | `FUNDHACRE (2001586)`, no warning, 28.2 s (692,004 registry rows read) |
| SIH-RD AC 2022 (49,547 rows) `CNES_label` nulls | 49,547 | 0 |
| rendered labels of 33 fields (SIM-DO 2012 BR 1,181,166 rows; SIH-RD; SINAN-CHIK 2015; SINAN-LEPT 2019): table used, null count, top-6 labels | | identical on 32; `CNES` the one change |
| `describe(...).reference.table` against the rendered lead table, the same 33 | equal 9, a member of the rendered chain 4, outside it 20 (maintainer catalog) | equal 32 (shipped and maintainer catalog); CHIK `CLASSI_FIN` names the form's dictionary where the render measured `CLASSI_FIN`: the catalog holds no values to weigh against (`observed_codes: 0`) |
| SIDRA registry copy (9,336 tables, 49,338 variables) | `search` lower case | re-folded on open in 3 s, `fold(old) == new` for 9,336, stable on a second fold; `rank` N6/N3 (400 each), `survey`, `infer_kind` identical; `search("pós-graduação")` 1 -> 5 tables; `vintage_families` same 31 families, key text upper case |

Not measured: the ledger's naming (no catalog held has `ledger` or `variable_profiles` rows). `build_plan` computes `labels`, `codelist`
and `hierarchical` that `emit_labels=False` never emits, but `plan_fingerprint` hashes them (ADR-0173), so it is not dead.
