## ADR-0133: Of equivalent representations, the one already cached or smallest on the wire is read

**Date:** 2026-10-03. **Status:** active. Amends ADR-0047 (its decode-cost
preference).

**Context.**
- **What ADR-0047 chose.** Among equivalent physical forms of one
  publication, it chose the cheapest to decode (Parquet, DuckDB, CSV before
  compressed formats).
- **What that costs.** For SIH-RD 2008–2014, DATASUS publishes each month as
  `.dbc` (Acre 2008-01: 114 KB), `.dbf` (1.05 MB), `.csv` (1.05 MB) and
  `.xml` (5.1 MB). The selector fetched the CSV or XML copy, nine to
  forty-five times the bytes. Bytes on the wire are the project's scarce
  resource (CLAUDE §3).
- **The defect it caused during the outage.** With the FTP data channel
  down, the HTTPS mirror (ADR-0122) holds the `.dbc` and `.dbf` copies but
  not the CSV/XML trees. `query("SIH.RD", geography="AC")` returned nothing
  for 2008 and 2010–2012, and one month of 2009 (EVALUATION 2026-10-03 "SIH
  money is in one unit across every era").

**Decision.** Among candidates that ADR-0047 already treats as one
publication, the winner is the first by:
1. already in the blob store (`fetches` holds the path), which costs no
   bytes;
2. size on the server;
3. decode cost, as before;
4. path.

Conflict detection, editions (ADR-0068) and archive members are unchanged.

**Evidence.** On a fresh home through the mirror, SIH-RD Acre now returns:

| year | AIH | `VAL_TOT` total (R$) | time |
|---|---|---|---|
| 2008 | 46,087 | 22,365,143.69 | 99 s |
| 2011 | 52,269 | 33,510,058.61 | 96 s |

Rows and money equal the agent's direct reading of the `.dbc` files.

**Consequences.**
- **Fewer bytes per query** wherever a compressed copy exists.
- **Decoding `.dbc` is slower than reading CSV,** and the time is spent
  locally rather than on the wire.
- **A cached copy is never refetched in another format.**
