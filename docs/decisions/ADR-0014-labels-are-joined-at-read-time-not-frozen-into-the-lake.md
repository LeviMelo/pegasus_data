## ADR-0014: Classification labels are joined at read time from vintage-scoped reference tables, not frozen into the lake

**Date:** 2026-08-18. **Status:** active.

**Context.** The first implementation wrote a `<field>_label` column for every
decoded field at build time. For `DIAG_PRINC` that was wrong for three reasons
(`docs/history/FINDINGS.md` §3b):

- it fixed a granularity choice invisibly (`E11` and `E119` are distinct
  CID-10 rows);
- it discarded the versioning: the 1992–1997 CID-10 has 14,197 codes and the
  current one 14,253, and a string baked into a 2019 row cannot be corrected
  without rewriting the lake;
- the published wording is lossy and dated (`DESCR` is 50 characters).

A second defect followed: `labels=True` selected `*_label` columns that had to
exist already, so asking for a label after a `--no-labels` build returned
unlabelled data with no error (`docs/history/pegasus_data_ARCHITECTURE.md` §8).
Reference tables landed in `b68e446` (2026-08-18); the read-time join in
`00af847` (2026-08-19: "the label join that was claimed but never
implemented").

**Decision.**
- Code tables live in `lake/reference/<table>/system=<SYS>/window=<valid_from>/`
  and are joined **at read time** for the years being read (ARCH §7.3, §8).
- A read with no year returns the current vintage (FINDINGS §3e).
- Rendering is controlled by `code_system` per variable (`internal`,
  `external`, `none`) and by a profile per call (`analysis`, `codes`, `audit`,
  `report`); any column can override both.
- `fetch()`, `load()` and `translate()` share one render path
  (`render_groups.py`), split per `(rows, family, year, competência)` so each
  generation is labelled against its own era (ARCH §8.2).

**Alternatives.** Materialised labels, as the brief's §7.1 step 3 read
literally. Rejected for the three reasons above. Small closed codelists may
still carry a materialised label; `describe()` says which policy applies.

**What would reverse it.** Nothing foreseen.
