# ADR-0216: The compendium is the one map of what pegasus_data holds and can do; search reads it; an open question is one a person must answer

2026-11-08. Status: active. Amends ADR-0075 (the compendium as the researcher's map); advances ARCHITECTURE §5 "describe a thing".

## Context

The author's agents kept missing variables and data. Measured on the home (evaluation 2026-11-08-the-one-map):

- **DATASUS only.** `compendium()` mapped what the FTP's file headers declare. It did not cover:
  - 24 datasets (all of SISAGUA, SRAG, yellow fever, SNGPC, INEP, ANS), which showed zero columns;
  - the 122 context fields (GDP, climate, CNES supply, water);
  - roles, event types, links, aggregates and SIDRA's 9,336 tables;
  - the functions and commands that use them.
- **Wrong about labels.** It reported 1,489 coded columns as having no codelist. A query labels them anyway, from the binding
  stored per schema family (`label_bindings`, ADR-0072): SIH `COBRANCA` renders "Alta melhorado".
- **Search saw two tables.** It read `variable_docs` and `dataset_docs` only, and did not say how to get what it found.
  `search voos` found nothing; `search precipitação` found a suicide code.
- **Open questions were mostly noise.** 733 were open:
  - **676 from a width check.** A reference table holding several code widths was called a vintage hazard. A label is
    joined on the code's exact string (`lookups`: `Mapping[str, str]`), so one width can never take another's meaning.
  - **49 from a prefix check.** A prefix whose files appeared in a second tree was called a reorganisation. 47 were
    republication: SINAN series in `SINAN/DADOS` and `Dados_Abertos`, and documentation tables in both the SIM and the
    SINASC kits. One (CM) was a true collision that the path already decides. One (POP) names two series.
  - **Answered but never closed.** COD_IDADE's units, COMPLEX, FAECAIHS, V2, V6, V8 and V9 had all been answered, and
    `build.py` re-opened V8 on every population run.

## Decision

1. **The compendium is the one map.** It is built from the catalog, the lake, the curation and the code. It describes:
   - **every dataset `query()` serves:** FTP and intake alike;
   - **every column with:**
     - its meaning;
     - the codelists a query labels it with (`dataset_variables.codelists`, from `label_bindings`, oldest family first);
     - its fill (the non-null share of the rows held, from the lake's Parquet statistics; NULL when nothing is held);
   - **what the install holds:** rows per dataset, year and state, read by the lake's own layout, so intake data counts;
   - **the context fields** (`fields`), **roles and event types**, **links** with their stored runs, **aggregates** and
     **SIDRA's tables**;
   - **operations:** every public function and command, with its help, read from `__init__` and the CLI.

   Each section is read through the loader the package itself uses, so the map says what a call would find.
2. **One index, with the call.** `entries` holds one row per thing a reader can look up, with `how`: the call that gets
   it (`query("SIH.RD", select=["COBRANCA"])`, `load_field("gdp")`, `pegasus-data link sih_deaths_to_sim`).
   - **The home keeps its own map** (`_catalog/compendium.sqlite`, `_compendium.current`). It is rebuilt when the
     catalog, the curation, a lake partition folder, a field, a link, the SIDRA registry or the module change. A rebuild
     takes about 20 s.
   - **`search()` reads `entries`,** and the label pack for codes. Every word of a query must begin a word of an entry.
3. **An open question is one a person must answer.**
   - **The width check is removed** (`persist.reference.flag_mixed_width_tables`).
   - **The prefix check asks only when the prior system's files are gone.** A reorganisation moves files. A prefix whose
     established system keeps them is shared (`inventory.systems._still_holds`).
   - **V8 is closed,** not re-noted (`build.py`).
   - **All 733 are resolved in the home catalog,** each with its evidence. The CM files were refiled by re-running the
     inventory: 47 under SIHSUS.

## Consequences

- **Questions that stay open.** Unresolved matters live in `OPEN_QUESTIONS.md`. The catalog's table holds only what a
  run cannot settle by itself.
- **The packaged seed** carried the 733 questions to every fresh install. It is rebuilt from the cleaned catalog
  (`scripts/build_resources.py`).
- **Still separate.** `info`, `describe`, `explore` and `availability` keep their own readers of the catalog. Folding them
  onto the map is the remainder of ARCHITECTURE §5's row.
