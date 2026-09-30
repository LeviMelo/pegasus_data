# Pre-merge live run: every scenario and every declared dataset, before `redesign` became `master`

**Date:** 2026-09-30. **Regime:** `redesign` at `206ceb2`, `scripts/live.py
--all --fresh` (fresh `~/pegasus_live/home`), live FTP, 00:35–01:25.
Artifact: `data/probes/live/20260930-010457/` (one JSON per scenario plus
`summary.json`); re-run with the corrected metric,
`data/probes/live/20260930-013931/`.

**Why this run.** A merge into `master` should rest on the system working
for a person, from nothing, against the real server: every scenario a user
would run, and every declared dataset queried for its cheapest publication.

**Counted.**
- **Scenarios:** metadata, sih_rd, fetch_sih, sim_do, sinasc, cnes_st, sia_pa,
  sinan_deng, sinan_tube, cli_query, sih_2016, sia_sp_parts, age. All `ok`.
- **Sweep:** every declared dataset `ok` but one. `SINAN.CHAG` 2025 failed:
  the server lists `CHAGBR25.dbc` and answers SIZE, but refuses RETR with
  `550 The parameter is incorrect`, three times running. The library reports
  it as "could not be fetched or decoded". A server fault, recorded in
  DATA_SOURCES §1.7.
- **`SINAN.COLE` returned 0 rows as `PublishedEmpty`.** `COLEBR25.dbc` is
  2,923 bytes, a header with no records. The empty result is labelled as
  such, which the library already does by design.

**A defect in the harness itself.** Every scenario but one reported
`labelled=0`. The metric counted `<column>_label` companions, and the default
presentation (ADR-0084) has none: a coded cell reads "Label (code)". The
metric had measured nothing since ADR-0084. It now reads the readable form
too: a column counts as coded when ≥ 90% of its values end "(…)", and as
decoded unless a value reads "code (?)". Re-run: sih_rd 58 labelled columns,
sinasc 36.

**Defects found beside the run, fixed on `linkage`:**
- **National queries failed for per-state datasets.** `geography="BR"` raised
  NothingPublished (ADR-0109).
- **Provenance vanished under `select=`** (ADR-0109).
- **Uncoded date columns warned.** `DT_SAIDA` and `DTOBITO` are `code_system:
  none` but bound by a kit `.DEF`, and warned "no bound table decodes the
  column" on every SIH and SIM query. Rendering now skips label selection for
  a column the curation declares uncoded. SIH-RD's warnings went from 2 to 1.
- **SIH `IDENT` read TabWin's grouping** (ADR-0108).

**Merge.** `master` fast-forwarded to `206ceb2` locally; not pushed
(CLAUDE.md §4).
