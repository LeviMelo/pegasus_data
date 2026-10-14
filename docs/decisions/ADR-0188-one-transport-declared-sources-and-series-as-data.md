---

# ADR-0188: one transport for every non-FTP byte, S2iD/INEP/ANS as declared sources, population series as data

**Date:** 2026-10-14. **Status:** accepted. Builds on ADR-0162, ADR-0172, ADR-0175; the structure section of the intake review of 2026-10-14.

**Context.** Three transports remained beside `intake`: `sources.download` (urllib), `intake.get_json` (httpx) and one private urllib client each in
SIDRA, BR-DWGD and TabNet, with four retry rules, two User-Agents and no common politeness. They disagreed in ways that broke reads: the httpx
client verified against `certifi` and could not reach `servicodados.ibge.gov.br` (incomplete chain: `fetch_municipalities` waited 77 s and failed)
or `download.inep.gov.br` (reset); from this network `zenodo.org` answers 403 over IPv6 and serves over IPv4, which failed every BR-DWGD read
after 53 s. S2iD, INEP and ANS were read by three modules that reduced a file to a field and kept no record (an event with no date was dropped
uncounted, an unplaced beneficiary kept under its raw code). `KNOWN_SERIES` was a Python dict that declared years and an `age_standardizable`
flag the files could contradict, and was mutated by the builder.

**Decision.**
1. **`transport.py` is the one client** of every byte not on the DATASUS FTP tree: `request`/`get_json`/`get_text`, `read_range`, `download`.
   HTTP/1.1 over IPv4 with the operating system's trust store (`PEGASUS_IPV6=1` to let the system choose), one browser User-Agent, one request
   per interval per host (reserved under a lock, shared by threads), one classification (resets, timeouts, 408/425/429 and 5xx retried with
   `Retry-After`; any other 4xx is `SourceAbsent` at once; a certificate that does not verify is not retried), one resume rule (`If-Range`
   validator, 416 only when the length matches). SIDRA, BR-DWGD, TabNet and every file reader call it; SIDRA passes its own `retry_on` (its 500
   is a request it will not serve). The FTP client and the S3 mirror of the FTP tree are the FTP tree's own and stay.
2. **S2iD, INEP and ANS are declared sources** (`curation/intake.yml`): their records land in the lake (datasets `S2ID-EVENTOS`, `INEP-EDBASICA`,
   `ANS-ICB`) under the landing contract, are counted against an independent figure, and the fields `disasters`, `inep_enrolments` and
   `ans_beneficiaries` are derived from the records with the layout their readers use. The declaration mechanism gained what they needed and
   nothing source-specific: `origin.across` (further pattern axes: ANS by state), `csv.member` (INEP's zip holds two tables), `csv.multiline`
   (quoted line breaks: the independent count is a second parser's, not the lines'), `by: [{COLUMN: name}]`, field `unpivot` (strata filed as
   columns), field `rows` (a register read as events), field `declares` (the keys fields.yml gave the field: `where`, `icd10`, `harm`), a
   per-column `unparsed` count, and smaller row groups for tables wider than 100 columns (INEP's has 408: the 2 GB limit ran out at 20,000 rows
   a group on four threads).
3. **Population series are data.** `curation/populations.yml` declares each series (kind, authority, source, the axes the producer publishes,
   notes); the files decide the rest. `sources.ibge.materialised` reads the years, columns and municipality code widths; whether a rate can be
   age-standardised is whether the files carry sex and age; `load_population`, `capabilities`, `Catalog.population_series`, `verify` and
   `/population` read the same thing. A directory that is only another under a different case is not the series. `load_population` refuses a
   year the files do not hold and takes its axes from the caller (`by=()` by default), and its state filter is by code width.
4. **A command that writes says where** (`cli._writer`, on stderr): the root, the lake, the catalog, the blobs and the work place, and the
   layers an explicit `--root` displaced.

**Consequences.** Bytes, retries and politeness are one thing to read and to change. The three source modules and three field builders are
gone (`sources/s2id.py`, `inep.py`, `ans.py`; `fields._build_*`). The field layouts are those of the old readers except where the records now
decide: a beneficiary or event whose municipality is not an IBGE municipality is *unallocated* (kept in the records, counted, left out of the
field) instead of carried under its raw code (ANS Dec 2022: 41,879 of 50,530,569 medical-hospital links; `sus_dependent.load_ans` takes that
mass from the records); `ans_beneficiaries.value` is a double, `month` is gone, every intake field carries `status`/`municipality7`/`source`.
`S2iD` is now read with `encoding: mixed` (cp1252). A home built before keeps `lake/population/censo` and its old field folders until they
are rebuilt (`pegasus-data population --series census_covariates`, `pegasus-data fields`); the catalog table `population_series` and
`api_ingests` are no longer written. INMET's and CNES's readers stay (they decode a 1.4 GB parquet and DBC files), as does `sigtap` (an FTP
server of the Ministry).
