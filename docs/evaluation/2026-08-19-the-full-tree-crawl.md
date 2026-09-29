## 2026-08-19 — The full-tree crawl, and what it found

*Split from docs/history/FINDINGS.md §3c on 2026-09-28; text unchanged.*

## 3c. The full-tree crawl, and what it found (2026-08-19)

### The prior inventory was missing a third of DATASUS, silently

The full crawl found **207,251 files** against the prior scan's 124,810 — **+82,441 (+66%)**, in
49 seconds across 362 directories, with size and mtime on 100% of them.

The delta decomposes almost entirely into directories the old scan never listed: 81,934 files from
53 such directories, plus 575 genuinely new ones. Of those 53, the old scan had *reported* 32 as
failures. The rest it never knew existed.

The largest is `SIASUS/200801_/Dados` at **54,199 files** — SIA outpatient production, 2008 to the
present, the biggest dataset on the tree. The old scan recorded `Dados` as a **file** under
`SIASUS/200801_`, and `uploads` as a file under the root. NLST returns bare names with no type
information, so an extensionless directory name is indistinguishable from a file; the crawl typed
both as leaves and never recursed. **No warning was emitted for either.** The inventory reported a
clean bill of health over a third of the archive it had never opened.

A silent loss is strictly worse than a loud one, and this is why the crawler now gives every entry
it cannot type a per-file `SIZE` probe, treating only a successful probe as evidence of a file. All
32 previously-failed directories now list successfully as well; three are genuinely empty on the
server and nine are container directories holding only `csv`/`json`/`parquet` subdirectories.

One coverage gap remains: `/dissemin/publicos/uploads` returns `550 Access is denied` to both LIST
and NLST. That is a server-side ACL, not a dialect failure, and is recorded rather than passed over.

### Reconciliation held at scale

All 34,029 previously-known files classified `unchanged`, with **0 gone, 0 moved, 0 unresolved** —
no mass-withdrawal artifact from the tree tripling in size. `Dados_Abertos/BackUp_Ducks_SIASUS_PA`
(66 `.duck` files) *did* disappear server-side, replaced by `PA_SIASUS` and `APAC_SIA`; it correctly
produced no `gone` rows, because those files were never in this catalog.

### The sticky prefix map held a wrong answer, correctly

`CM` was established as SIHSUS from 42 files seen in the partial crawl. The full crawl found 1,717
files at 98% agreement under SISCAN — `CM` is SISMAMA's mammography series. The map held its first
answer, which is the designed behaviour and was right: a reorganisation and a shared prefix are
indistinguishable from one crawl. But holding with *no way out* meant the first crawl owned the
answer forever, and the first crawl is the most likely to be wrong because it sees least.
`pegasus-data prefix-adjudicate` settles it deliberately. After adjudicating, system disagreements
fell from 1,675 to 42 — and those 42 are real: `CM` genuinely appears in both trees, 98/2.

### Low-trust prefixes cover almost nothing

1,351 of 1,436 learned prefixes are low-trust, which sounds alarming and is not: they cover 4,219 of
207,251 files (**2.04%**), and none carries as many as a thousand. 1,313 are simply thin (fewer than
five observations). The 38 genuinely ambiguous ones are SINAN diseases published in both the legacy
tree and `Dados_Abertos` — shared prefixes, not a reorganisation. The count alone would have hidden
that; ranking by file count is the point.
