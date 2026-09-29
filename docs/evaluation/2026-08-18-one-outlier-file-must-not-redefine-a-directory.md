## 2026-08-18 — One outlier file must not redefine a directory

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### One outlier file must not redefine a directory

The date convention is inferred per directory, exactly as §5.2 requires. The first
implementation of the first rule was: *a tail outside 01–12 cannot be a month, so the directory is
annual.* That is sound logic and it was wrong in practice.

`SIHSUS/200801_/Dados` holds 22,807 files. All but two are monthly — `RDAC1901.dbc`,
`CHBR1901.dbc`, `SPAC2603.dbc` — and two are annual ZIP bundles: `RDAC2017.zip` and
`RDSP2017.zip`, whose tail is `17`. Under "any outlier proves annual", those two files flipped the
entire directory, and `CHBR1901.dbc` was dated to **the year 1901** instead of 2019-01. The whole
modern SIH series landed a century early, silently, and every stratum built on it was wrong.

`RDAC2017.zip` is the same file the brief singles out — the one whose accidental placement in a
separate family was the only reason the 113-column schema surfaced in the prior compendium at all.
It is an unusually load-bearing filename.

The convention is now the **dominant** pattern (≥98% of tails being valid months), and the outliers
that motivated the inference are themselves left undated with `date_format = 'ambiguous'` rather
than forced into the majority reading — under a monthly reading `2017` would mean month 17, and
inventing a date for it is precisely what §13 forbids. Measured after the fix: SIHSUS spans
1992–2026, zero files date before 1990, and exactly two files are undated.
