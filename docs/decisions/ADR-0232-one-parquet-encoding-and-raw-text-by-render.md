## ADR-0232: One Parquet encoding for the home, and a typed column's text as filed stored by render

**Date:** 2026-11-22. **Status:** active. **Extends** ADR-0231 (what the lake computes it does not store).

**Context.** After the record key left the lake, the listed lake was 29.8 GB, 2.1× smaller than its encoded size.

- **Row groups.** The lake writer made one row group per incoming batch: 65,536 rows where 262,144 were asked.
- **Compression level.** zstd ran at its default level.
- **Raw text.** A typed intake column kept its text as filed beside it, whole (`<NAME>__RAW`): 4.0 GB, 12% of the lake.
  ANS TISS items spent 28% on it and SNGPC 18%. Almost all of it is the typed value written back: 99.5% of TISS item
  values are their number with a decimal comma and no ".0".

**Evidence.** On SIH-RD SP 2024 (2.86 M rows):

| Encoding | Size | Write time |
|---|---|---|
| 65,536-row groups, current level | 113 MB | |
| 262,144-row groups | 102.8 MB | |
| zstd 9 | 96.2 MB | same as level 3 |
| zstd 15 | 94.6 MB | twice as long |

Scratch homes, every value compared by a hash over all columns:

- SIH-RD SE, AL and SP 2024 went from 130.6 MB to 110.1 MB.
- The TISS hospital events and items of Acre, January to March 2023, landed again, went from 251 KB to 159 KB.
- 26 older files re-encoded went from 5.98 MB to 4.67 MB.
- Every value read back identical, raw text included, through `Lake.read` and `query()`.

**Decision.**

1. **One encoding:** zstd 9 and row groups of 262,144 rows (`persist.kept.ZSTD_LEVEL`, `ROW_GROUP_ROWS`), stamped in
   each file's metadata (`pegasus.encoding`). The lake writer gathers batches into row groups (`RowGroups`).
   `write_parquet_atomic` and the intake's `COPY` use the same encoding.
2. **Raw text by render (`raw_text`):**
   - A landing chooses, per typed column, the render among a fixed set that gives back most of a sample's text. A date
     column's own declared formats are candidates too.
   - It stores the text only where the render does not give it back, and names the render in the file's metadata
     (`pegasus.raw_render`).
   - `Lake.read` and the intake's re-land give the text back whole, as `coalesce(raw, render(typed))`. Nothing is lost.
   - A render that gives back under half of the values is not used, and the text stays whole.
3. **`reencode-lake`** rewrites every file of an older encoding, or with whole raw text, value for value.

**Rejected.**

- **zstd 15:** 1.6% smaller again, at twice the write time.
- **Dropping the raw text where typing succeeded:** it is what lets a unit be re-landed under a changed declaration
  without downloading it again, and its formatting ("1,0") is information.
