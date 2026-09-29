## 2026-08-30 — Reviewing the whole with fresh eyes (three-front review)

*Split from docs/history/FINDINGS.md §3v on 2026-09-28; text unchanged.*

## 3v. Reviewing the whole with fresh eyes (2026-08-30)

A structured review of three fronts -- retrieval/persist, serve/capabilities,
semantics/catalog -- surfaced sixteen findings; thirteen verified and were
fixed, one was judged self-healing, two were narrowed to notes. What is worth
keeping is not the list (the commit carries it) but the shapes:

**The unexercised path is where the corruption lives.** `min`/`max` measures
were declared, advertised in the capability tables, and broken at every stage
-- the lift filled blanks with 0.0 instead of the identity, the intra-chunk
group summed extreme-state columns into totals, and the columnar finalize
passed the identity through as literal Infinity. No shipped spec declares one,
which is precisely how all three survived; the first spec author to write
`kind: min` would have gotten silently wrong numbers with no refusal anywhere.
The generic lift fallback that summed "whatever it was handed" is now an
explicit refusal: a new kind must be added by hand or not at all.

**A rule enforced everywhere except one entry path is not enforced.** The
vintage guarantee held when a year was asked and not when none was; the
"visibly unfinished" rule held for bound codelists and not for curated columns
nothing was bound to; adjudications carried validity windows the runtime never
consulted. Each fix was two lines; each gap was the sacred rule with one door
left open.

**Caching discipline, consolidated.** Since 3t the codebase has grown a real
cache layer, and the review closed its remaining holes: keys must carry
exactly what the answer depends on (the manifest mtime joined the descriptor
key; the geography pack's mtime joined its readers), writes that a cache
derives from must invalidate at the mutation site (`build_label_pack` now
clears its own chain -- including the cached pack PATH, which froze `None`
forever on a fresh install), and a multi-file artifact must move atomically
or its caches read a torn pair (the manifest now stages+renames like the
cells beside it).

**Self-healing beats transactional, when it is real.** `load_curation` is four
separately committed writes, and the reviewer flagged the torn state a crash
leaves. But the curation fingerprint is recorded only AFTER all four land, so
an interrupted reload re-runs whole on the next fetch. That is a legitimate
design -- noted here so nobody "fixes" it into a lock.

Also in this pass: the population stage had rotted against the decode
refactor (`_RemoteTable` promised DecodedTable's shape and lacked
`to_table`), and `build_aggregate`'s national fallback was unreachable for
exactly the datasets it was written for, because an empty per-UF probe RAISED
instead of returning empty. Both were found not by the review but by running
the paths -- the fallback by building SINAN dengue, the population stage by
materialising denominators for B6. A review reads what the code says; a build
finds out what it does.
