# The cube, stage 1: SIDRA tables and series as cubes (2026-11-09)

**What was measured.** Whether the 26 context fields built from SIDRA (5 table slices, 21 stitched series) come out of
`cube()` exactly as they were stored, and whether an undeclared table is served. Real home `pegasus_core_data`, master
after bd867e4, ADR-0217. Scripts: the session's `cmp_sidra.py`, which compares stored fields with `cube()` by
(municipality, year) → (value, status), and `cmp_views.py`, which compares stored copies with `load_field` on all seven
columns and their types.

| check | result |
|---|---|
| 26 fields against `cube()` | 26 equal, 0 differences (about 640,000 rows: gdp 122,540; households 16,642; population by race 16,705…) |
| 26 stored copies against `load_field` served from the cube | 26 equal on all columns and types |
| GDP 2021 rolled up from municipalities to states | 27 rows, Brazil 9,012,142,031: the field's verified total |
| undeclared tables | 2683/343 (deaths by civil status, 122,540 rows, 95 `not_available`) and 10381/696 (5,570 rows) served; their state roll-ups too |
| a table with no municipal facts held | raises with the fetch command, never an empty table |
| a stitched series read | 8.2-8.6 s built, 0.66-0.70 s from the cube cache |

The 26 copies under `lake/fields/` were removed after the second check.

**A defect found on the way, and repaired.** A records cube of SRAG was planned as an FTP fetch, though SRAG lives in the
lake. The catalog held no lake partitions for any intake source except PNI's month landed the day before.
- **Cause.** `pegasus-data families`, run on 2026-11-08 to refile the CM files, deletes every family it does not derive
  from the crawl's strata. The intake's families are not derived from strata, so it deleted them, and with them their lake
  partitions, codelist bindings and ledger rows. The records on disk were untouched, but `query` could not reach SRAG,
  SISAGUA, SNGPC, FA, BNAFAR, SIES or REGIAO. Their old fields were built from disk, which hid the loss.
- **Fix.** The families stage now keeps a family whose `schema_source` is `intake` (`inventory/families.py`).
- **Restored.** `intake-register` (`intake.register_held`) re-registers every landed unit from its own parts. A file
  source's unit is found by its sidecar's family; an API piece or a snapshot read by the publication path the catalog
  still kept.
  - 186 file units and 79 API or snapshot units, 391 partitions, 711,680,059 rows, each source's count equal to its files.
  - One stale unit was left out: the health-region list's old offset piece, superseded by the per-state pieces.
- **Checked.**
  - After `curate`, SRAG 2022 (566,133 rows), SISAGUA-VIGB 2023, SNGPC-IND 2021 and BNAFAR 2025 query from the lake,
    labelled.
  - `families` run again keeps all 391 partitions.

**Stage 2, the records adapter, against the intake fields** (`records:<dataset>/<event>`; the session's `cmp_records.py`).
The comparison is by (municipality, month).
- **The adapter.** It counts the event type's events by the dataset's place and time bindings. It reads only the
  published years, in runs, and lists the others as `not_published`. Places follow `geography.place_municipalities`:
  - a code as filed, less `.0`;
  - 6 or 7 digits, a 7-digit code read by its first six;
  - in a state with one municipality, that municipality.
- **Results:**

  | field | field total | cube total | cells differing | events unplaced |
  |---|---|---|---|---|
  | yellow_fever_human_cases | 2,893 | 2,893 | 0 | 18 |
  | yellow_fever_human_deaths | 1,065 | 1,065 | 0 | 4 |
  | srag_cases | 4,666,020 | 4,665,991 | 27 | 890 |
  | srag_covid | 2,291,288 | 2,291,284 | 4 | 334 |
  | srag_deaths | 935,795 | 935,792 | 3 | 213 |
- **The SRAG difference is a correction, not a loss.** It comes to 29 notifications, all in 2025: the notifications SRAG
  files in both INFLUD24 and INFLUD25 (its gotcha). The field counted rows; the event type merges by `NU_NOTIFIC`.
- **Brasília.** Before the single-municipality rule, 105,788 SRAG events filed under the Federal District's
  administrative-region codes (53xxxx) were unplaced, for example 1,373 against 5 in December 2022.

**Stage 3 can start without downloads.**
- **The mirror is a copy.** The CNES fields' private pipeline (`sources/cnes.py`) had downloaded 1,728 DBCs (ST, LT, EQ and
  EP, 432 each) from a third-party mirror of the FTP.
  - All 1,728 have the size the catalog lists for the same FTP path.
  - Five sampled from the FTP (STAC2312, LTAC1512, EQRR1012, EPAP0812, STRR2012) are byte-identical.
- **Adopted.** `adopt-copies` (`adopt.adopt_copies`) stored them in the blob store as fetches of their FTP paths
  (`local-copy`, 367 MB), the folder left as it was. `query("CNES.LT", period="2015-12", geography="AC")` then read
  Acre's 204 rows (1,354 SUS beds) within a 1-byte download budget.

**Every convertible intake field against its cube** (the session's `cmp_intake.py`; 581cddc and after). The comparison is
by (municipality, period, strata), and each cube is the field's own declaration as a request: its `where`, its `by`, its
`sum` column, and its event type where the dataset declares one, else its rows.

| fields | result |
|---|---|
| 17 SISAGUA surveillance and control counts (analyses 34,195,729; censored, quantified, outbreak, the seven `_assessed` denominators, other, cyanobacteria, control other, outside standard) | all equal, 0 cells differing |
| `sisagua_surveillance_result_sum` (a sum) | equal: 67,716,248.8 |
| `sisagua_control_counts` (a sum over `CAMPO` rows by prefix) | equal: 2,174,577,401.8 over 15,792,073 cells (the first run gave 0 because `where`'s prefix form was not yet read; it is) |
| yellow fever: cases, deaths, epizootics | equal |
| SRAG: cases, COVID, deaths, ICU | lower by the notifications filed in two yearly files (29, 4, 3, 12), a correction |
| `ans_beneficiaries` | not comparable: ANS's records were never landed, so its stored copy is its only form |

Not yet cubes: the 7 SISAGUA outcome shares (zero-filled over their `_assessed` population), INEP's unpivoted margins,
S2iD's register of events, and the 5 SISAGUA supply, tanker and SNGPC sums whose datasets have no code-placed roles.

**The rest, on ca91def and after (2026-11-09, `scratchpad/cmp_views_db.py`, year by year).**
- **The binding `landed`.** An intake record carries the place and period it was landed by (`_MUNICIPALITY`, `year`,
  `_MONTH`), so a source placed by a name or with no roles file is a cube. SNGPC's three sums are equal in every cell:
  compounded 1,861,805 rows (2,176,754,969 units), sales 56,212,387 and by CID 57,048,191 rows (2,597,529,837 units).
  - The tanker trucks are equal (666 rows, 2,174), and so are the five supply-population sums (2,119,897,396 persons).
    The register's new roles bind it by `NU_ANO` alone: the first run gave 0 rows, a year-only binding having no
    month; the cube keeps such a record at its year, as it does a month-less event.
- **Memory.** A records cube read a run of consecutive years in one query; SNGPC's sales of 2014-2021 national ran out
  of memory. A dataset's rows are now read a year at a time. Events keep their runs, since an event type removes a
  notification filed in two years' files only within one read.
  - The sales field is 10.4 GB in memory when read whole (its strata are plain strings), as its stored copy was.
- **A comparison artefact, not a difference.** A first pyarrow comparison found 378,090 cells differing out of equal
  totals: a join never matches a null key (`co_cid10` is mostly null). Sampled cells were identical; with nulls keyed,
  0 differ.
