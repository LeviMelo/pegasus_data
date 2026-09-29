## 2026-08-19 — What the catalogue holds after the census

*Split from docs/history/FINDINGS.md §3i on 2026-09-28; text unchanged.*

## 3i. What the catalogue holds now (2026-08-19)

After the census, the community ingestion and the reference rebuild:

| | |
|---|---|
| files crawled | **207,251** |
| strata | 4,418 |
| strata with a known schema | **3,688** (83%) |
| distinct schemas | **273** |
| distinct columns known | **4,354** |
| dictionary rows | 19,905,196 |
| codelists | 10,748 |
| field→codelist bindings | 9,304 |
| systems documented | **16** |
| columns that decode | **2,159** |

The gap between "described" and "decodable" is worth stating because they are
different facts and only reporting the first buries the second. CNES has 4
described columns and **156** whose values now translate; SINAN has 0 and
**1,178**. Across all systems, 268 columns carry a prose description and 2,159
have a working codelist.

The 1,339 open questions are not a backlog that grew — they are the mixed-width
tables, the unlabelled codelists and the suspect bindings that the system names
rather than papering over. A gap you can query is a different thing from a gap
you cannot see, which is the whole thesis of §0.

### Where the schema catalogue still stops

705 strata are sampled by a `.zip`, whose members need the archive rather than a
prefix; a `.parquet` keeps its footer at the end of the file; 7 are LHA
self-extracting `.exe`. These are counted apart from the 30 that failed on the
network, because "needs a different reader" and "the fetch broke" want different
responses and only one of them is fixed by trying again.
