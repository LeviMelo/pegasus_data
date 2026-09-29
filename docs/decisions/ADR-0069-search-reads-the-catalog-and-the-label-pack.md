## ADR-0069: `search()` reads the catalog and the label pack; no dictionary build is needed

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0028 (the
dictionary is one SQLite database).

**Context.** `search()` answered from `docs/dictionary.sqlite`, a 557 MB
database written by `pegasus-data dictionary` from a maintainer catalog.
- On a fresh install it raised `FileNotFoundError` (live run 2026-09-28).
- The CLI's `search` looked only in `./docs/`.
- Everything it indexes already ships: variable and dataset documentation is
  in the catalog (the seed, ADR-0067), and every code label is in
  `resources/labels.parquet`.

**Decision.**
- `search()` (`_search.py`) reads the catalog's `variable_docs` and
  `dataset_docs` and the shipped label pack (through DuckDB).
- Case and diacritics are folded on both sides, and a match must begin a word
  (live: "raça" matched `DURACAO` before this rule).
- Ranking is stated: exact name, then name, then prose; for codes, exact
  label, then prefix, then word match, shorter first.
- `kind=` narrows to `variable`, `dataset` or `code`; `system=` to one
  system. The CLI `search` calls the same function.
- `docsgen.search` is deleted. `docsgen.search_docs` and `read_page` remain
  for the dictionary database, whose future is M3's (ARCHITECTURE §5).

**Measured** (fresh home, `seed-1`):
- "raça" returns 25 hits in 0.13 s: `RACCOR`, `CS_RACA`, `RACACOR` and so on.
- "Parda", codes only, 0.80 s: `CORRACA = 03`, `CS_RACA = 4`, SIHSUS
  `RACACOR = 03`.
- "infarto agudo" returns CID10 I21, I214, I219 in 0.09 s.

**What would reverse it.** A query mix where scanning 3.65M labels per call
is too slow. An index can be built in the data home then, on first use.
