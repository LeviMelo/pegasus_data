## 2026-08-23 — Measured state of the catalog and shipped artifacts (ARCH §21)

*Split from docs/history/pegasus_data_ARCHITECTURE.md §21 on 2026-09-28; text unchanged.*

## 21. Measured state

**This table is the project's bookkeeper.** Every count about what exists lives
here and nowhere else. `docs/RESUME.md` says what to do next, `docs/FINDINGS.md`
what measurement contradicted, §22 what is claimed on thin evidence, `docs/DEFECTS.md` what was broken and is now fixed — none of them
carry counts, because when they did they drifted. §21 read "1,572 described
(34.7%)" beside 538 tests while RESUME read "4,528 (100%)" beside 601, and a
reader had no way to tell which was current. The test count is stated beside the
numbers as the cheapest available clock.

Counted on the shipped artifacts, not estimated. **As of 1,184 tests passing.**

### Storage evidence

`scripts/storage_report.py` uses SQLite `dbstat` and exact row counts; it is
read-only and produces machine-readable JSON. On the recovered full catalog the
14,995,771,392-byte file had no freelist: the size is live expansion and B-tree
duplication, not stale SQLite pages. `code_tables` occupied 6.10 GB for 11.91M
rows (512 bytes/row), `dictionary` 3.98 GB for 21.29M rows (187 bytes/row), and
their primary/lookup indexes another 4.13 GB. The claim that “SQLite costs 15
GB” is therefore rejected; the maintainer warehouse stores expanded evidence
and repeated indexes. Runtime artifacts are compiled projections and total
41,705,449 bytes under the 47,185,920-byte manifest budget.

### The tree

| | |
|---|---:|
| files crawled | 207,251 |
| files the prior scan found | 124,810 |
| data files bound to a declared dataset | 207,030 (100%) |
| systems · datasets declared | 20 · 131 |
| strata · with a known schema | 4,418 · 3,688 |
| distinct schemas | 273 |
| families (system × series × schema) | 1,633 |

### Meaning — what a column IS

| | |
|---|---:|
| distinct columns catalogued | 4,528 |
| **columns described** | **4,528 (100%)** |
| curation entries · files | 4,534 · 108 |
| datasets with `what_one_row_is` | 131 (100%) |

`catalogued` is a MOVING denominator — it is the columns the census knows about,
and the census grows. That is not pedantry: this line read 100% while SIH-RD had
15 of its 117 columns described, because the census had reached families the
description waves never covered. Re-measure rather than trusting the number.

### Meaning — what a VALUE decodes to

| | |
|---|---:|
| label pack | 3,654,320 versioned runs · 2,238 codelists · 30.0 MB |
| CNES↔CNPJ crosswalk | 1,774,993 temporal evidence rows · 10.34 MB |
| field→codelist bindings shipped | 9,796 |
| bindings by rung | def 8,548 · manual 534 · community 315 · semantic_match 298 · layout_doc 101 |
| columns curation declares as code-bearing | 2,157 |
| **… reaching a codelist that ships** | **2,070 (96.0%)** |
| … bound to a registry the pack holds back BY DESIGN | 19 |
| … with no binding at all | 68 |

The 19 are not a gap, and saying so is what `curation/codelists.yml`'s ROLES
are for. They are CNES establishment and team registries — `CADGER*`, `TCNESBR`,
`INE_EQUIPE*`, `HOSFEDRJ` — plus two CNPJ columns that reach CNES through the
shipped crosswalk rather than through a label table. §14.9 holds all of those out
of the pack deliberately; they are reached through `fetch("CNES-ST")` and the key
declared in `joins.yml`. Each is bound to the directory it belongs to anyway,
because naming WHICH registry is the useful half of the answer even when the
table is deliberately absent — and at confidence 0.35, so it can never outrank a
table that does ship.

Reporting these as undecodable was conflating "no table ships" with "no table
should ship", which is the distinction the roles exist to draw.

The 68 that genuinely do not decode are not merely undone; the reasons are in
§22.1b. `semantic_match` bindings are CANDIDATES at
confidence ≤0.6 with `decodes_observed` NULL — the renderer weighs each against
the column's real values and discards what explains nothing, so a wrong one
costs a measurement rather than producing a wrong label.

### Elsewhere

| | |
|---|---:|
| dictionary rows (full catalog, not shipped) | 19,905,196 |
| open questions, recorded not guessed | 1,339 |
| full semantic bundle · per system | 153 MB · ~10 MB |
| dictionary database | 531 MB, 7.47M codes |
| vendored source documents (`sources/`, gitignored) | 11,379 files, incl. 2,563 `.CNV` |

The headline is the first two rows of the tree table. The mechanism behind the
82,441-file difference is stated plainly in `docs/FINDINGS.md` §0.

`docs/FINDINGS.md` records what we measured that contradicted an assumption.
**§22 below records the opposite** — claims this project makes that are NOT
well-evidenced, ranked by how much damage a wrong one would do, each with what
would settle it. A project whose pitch is that it says what it does not know
owes the reader that list, and owes it in the same document as the claims.
