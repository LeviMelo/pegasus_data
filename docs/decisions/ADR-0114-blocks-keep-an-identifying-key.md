## ADR-0114: Every candidate block keeps an identifying key; typo-variant blocks exist and are used only where they add links

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0107 (principle 2), ADR-0111.

**Context.**
- **Geography-only blocks exploded.** ADR-0107 finds candidates by intrinsic
  properties and weighs geography as evidence. Two probabilistic specs still
  had a block of hospital + a day + residence, with no birth date:
  - newborn admissions: tens of millions of candidates in RR (ADR-0113);
  - deliveries: 1.16 million in RR, and hundreds of millions nationally, most
    with positive scores.
  
  Such a block adds candidates without adding the evidence that would
  separate them.
- **Tighter blocks cost nothing.** Deliveries with every block keeping the
  mother's birth date:

  | scope | old blocks | new blocks |
  |---|---|---|
  | RR | 8,433 pairs, 1.16M candidates | **8,447 pairs, 29,825 candidates** |
  | AC | 9,886 pairs | **10,128 pairs**, est. FDR 1.0%, upper bound 1.21% |

  Fewer spurious candidates means fewer runner-ups tripping the ambiguity
  margin.
- **A birth date mistyped in the blocking key is then missed.** The measured
  channel (EVALUATION 2026-09-30, national measurements) says how dates are
  mistyped.

**Decision.**
- **Every block keeps at least one identifying intrinsic key** (a birth date).
  Blocks without one are removed from the delivery and neonatal specs; the
  death and infant-death specs keep blocks without a birth date only where an
  event key (death day + hospital, residence + birth weight) is itself
  identifying.
- **Typo-variant blocks.** A block key may be `[left, right, typo]`. The left
  date then also matches through its plausible mistypings, generated from the
  measured channel (`probabilistic.typo_variants`): one digit replaced by an
  adjacent key, neighbouring digits swapped, day and month exchanged. A
  variant that is not a calendar date is dropped.
- **Used only where it adds links.** On deliveries it adds none:
  - RR: 8,447 → 8,444;
  - AC: 10,128 → 9,969.
  
  A one-digit typo earns ~5 bits where equality earns ~13, so such pairs stay
  below the 1% threshold, and the extra candidates only add runner-ups. The
  spec does not use it; OQ-63 records what evidence would lift typo pairs.
