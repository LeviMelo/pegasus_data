## ADR-0006: A family is (system, series, schema signature); format is a representation, and an archive member is a dataset

**Date:** 2026-08-18. **Status:** active.

**Context.** The prior scan keyed families by format, so one dataset published
as `.dbc` and as `.csv.zip` became several (defect D3,
`docs/history/pegasus_data_ARCHITECTURE.md` §2). SIH-RD's column layout changes
over time: nine generations were visible in January files for Acre on
2026-08-18, and the header census later counted twenty
(`docs/history/FINDINGS.md` §2, §3g). One APAC `.exe` is seven logical datasets
with seven schemas (FINDINGS §1 V2). The prior `choose_archive_member()` kept
one "best" member and would have discarded six. Implemented in `7b9488a`.

**Decision.** Three keys, kept distinct (ARCH §5.3):
- `stratum := (system, series, year)`, the unit of schema evidence;
- `family := (system, series, schema_signature)`, the unit of data. A schema
  change starts a new family instead of corrupting the old one;
- `representation := (family, container_format)`. The same data as `.dbc`
  and as `.csv.zip` is one family with two representations.

An archive member is a first-class row in the family model. A family needs a
schema, not a decode: a header-census stratum is grounds for a family
(`families.schema_source = 'header'`). That change took families from 316 to
1,633 and made sixteen more systems fetchable (ARCH §5.3, commit `9f1ab3b`,
2026-08-19).

**Alternatives.** Families keyed by format, as in the prior scan. Rejected as
defect D3.

**What would reverse it.** Evidence that one schema signature carries two
different datasets within a series. The ontology (ADR-0033) would then have to
split what the signature joins.
