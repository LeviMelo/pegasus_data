# An export older than its native file is an older edition

**Date:** 2026-10-03.
**Regime:** commit a731835 plus this change.
**Data homes:** the maintainer catalog (2026-09-28 tree) and a fresh home at `~/pegasus_live/home`.

**Found in live use.** `query("SINAN.ACBI", period=2023)` returned:

| Home | Rows | File read |
|---|---|---|
| repo home | 80,094 | `SINAN/DADOS/PRELIM/ACBIBR23.dbc` (modified 2026-09-02, cached) |
| fresh home | 78,242 | `Dados_Abertos/.../ACBIBR23.csv.zip` (2026-01-29) |

The fresh home ranked candidates by bytes on the wire (ADR-0133), and the CSV is 2.95 MB against 4.14 MB. The CSV is the January edition of a preliminary series the Ministry republishes.

**Scope**, over the catalog's `files`:
- 4,473 logical publications have more than one representation.
- 693 of them have an export dated before the newest native DBC/DBF:
  - **SINAN, 235.** The CSV is often the smaller file, so it was chosen.
  - **SIH-RD 2014 XML, 458.** Larger than the DBC, so never chosen.

**Change.** `representations._older_than_native` drops such exports before the byte ranking. An export dated after its native file is a re-export and still competes on bytes: SIH-RD AC 2008-01 keeps its 114 KB DBC (DBC 2018, CSV 2025).

`plan()` on the fresh home now fetches ACBI 2023 as 4,136,899 bytes, the DBC.

**Not settled.** An export refreshed after a native file that was never updated would carry newer data. Dates cannot show that, and row counts would only be known after fetching both.
