## 2026-08-23 — Reviewing the aggregate layer at the scale it is for

*Split from docs/history/FINDINGS.md §3q (second) on 2026-09-28; text unchanged.*

## 3q. Reviewing my own aggregate layer (2026-08-23)

A self-review of the code in §3o, measured rather than read. Three defects, all
mine, all found by asking "what does this cost at national scale" rather than
"does it pass".

### `memberships()` scanned the whole pack on every call

The lookup read every column of the 75,000-row geography pack to Python lists
**inside each call**. Measured: **665 ms per municipality**, so resolving one
national roll-up would have spent **62 minutes on geography alone** — for an
artifact whose entire purpose is answering in seconds.

Indexing once, at first use:

| | before | after |
|---|---:|---:|
| per lookup | 665 ms | **168 µs** |
| all 5,706 municipalities | 3,708 s | **0.96 s** |

Same answers. A ~3,900× difference that no test caught because every test used
a handful of codes.

### The merge was a Python loop, in both directions

`aggregate()` merged cell by cell and `build_aggregate()` lifted row by row.
Measured on a synthetic national year (133,680 cells): 2.6 s per roll-up, and a
realistic artifact is ~5× larger — about 13 s per question.

Both are now Arrow grouped aggregation, and **that is a property of the algebra
rather than an optimisation**: every accumulator is a commutative monoid whose
merge IS a column aggregate. `count` and `sum` merge by summing one column,
`mean` by summing `(n, sum)`, `ratio` by summing `(num, den)`, `min`/`max` by
`MIN`/`MAX`. The whole vocabulary maps onto `group_by().aggregate()` with no
special cases — which is a decent sign the abstraction was right.

| | before | after |
|---|---:|---:|
| serve, 133,680 cells, worst roll-up | 2.6 s | **1.1 s** |
| serve, 66,564 output rows | — | **1.5 s** |
| build, SIH-RD/AC/2022 end to end | 199 s | **113 s** |

The build's remaining time is the fetch; its aggregation went from ~70 s to
~3 s. Every figure on the rebuilt artifact is byte-identical to the loop's:
49,547 admissions, 1,706 deaths, R$ 43,377,991.73, mean stay 4.702323.

### Arrow's cast raises on DATASUS's blanks

Naively casting a text column to double fails on `''`, and DATASUS writes
numbers as fixed-width text where blank means ABSENT. Non-numeric cells are now
nulled before the cast, because a null contributes nothing to a sum and nothing
to a mean's denominator — which is what "not observed" should do. Coercing them
to zero instead would drag every mean down invisibly, which is the same class of
error as counting a structural absence as a clinical zero.

### And the `query(select=)` defect from §3o is fixed

The planner adds `_source_path`, `year`, `_competencia` and `_source_resolution`
as hidden dependencies because the semantic layer needs them. **Three of the four
are derived after retrieval** by `_with_competence`, out of `_source_path` and
the source report — no DATASUS family carries them — and all four were being
passed to the source projection. So every `select=` query refused.

The fix is one subtraction in the executor: a source projection excludes what is
synthesised downstream. `_source_path` stays, because it is a real column and is
the thing the other three are derived FROM.

Verified against live data: `query("SIH-RD", period="2022-01", geography="AC",
select=[7 columns])` now returns 3,977 rows × exactly those 7 columns.

It survived a suite that exercises this path hard because **without `select=`
nothing is projected and every column arrives regardless** — the defect needed
the narrow projection an aggregate build happens to want.

### The lesson

None of these were correctness bugs and every test passed throughout. They were
found by asking what the code costs at the scale it is *for* — and the artifact
exists precisely because scale is the problem. **A layer built to make something
fast should be measured at size before it is called done.**
