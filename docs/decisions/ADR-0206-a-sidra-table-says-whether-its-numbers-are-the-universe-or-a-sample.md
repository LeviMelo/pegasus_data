# ADR-0206: A SIDRA table says whether its numbers are the universe or a sample

2026-10-24. Status: active. Builds on ADR-0142 (the SIDRA interface).

## Context

A cell of a SIDRA table carries no mark of what it rests on. Table 10061 (adults by schooling × age × sex × colour, 2022)
is "Dados dos Resultados preliminares da amostra, estimados a partir de áreas de ponderação preliminares"; 9606 and 9952 are
"Dados do Universo". Read as counts, sample estimates enter a model as exact denominators. The diabetes prevalence study
found it (its PEGASUS_ISSUES item 1). The registry stored IBGE's variables, classifications and categories, not the notes,
and the API of aggregates (`/agregados/<t>/metadados`) has no notes to store.

The notes are served by `apisidra.ibge.gov.br/desctabapi.aspx?c=<t>` and by the table page's own JSON
(`sidra.ibge.gov.br/Ajax/JSon/Tabela/1/<t>`, its `Notas`). Both sit behind a Cloudflare challenge ("Just a moment...", 403)
for a non-browser client: the transport (httpx, browser User-Agent, any headers or TLS context) and `curl` with its own
agent are refused; the table page itself (`sidra.ibge.gov.br/tabela/<t>`) answers but loads its notes from that JSON.

## Decision

1. **The library does not disguise itself to pass a bot check.** It does not read notes by impersonating a browser's
   TLS handshake or by shelling out to a client the filter happens to admit.
2. **What a table rests on is `basis`** (`sidra/notes.py`): `universe`, `sample`, `mixed` (the note gives each census its
   own; `by_period` says which, and a row takes its period's) or `unknown`, from, in order:
   * a **declaration** in `curation/sidra/notes.yml`: IBGE's passage verbatim (`evidence`), the day it was read in a
     browser and the table's own "última atualização";
   * the table's **precision variables**: a table publishing a coefficient of variation or a confidence interval is a
     sample estimate (IBGE gives precision only for estimates);
   * otherwise **unknown**, with the reason, never taken for a count. A note read and found silent is declared
     `unknown` with `why`.
3. **Where it shows:** `Sidra().describe` and `pegasus-data sidra show` (the `basis` entry), `Sidra().labelled` (a `basis`
   column per fact and `pegasus.basis` in the schema metadata) and `build_series` (a `basis` column per row, by the
   source's period).

## Evidence

Evaluation 2026-10-24-sidra-basis: 99 tables declared from their notes (the compendium's 97 and the diabetes study's
9952 and 10061; 32 universe, 38 sample, 3 by period, 26 whose note states no basis); 4,103 of the registry's 9,336 tables
are sample estimates by their variables; no declared-universe table publishes precision; 10061 is sample, 9606 and 9952
universe; the stitched `population_total` is universe for 1991-2022 and, from table 202, sample for 1970 and 1980.

## Consequences

* 5,160 tables, 1,306 of them the Census's, stay `unknown` until their note is read and declared; a study declares the
  tables it uses (one entry each).
* A note IBGE revises is not followed automatically: `updated` records the version read.
