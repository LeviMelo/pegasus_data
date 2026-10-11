# The query's split by competence: one sort instead of a filter per month (2026-10-11)

**Regime.** Branch `perf`, data home `pegasus_core_data`, SIH-RD 2016: 11,527,712 rows, 12 competences. Driver: the PegaSUS
evaluation 2026-10-11-performance (py-spy on `pg.query`).

**What was slow.** `render_groups.split_by_year_column` filtered the whole table once per competence. That was 19% of
one query.

**The change.** `_partition` does one stable sort and takes contiguous slices. Rows outside the values keep their
original order.

**Result.** The groups are identical: same order, same rows (the query's output hash is equal). The split takes
0.72 s, against 1.29 s.
