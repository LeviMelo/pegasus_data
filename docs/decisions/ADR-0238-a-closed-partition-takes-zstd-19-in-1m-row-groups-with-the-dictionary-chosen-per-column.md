## ADR-0238: A closed partition takes zstd 19 in 1M-row groups, with the dictionary chosen per column

**Date:** 2026-11-26. **Status:** active. **Amends** ADR-0232 (one encoding, zstd 9). **Request:** the author,
2026-11-26: the disk is nearly full; every gigabyte matters; the strongest compression should be the default form,
not a second tier (docs/plans/storage.md).

**Context.** Measured on real partitions, AL (docs/plans/storage.md, "One form, at the archive's size").
- zstd 9 in 262,144-row groups with the dictionary on every column leaves 10-18% on the table. The dictionary loses on
  near-unique columns (an AIH number, a postcode) and wins on coded ones; nothing declared says which.
- Level 22 gave SIH-SP AL 2023 13.71 MB where 19 gave 13.74, in 34 s against 27. Both read at about the speed of 9
  (every row of SIH-SP AL: 1.43-1.50 s against 1.29-1.31).
- A probe of the first 65,536 rows chose the dictionary on 34 of SIH-SP's 43 columns in 8 s; one of 262,144 rows chose
  35 in 30 s.
- ADR-0232 rejected higher levels for write time. A closed year is written once.

**Decision.**
1. A partition of a year before last (`reencode-lake --closed-before`, default the last year) is rewritten in the
   closed encoding: zstd 19, row groups of 1,048,576 rows, the dictionary on the columns where `probe_dictionary`
   finds it smaller, `_row` delta-encoded. Stamped `pegasus.encoding = zstd19-rg1048576-dictprobe`.
2. Builds keep writing the open encoding (zstd 9); a closed file is never rewritten back to it.
3. Value for value, in one rename per file, the catalog's size following, role tables and runs carried current
   (`carried_currency`), as every re-encode.

**Consequences.** Whole AL 2023 files: SIH-SP 16.71 to 13.69 MB (-18%), SIH-RD 5.11 to 4.58 (-10%), CNES-PF 24.93 to
21.55 (-14%); every value read back equal. About 2 s of one core per MB written. The dependency split and the
snapshot timeline of the storage plan come on top of this encoding, not instead of it.
