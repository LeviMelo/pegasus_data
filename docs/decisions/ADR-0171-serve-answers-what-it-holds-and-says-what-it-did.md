# ADR-0171: the HTTP layer answers from what is stored, refuses what matches nothing, and says what the engine did

**Date:** 2026-10-14. **Status:** accepted. **Contract:** `../pegasus_view` reads `/health`, `/datasets`, `/capabilities`,
`/population`, `/geo/membership`, `/records` and `/artifacts`; no field was renamed or retyped, fields were added and values corrected.

**Context.** A review of `serve/` on 2026-10-14 found answers that looked legitimate and were not: `/geo/membership` picked the
alphabetically first system for 347 contested municipalities and accepted `system=NOPE`; `/population` mixed 6- and 7-digit
codes in one POPTCU response and answered `0.0` for a year it did not hold; `dim.SEXO=1&dim.SEXO=3` served SEXO=3 alone
(7.17 M admissions against 12.52 M), `dim.SEXO=ZZ` an empty 200; `/records` echoed the requested period whatever the engine
adapted, depended on the server's presentation setting, and could download from the FTP inside a handler; the descriptor took 18 s
to build, the covariates table `censo` was offered beside the SIDRA census `CENSO` as an age-standardisable denominator.

**Decision.**
- **Refuse what matches nothing (422), with what exists.** A `dim.` code the artifact does not hold, a year, month, UF,
  municipality or classification member outside it, an unknown `system`, a population year the series lacks. Repeated `dim.X`
  parameters merge. Months accept `YYYY-MM` (the wire's own form) and municipalities `code7`.
- **One identity, one width.** `capabilities.artifact_identity` (cells, manifest, spec, membership pack, `geography.yml`, the
  population directories) keys both the descriptor and the response caches, which are bounded by bytes and evict one entry.
  `/population` maps every code through `geography.to_code7`; an extinct code (POP 53, POPTCU 2001: 1) leaves the municipal
  rows and is named in `unresolved` with its mass, which stays in `total`.
- **Denominators are what the files hold.** `sources.ibge.materialised` reads columns and years from the parquet; the descriptor's
  `stratifications`/`years` and `/population`'s refusals come from it. The covariates series is `census_covariates`
  (`kind="covariates"`, never a denominator); `KNOWN_SERIES` refuses names that differ only by case.
- **Stored, not computed.** `/geo/membership` is built once per (pack, system) with `conflicts` per municipality and sent with an
  ETag and a day's max-age. `/records` reads the lake only (`max_download=0`, 409 when it would fetch), spans at most three
  years, caches tables by bytes under a per-key lock keyed on the catalog's identity, takes `settings`, serves codes as filed
  (`present="codes"`) and returns `effective_period`, `warnings`, `structural_absence`, `complete`, `gaps` and
  `geography_basis`. A timeline's missing stored run (`LookupError`) is a 409, as is a server rooted away from the default home (the timeline readers take no `settings`). `/geo/mesh` (nothing wrote its files) and the start-up
  roll-up warm-up are removed.

**Consequences.** `pegasus-data population --series census_covariates` replaces `--series censo`; an old `lake/population/censo`
directory is ignored. The first `/geo/membership` for a system costs 2 to 3 s once. `/records` without a lake slice answers 409
where it used to download.
