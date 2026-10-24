# Universe or sample: what each SIDRA table rests on (2026-10-24)

**Check.** `sidra/notes.basis` (ADR-0206) over the registry (`pegasus_core_data/registries/sidra/registry.sqlite`, 9,336
tables), `Sidra().describe`, `labelled` and `build_series` on stored facts. What was counted and why: which tables get a
basis and from what (a basis the library cannot support must say `unknown`); whether a declaration and the precision rule
ever disagree (a table both "Dados do Universo" and publishing CVs would mean one of the two readings is wrong); and the
three tables the diabetes study named, against their notes. Regime: worktree branch `sidra-notes` from f971574, the real
data home read only, 2026-10-24; notes read in the in-app browser (73 Census tables, then the compendium's 26 others).

**Reaching the notes.** `desctabapi.aspx?c=10061` answers 403 with Cloudflare's "Just a moment..." page to httpx with the
browser User-Agent, with browser headers, with the system TLS context, and to `curl` with its own agent; `curl` with a
browser agent and a browser get 200. `sidra.ibge.gov.br/tabela/10061` answers 200 but carries no note: its script
(`editor-layout.js`, `descritorTabela.Notas`) loads them from `/Ajax/JSon/Tabela/1/<t>`, which is 403 as well. The API of
aggregates has no notes (`/metadados` keys: id, nome, URL, pesquisa, assunto, periodicidade, nivelTerritorial, variaveis,
classificacoes).

| basis / from | tables |
|---|---|
| sample, by precision variables | 4,103 (PNS 2,222, PNAD Contínua annual 1,075, PeNSE 367, PNAD 174, ...) |
| sample, declared | 38 |
| universe, declared | 32 |
| mixed by period, declared | 3 (200, 202, 206) |
| unknown | 5,160 (26 of them declared after reading a note that states no basis) |

* **Census.** 82 of 1,388 Census tables have a basis. The 2022 sample tables say "Dados dos Resultados preliminares da
  amostra, estimados a partir de áreas de ponderação preliminares" (10061, 10062, 10075-10077, 10141, 10142, 10280-10381,
  9517, 9931-9936); the 2022 universe tables "Dados do Universo"; 2010's sample tables "Dados (dos Resultados Gerais) da
  Amostra".
* **By period.** Table 200 is universe for 1991 and sample for 1970, 1980, 2000 and 2010; 202 sample for 1970 and 1980,
  universe for 1991-2010; 206 universe for 1991 only; 616 sample throughout.
* **No contradiction**: no table declared universe (whole or for a period) publishes a CV or a confidence interval.
* **The study's tables.** 10061: sample (3,743,040 stored facts carry `basis` sample); 9606: universe (11,408,244 facts,
  2010 and 2022); 9952: universe; the PNS diabetes tables 4487-4491: sample by their confidence-interval variables.
* **Series.** `population_total`: census_2010_2022 universe (2010, 2022), census_1970_2010 universe for 1991-2010 and
  sample for 1970 and 1980 (table 202's note), the yearly estimates unknown (table 6579's note states no basis).
