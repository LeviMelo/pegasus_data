## ADR-0013: A filename's date convention is inferred per directory, by the dominant pattern

**Date:** 2026-08-18. **Status:** active.

**Context.** `SIHSUS/200801_/Dados` holds 22,807 files. All but two are
monthly (`RDAC1901.dbc`, `CHBR1901.dbc`); two are annual ZIP bundles
(`RDAC2017.zip`, `RDSP2017.zip`). The first rule, "a tail outside 01–12 cannot
be a month, so the directory is annual", let those two files flip the whole
directory, and `CHBR1901.dbc` was dated to the year 1901. The modern SIH series
landed a century early, silently (`docs/history/FINDINGS.md` §3, "One outlier
file must not redefine a directory"). Deciding per file instead gives a
directory in which some files are 2008 and some 2080 (ARCH §5.2). The usual
two-digit pivot (≤40 → 2000s) read `IBGE/projpop`'s `70` as 1970 (FINDINGS §1
V7). Fixed in `745dd68` (2026-08-18: "mis-dated 22,807 files by a century").

**Decision.**
- The date convention is inferred **per directory, never per file**, as the
  dominant pattern (at least 98% of tails valid months for a monthly reading).
- Outliers are left undated with `date_format = 'ambiguous'`, not forced into
  the majority reading.
- A two-digit year is expanded to the reading whose years form the tightest
  contiguous span, per directory (`naming.infer_two_digit_epoch`): 2000–2070
  for projpop, 1996–2023 for SIM.
- A directory whose codes parse equally as `YYMM` and `YYYY` records NULL
  years and raises a question naming it (FINDINGS §4).

Measured after the fix: SIHSUS spans 1992–2026, zero files date before 1990,
and exactly two files are undated.

**Alternatives.** "Any outlier proves annual", rejected above; per-file
inference, rejected as incoherent within a directory.

**What would reverse it.** A directory where the dominant pattern is itself
wrong, which the per-directory question would surface.
