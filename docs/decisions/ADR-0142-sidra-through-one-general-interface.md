## ADR-0142: SIDRA is read through one general interface: a metadata registry, a planner under the measured limits, and a long fact store

**Date:** 2026-10-05. **Status:** active. **Part of:** ADR-0127 (context fields), ADR-0055 (denominators).
**Replaces:** `sources/census.py`'s SIDRA client and `fields.py`'s own URL builder. **Request:** the author's
SIDRA specification and compendium (`docs/history`, `PegaSUS/config/registries/sidra`).

**Context.**
- **Two narrow clients, each with its own URL building, retries and symbol reading.** `sources/census.py` knew
  three population tables; `fields.py` knew fifteen fields. Neither could say what else SIDRA holds or whether a
  request was legal before sending it.
- **The author's earlier attempts** (read 2026-10-05) discovered tables well and fetched values badly:
  - an R engine scraped `desctabapi.aspx` for table numbers 1 to 10,000, which breaks with the page layout and
    returns no values;
  - `miniPegaSUS/sidra_core.py` (2,115 lines) and `PegaSUS/sidra/` (4,500 lines) planned and parsed, but took a
    hand-picked table list as truth, found the limits late (a 200-locality cap added after HTTP 599) and set a
    ceiling of 49,900 values by estimate;
  - none stored the answers as one set of observations with their provenance.
- **IBGE's API is complete enough to need no scraping** (measured 2026-10-05, `sidra/client.py`):
  - `/agregados` lists 9,336 tables of 70 researches; `?nivel=N6` selects 4,448 and `?nivel=N3` 6,269;
  - `/metadados` gives a table's variables, units, classifications, categories, periodicity and levels (median
    5 KB, 0.7 s);
  - **category ids are global**: a (classification, category) pair has one name in every table scanned;
  - **`N6` is not "all municipalities"**: PNS, PeNSE and PNAD Contínua publish the 27 capitals at N6, so the count
    behind the level (`/localidades/N6`) is part of a table's reach;
  - **68 of 3,105 classifications list no Total**, yet a request that leaves them out is answered with category
    0 and an empty name (table 307);
  - a selector names several states (`N6[N3[11,12]]`); two selectors joined by `|` fail with HTTP 500;
  - **one request costs about 8 seconds at 41,000 values** (7,900 values a second on table 9606).

**Decision.** All SIDRA access is `pegasus_data.sidra`; `sidra/client.py` is the only code that sends a request.
1. **A registry from IBGE's own metadata**, not a list: `registry.sqlite` under `<root>/registries/sidra/`, rebuilt
   from the cached responses. The author's compendium (97 tables, tiers, kept variables and kinds) is an overlay
   in `curation/sidra/compendium.yml`; where IBGE's metadata disagrees, IBGE wins and `sidra check` says so.
2. **A planner** (`sidra/planner.py`) turns a selection into requests, checked against the registry first: at most
   48,000 values (localities × variables × periods × the categories chosen of each classification; a classification
   left out is fixed at its Total and costs nothing), explicit ID lists under 3,500 characters, URLs under 6,000.
   States are named by selector and packed; cuts go to the widest dimension and fill each request. A request the
   server still refuses with HTTP 500 is halved and retried, and counted.
3. **A long fact store**: one row per observation, `table/variable/period/level/locality/c<classification>` with the
   category id, `value_raw`, `value`, `status`. One Parquet part per request under `<lake>/sidra/facts/table=<id>/`;
   a table's parts share a schema. Classifications are columns, not a JSON tuple: a table's set is fixed, and a
   column filters, joins and compresses where a tuple does not. Labels, units, kind and Total flags are joined from
   the registry at read time and never stored.
4. **IBGE's marks are a status, never a value**: `-` is a true zero; `..`, `...` and `X` are null with their reason;
   anything else is `unknown_symbol` with its raw text. The raw cell is always kept.
5. **Provenance**: every response is kept as received (URL, bytes, SHA-256, time); each part's footer carries the
   same and the registry's metadata hash. The same observation fetched twice is kept once, the latest.
6. **Series across vintages are declared, not guessed**: `curation/sidra/series.yml` and `axes.yml` name the sources
   and say what their category ids mean in a common vocabulary (sex is 4/5 in one table and 92956/92957 in
   another). Where sources overlap both claims are kept and one is `selected`. Each map entry is checked against
   IBGE's category name, and each source's cells against the table's own Total.
7. **Municipal lineage by comparable area** (`sidra/lineage.py`): counts are rolled up to IPEA's minimum comparable
   areas; a sum with a missing part is missing; a mean or rate is refused.
8. **It feeds PegaSUS through the existing doors**: `fields.yml` entries are read through the interface
   (`load_field` unchanged); the Census series `CENSO` is the projection of the series `population_age_sex`;
   `Sidra` is exported for the rest.
9. **Nothing is fetched implicitly**; `pegasus-data sidra curated` prices the compendium before fetching it.

**Evidence.** EVALUATION 2026-10-05 "SIDRA general interface". The fifteen SIDRA fields rebuilt through the
interface equal the previous implementation's output in all 83 partitions. The three censuses (tables 1552, 1378,
9514) equal the previous `CENSO` files cell for cell, and each municipality's cells add up to the table's own Total
(0 mismatches in 5,507, 5,565 and 5,570 municipalities). A request of 51,180 values, the size documented to fail,
was refused, halved and returned all its rows.

**Alternatives.**
- *Wide tables (one column per category).* Rejected by the author's own specification and by measurement: categories
  shift between vintages and one table has up to 2,412 cells per locality.
- *`view=flat`.* Repeats every name on every row and carries a header row that looks like data; the default JSON
  states the category ids once per result.
- *An R/Python wrapper (`sidrar`, `sidrapy`).* No planner under the measured limits, no provenance, no status.
- *The catalog SQLite.* Its schema is changing under other work, and the registry is derived and rebuildable.

**Consequences.**
- `sources/census.py` is removed (2026-10-05): the interface had nothing to add to it and its values were reproduced cell for cell;
  `build.py` already calls `sidra.population.build_census`.
- A change to the planner changes request URLs, so a re-run after it fetches again; stored facts stay valid.
- The cache holds each response as received: about 4 KB (gzip) per thousand values; the facts take about 2 MB per million rows.

**Would overturn it.** IBGE publishing the tables in bulk (files) or changing the limits; or a table family whose
answers do not fit one value per category combination.
