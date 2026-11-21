## ADR-0223: every curation file has a declared shape, checked when it is parsed

**Date:** 2026-11-21. **Status:** active. **Request:** the architecture review of 2026-11-21.

**Context.** `curation/` (338 YAML files, about 241,000 lines) is read as raw mappings: about 1,500 `.get("key")`
calls, no schema. Only `column_roles` refused an unknown key. Elsewhere a misspelt key was ignored and a default
applied: `status` defaulted to active and `confidence` to high in the ontology, a link's `shift_days` to 7, an
aggregate's `dimensions` to none. `products.yml` had no loader and was read inline in eight places. Name-guessed
declarations had been found wrong about fifteen times; none of that was catchable at load.

**Decision.**
1. Each kind of file has one schema, as data, in `semantics/schema.py`: a mapping with a fixed vocabulary of keys,
   a mapping with free keys, a list, an enum, or an unchecked subtree. No dependency was added: the language is 60
   lines and the files' shapes are simple.
2. `curation._parsed_yaml`, the one parse point, checks a file against its kind once per version of the file and of the
   schema. An unknown key, a missing required key or a value outside an enum is refused, with the file, the path and the
   closest allowed key; every violation of a file is listed. A file that matches no kind is refused: a new file
   declares its kind.
3. The roles schema is `column_roles.KEYS` itself, not a copy.
4. Call sites keep reading mappings. The schema guarantees the spelling they rely on; it does not replace the typed
   loaders (`ColumnRole`, `EventType`, `VariableDoc`, `AggregateSpec`), which keep their cross-field rules.
5. `products.yml` is read through `curation.products()` / `product(name)`; SIDRA's three files through `read_yaml`.

**Evidence** (evaluation 2026-11-21-architecture-review). 338 files pass. The schemas were derived from the keys the
files hold and the keys the code reads; the comparison found one real defect: twenty column descriptions of
`intake.yml` (SIES, S2iD, ANS, INEP, SI-PNI doses) were unquoted and held a comma, so YAML cut each at the comma and
read the rest as stray keys; they are quoted. Five typos planted in a copy (`precison`, `staus`, `shift_dayz`,
`dimensons`, `grian`) are each refused by name. Cold, checking adds 0.08 s to 3.7 s of parsing; warm, nothing.

**Consequences.** A new key is added to the schema with the code that reads it. Free-form subtrees (labels by code, a
source's origin block, a product's inputs) are not checked below their root.
