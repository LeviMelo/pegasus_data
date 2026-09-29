## 2026-08-30 — The serve path met its first national artifact

*Split from docs/history/FINDINGS.md §3t on 2026-09-28; text unchanged.*

## 3t. The serve path met its first national artifact (2026-08-30)

Third instance of the same lesson (3q, 3s, now this): **correct at fixture size
is not a property of the code.** The serve path had been verified exhaustively
at 2,417 cells. The first national artifact has 422,203.

### Measured

Every HTTP roll-up cost 2.8–4.4 s — including a ONE-ROW national total. The
floor was not Arrow and not the network: `aggregate()` began with
`{c: table.column(c).to_pylist()}` and ran Python loops for the mask, the
pushforward application, the unmapped-mass scan and the index build — ~3.8
million Python objects per request. On top of it, the HTTP handler consulted
`capabilities()` on every cell request, and the projection re-read the parquet
and the catalog each time (~1.2 s), putting a constant floor under even cached
answers.

### The fix, and what stayed in Python

Arrow end to end: `is_in` masks, pushforwards applied with `index_in` + `take`
over a mapping decided in Python on the DISTINCT codes only (a few thousand
lookups — where `uf_from_code` and `memberships` own the rule), lost mass via
`sum(filter(...))`, vectorised finalize mirroring `Kind.finalize`'s 0/0-is-null
semantics, Arrow sort. Three caches keyed on on-disk identity (mtime): the
artifact table, the classification map, the finished Capability. orjson on the
wire for the megabyte payloads.

| request | before | after (warm) |
|---|---|---|
| national total (1 row) | 2,674–3,304 ms | **181 ms** |
| uf × year | 2,853 | 255 |
| municipality × year (569 KB) | 3,082 | 539 |
| municipality × month (3.8 MB) | 4,400 | ~1,470 |
| health_region × year | 2,755 | ~250 |
| capabilities | 1,211 | 96 |

All 81 serve/capability tests passed **unchanged** across the rewrite, and the
national invariants held: total = 12,520,914 = sum of sex parts; mean LOS
5.210395 = sum/n to the last digit.

### The boundary that keeps this honest

The RULES stayed in Python where their owners live; only the APPLICATION moved
to Arrow. A pushforward is still `memberships()`'s answer — computed once per
distinct code, not re-derived in compute kernels. The columnar finalize is tied
to the scalar one by `test_formula_matches_finalize`, the same test that ties
the wire formula: one projection, three spellings, one test holding them
together.

The frontend had the same defect in miniature: the time surface rebuilt each
territory's series by rescanning all cells — 5,570 × 66,832 ≈ 370M operations
per render — and drew 5,570 overlapping polylines where ~300 are a solid band.
One pass now, and a sample taken evenly across the by-total ordering so the
band keeps its true spread; the legend states the sampling.
