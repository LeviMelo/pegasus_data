## 2026-08-30 — The build spent an hour labelling nothing

*Split from docs/history/FINDINGS.md §3u on 2026-09-28; text unchanged.*

## 3u. The build spent an hour labelling nothing (2026-08-30)

The national SIH build took 65 minutes for 12.5 million rows, and the question
was where the hour went. Not where anyone would look first: not the network
(the lake was warm), not the DBC decode (native, already parallel across
files), not the aggregation (columnar since 3o). Profiled on one state-year,
**205 of a 209-second fetch was codelist selection whose result was then
discarded** — `fetch(labels=False)` still ran every column of every file
through `_select_codelists`, which reads packed reference tables, queries the
relations catalog and parses YAML, so that the `codes` profile could then emit
the column exactly as filed.

Four layers, four fixes, each measured before the next:

| layer | defect | fix |
|---|---|---|
| `_render_table` | selection runs when every column renders as its code | `codes_only` gate: emit as filed, skip selection |
| `relations.load_relations` | joins.yml re-parsed per call (1,359 parses, 84 s) | parse cached by CONTENT, not mtime |
| `labelpack._read_packed` | cache keyed by vintage, so 12 competencias = 12 expansions of the same rows | scan, runs and expansion cached by what is actually read/expanded |
| `view._lookup_map` / `_contradictions` | dict rebuilt from the packed table per call | `lru_cache`, returns treated as read-only |

Numbers, same machine, warm lake: `labels=False` one state-year 233.7 s →
44.8 s; `labels=True` 218 s → 46.7 s; the national build 65 min → **12.9
minutes**, byte-identical artifact, and the warning spam (a labelling warning
per file for a fetch that asked for no labels) gone with the work that
produced it.

Three of the lessons are old ones wearing new clothes. *Work whose result is
discarded is still work* — the serve path's finalize-then-refuse (3q), the
frontend's 370M-operation render (3t), and now selection under `codes`. *A
cache key must carry exactly what the answer depends on* — no more (the
vintage key that split identical expansions twelve ways), and no less. The
mtime variant of "no less" is worth naming: **Windows advances mtime on a
~16 ms timer tick**, so two writes in quick succession can share one, and a
mtime-keyed cache serves the first write's parse for the second's content.
joins.yml is now keyed by its text.

The fourth lesson is new. A process-lifetime cache is a claim that the world
underneath it stands still, and `lake/reference/` does not: the reference
stage, first-use materialisation inside `fetch`, and a bundle unpacked
mid-process all rewrite it. The bundle round-trip test caught exactly this —
labels cached from the shipped pack kept answering after the bundle landed.
Invalidation lives at the mutation site (`write_reference_tables` calls
`view.clear_lookup_caches`), not scattered across callers; and
`labelpack.clear_caches` clears the WHOLE derivation chain, because clearing
one layer of a cache stack leaves the layers beneath it serving the old
world.

What remains of the 12.9 minutes is the honest floor for this design: native
DBC decompression and DBF parsing of 12.5 million rows, four files at a time.
The next lever, if rebuild time ever matters again, is a decoded-blob cache
keyed by content digest — the lake is already content-addressed, so decode
would happen once per blob ever, and a rebuild would be a parquet read. Not
built now: rebuilds at 13 minutes are no longer where development time goes.
