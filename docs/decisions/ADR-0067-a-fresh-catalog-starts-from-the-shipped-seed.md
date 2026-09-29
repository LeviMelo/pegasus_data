## ADR-0067: A fresh catalog starts from the shipped seed

**Date:** 2026-09-28. **Status:** active. **Supersedes:** ADR-0029 (the
crawled map ships as `tree.parquet`). **Amends:** ADR-0046 (resource tiers).

**Context.** On a fresh install (live runs 2026-09-28):
- `info()` failed with a raw `sqlite3.OperationalError`, and `search()` failed
  too. Both need catalog tables that only a maintainer's build has.
- `explore()` worked, but only because it had its own reader for a shipped
  `tree.parquet`. The query planner had a second reader for the same file.
- `fetch()` had its own bootstrap (`seed_bindings` from `bindings.parquet`,
  plus curation), and `translate()` a fourth.
- `families.parquet` and `schema_presence.parquet` shipped and were read by
  nothing.
- A first request for a system the catalog had not seen ran a targeted crawl
  plus a header census of every stratum it touched: 339 s for one SIA
  state-month.

The maintainer catalog refresh (evaluation 2026-09-28) measured the costs.
Listing the whole tree takes 32 s. Learning its schemas takes about 0.27 s
per stratum over 2,569 strata. The expensive knowledge is the same for
everyone.

**Decision.**
- The package ships `resources/catalog_seed.sqlite.gz`: the maintainer
  catalog's knowledge of the tree and its meaning (`catalog/seed.py`,
  `SEED_TABLES`). That covers files, file facts, strata, schemas, families,
  schema presence, bindings, curated variable and dataset docs, open
  questions, representations and crawl runs. It carries no local state:
  blobs, fetches, lake partitions, adjudications and events stay out.
- `Catalog.__init__` installs the seed when the catalog file does not exist,
  atomically (write beside, rename). Every entry point opens the catalog
  through that class, so every door starts from the same knowledge.
  `PEGASUS_SEED=0` disables it; the test suite sets it.
- Its schema is created by `Catalog` itself at export, so it is always the
  current `schema.sql`.
- One reader of the map: `explore()` and the planner read the catalog.
  `tree_snapshot`, `explore(source="packaged")`, the planner's `tree.parquet`
  branch, `labelpack.seed_bindings`/`build_binding_pack`, and `translate()`'s
  own bootstrap are deleted. So are `tree.parquet`, `families.parquet`,
  `schema_presence.parquet` and `bindings.parquet`.
- A catalog opened read-only where none exists and no seed ships raises a
  `FileNotFoundError` that names how to create one, instead of sqlite's
  "unable to open database file".
- The seed is built by `scripts/build_resources.py` from a current
  maintainer catalog (`crawl`, `inventory`, `schemas`, `families`, `curate`;
  RUNBOOK §5). The resource budget rises from 45 to 64 MiB for it (18.8 MB).

**Measured after** (`seed-1`, fresh home):

| | before | after |
|---|---|---|
| `info()` | crashed | 0.48 s |
| `info("SIH.RD")` | crashed | 0.10 s |
| `explore()` | 2.0 s, shipped snapshot | 1.2 s, the catalog |
| `query("SIA-PA", "2023-01", "AC")` | 339 s, 6 labelled columns | 35.5 s, 33 labelled columns |

**Cost.** 18.8 MB more in the wheel. 161 MB in the data home on first use,
and a few seconds to decompress. A seed goes stale as DATASUS publishes, and
`crawl` (half a minute) reconciles it like any catalog.

**Alternatives.**
- *Each door falls back to its own shipped file.* That was the state being
  replaced: four readers, two unused files, and a door (`info()`) with no
  fallback at all.
- *Crawl and census on first use.* Listing is cheap, but the census is
  twelve minutes for the tree.

**What would reverse it.** A seed that goes stale faster than releases ship,
so that users hit publications it does not know more often than the targeted
discovery handles.
