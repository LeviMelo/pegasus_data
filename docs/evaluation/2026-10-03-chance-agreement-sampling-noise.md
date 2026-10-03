# Chance agreement (u) was sampling noise on its most important level

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- `sih_deaths_to_sim`, national 2022. The comparisons are those of
  `4fb2807` (no ADR-0121 comparisons).
- Measured in-session: five draws of u per estimator, sampler seeds varied.

**What prompted it.** The same spec, rerun after the night's performance
changes, gave 547,257 national pairs against 551,181 before. On the SE and
SP slices, every one of those changes was identical pair for pair. Slices,
however, use the nation's stored u; only a national run draws its own.

**The estimator.**
- 200,000 random pairs, over 50,000-record reservoir samples of each side,
  paired by a stride.
- The reservoir draw follows the order rows are scanned in, which the
  materialised tables and state-by-state role builds had changed.

**Noise across five draws** (standard deviation of a level's bits):

| level | u | 200k pairs, 50k reservoirs | 5M pairs, 500k reservoirs | 20M pairs over both whole sides, hashed index |
|---|---|---|---|---|
| birth date equal | ~5e-5 | **0.76** | 0.34 | **0.024** |
| birth date, year off by one | ~1e-5 | — | — | 0.126 |
| birth date, one digit (adjacent key) | 6e-4 | — | — | 0.014 |
| death day equal | 2.6e-3 | 0.06 | 0.04 | 0.004 |
| sex equal | 0.50 | 0.01 | 0.00 | — |

"Birth date equal" weighs about 14 bits in every true pair, and its u
carried three quarters of a bit of noise. The threshold and the clear-best
margins sit inside that.

**The change** (`linkage/probabilistic.py`):
- u comes from 10 million pairs drawn uniformly over both whole sides, by
  hashing an index into the integer ids (0..n-1, ordered by record id).
- It is deterministic for a record set, whatever the row order.
- It is counted batch by batch.
- Slices use the nation's u (ADR-0120) and no longer draw their own.
- 20 million pairs took 50 s per draw; 10 million halve that.

**Result.** National `sih_deaths_to_sim`:
- 551,005 pairs, FDR 1.00%, upper 95% 1.03%, threshold 21.17 bits;
- validations as before: residence 93.91%, died in hospital 98.48%;
- 2.3 minutes;
- SE slice identical under the same stored national parameters.

**What it means for earlier figures.** Every national count before this
change carried this noise; the earlier 551,181 and the 547,257 are two
draws of it. Differences of a few thousand pairs between national runs of
the same spec were not findings. The final national figures (STATUS) come
from the relink with this estimator.
