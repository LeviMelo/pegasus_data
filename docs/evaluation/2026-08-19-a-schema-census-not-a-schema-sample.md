## 2026-08-19 — A schema census, not a schema sample

*Split from docs/history/FINDINGS.md §3g on 2026-09-28; text unchanged.*

## 3g. A schema census, not a schema sample (2026-08-19)

### The catalogue was a sample because a census looked unaffordable

Profiling reads a file to learn what its columns *contain*, and that needs the
payload. One representative file per stratum totals **183 GiB**, and 63% of
strata hold exactly one file, so there is no cheaper member to substitute. Every
schema statement this project made therefore came from a sample, and "SIH-RD has
N generations" always meant "N generations were sampled".

That constraint turned out to be an artefact of asking the wrong question. A DBF
declares its entire schema — every field name, type, width and decimal count — in
a header of a few hundred bytes. A `.dbc`, DATASUS's compressed DBF, stores that
header **uncompressed** ahead of the compressed payload. So the schema is
readable from a ranged fetch of the first few KB, and the payload is needed only
for questions about values.

Measured on `RDAC9201.dbc`: all 35 fields read from the first **1,153 of 91,967
bytes**, 1.25% of the file. Run over the whole tree: **3,701 strata examined, 2,813 schemas read for
19.23 MB**, against 183 GiB for the decode-everything route — a reduction of
about 9,750x. 859 targets are not DBF-shaped (CSV, XML, JSON, archives) and are
counted apart from the 29 that failed on the network after four retries.

### Validated two independent ways

The shortcut is only worth having if it gives the same answer as a full decode.

* **Against full decodes.** 571 cached `.dbc`/`.dbf` blobs had their
  prefix-parsed field list compared against the field list from a complete
  decode: **571 identical, 0 differing**, including an 87-column SIM file and
  48-column CID-9-era files.
* **Against the files' own arithmetic.** Every catalogued schema's field widths
  sum exactly to its declared record length, plus one byte for the DBF deletion
  flag: **100%**. A misread descriptor array would not add up.

Only two DBF type codes appear anywhere on the tree — `C` (character) and `N`
(numeric) — which is consistent with DATASUS writing dates and codes as text.

### What the census found that the sample could not

| series | generations | field range | span |
|---|---|---|---|
| `SIHSUS/RD` | **20** | 35–114 | 1992–2026 |
| `SIM/DOFET` | 18 | 40–99 | 1979–2026 |
| `SIM/DOEXT` | 13 | 40–88 | 1979–2026 |
| `SIM/DO` | 11 | 40–88 | 1996–2026 |
| `CNES/ST` | 3 | 200–208 | 2005–2026 |

The brief said SIH-RD had "exactly three" schema generations (35, 86, 113). An
early sample found 13. The census finds **20**, from 35 to 114 columns. The
progression is not a correction of the brief so much as a demonstration of what
sampling does: each wider look found more, because the answer was always "more
than you have looked at".

### Recorded apart from profiles, deliberately

Census results land in `schema_header_facts` and mark the stratum `'header'`,
never `'ok'`. A profile has read the data and can speak about values; the census
has read a few hundred bytes and can speak only about columns. Merging them would
let "we know this column exists" be read as "we know what is in it", which is the
class of error this project exists to prevent. They share `schema_signature`, so
a census entry and a profiled sample of the same shape land on the same family.
