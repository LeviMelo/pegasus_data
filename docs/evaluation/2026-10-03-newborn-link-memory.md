# The national newborn link ran out of memory; u is now counted, not materialised

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- `data/logs/national_all.py`, the seventh link
  (`sih_neonatal_admissions_to_sinasc`, BR 2022).
- The machine has 32 GB of RAM.

**What happened.**
- The six other national links finished in 1.6–13.3 minutes.
- The newborn link ran for over 30 minutes without finishing. Its process
  held 40.8 GB of private memory, with 0.3 GB of physical memory free, so it
  was paging.
- The process was stopped.

**Cause.** ADR-0120 took the u of evidence-only comparisons from the real
candidates. The code fetched every candidate's compared values as one Arrow
table (`_levels_of` → `fetch_arrow_table()`), and then computed the levels.
For the newborn link that is tens of millions of pairs, including the
admission's list of up to ten diagnoses.

**The fix.**
- `_distributions_stream` counts each level batch by batch, a million rows
  at a time, and keeps only the counts.
- The counts are exact: the same u as before.

**Checked on identical data.**
- Sergipe 2022, own parameters, the previous commit's code against the new:
  - the same 691 pairs, with the same bits per pair;
  - the same threshold, 12.53 bits.
- Peak memory with the new code: 1.9 GB, in 11 s.

**A side observation.** Sergipe's newborn link now keeps 691 pairs at an FDR
upper bound of 1.05%. In the morning's test it kept 524, but the national
births → delivery link it inherits AIH numbers from was then still keyed
by blob and row, so no inherited value matched. With record keys, "AIH
within 10 of the mother's delivery AIH" is worth +4.15 bits.

The national newborn link is rerun with the fix in the ADR-0121 relink.
