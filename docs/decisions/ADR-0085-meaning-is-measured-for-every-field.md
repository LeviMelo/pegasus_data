## ADR-0085: Meaning is measured for every field of every family, against a total standard

**Date:** 2026-09-29. **Status:** active.

**Context.**
- **The standard (user, 2026-09-29).** Every variable is described and every
  code is translatable, with no exception, including the hard classifications:
  geography, ICD, occupations (CBO), procedures (SIGTAP) and establishments
  (CNES).
- **What existed before.** The project had spot checks only: a live scenario
  counted labelled columns in one file.
  - Those counts cannot tell a column decoded 60% from one decoded 100%.
  - They cannot see a field no scenario touches.
- **Two findings on 2026-09-29.** The readable presentation (ADR-0084) showed
  them at once:
  - SIH `CNES` was undecoded: the establishment registry had been held out of
    the label pack by design.
  - SIH `CBOR` was undecoded too.

**Decision.**
- **What is measured.** `semantics/coverage.measure` classifies every
  (family, field) of the catalog, 22,714 rows on 2026-09-29, on two axes:
  - **description**, from the curation: `documented` (a cited source),
    `inferred`, or `missing`;
  - **coding**, from the compiled label decision, whose `share` is the
    fraction of codes observed in real sample files that the chosen table
    decodes: `not_coded`, `decoded`, `partial`, `undecoded`, `unmeasured`, or
    `unknown` (no curation entry says whether the field is coded).
- **Where it is reported.** `pegasus-data meaning` reports each system at its
  **worst** family and writes every row with `--out`. The rows under
  `data/probes/coverage/` are the work list; each run is an evaluation entry.
- **When a field counts as done.** Only when it is `documented`, and either
  `not_coded` or `decoded`. `partial` and `undecoded` are defects to be closed
  from a source: a DATASUS table, a data dictionary, a layout document, or the
  published classification. They are never closed by guessing.

**What would reverse it.** Nothing: this is the measure of the project's
purpose. Its classification rules may be refined; for example, sentinel codes
documented as "not informed" count as decoded.
