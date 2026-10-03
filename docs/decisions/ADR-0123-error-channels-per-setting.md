## ADR-0123: Error channels are estimated per setting, shrunk toward the national ones, in every run

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0107; executes
docs/plans/linkage-theory.md §2.3 (hierarchical channel parameters).
Amends ADR-0120 (T2, scope invariance).

**Context.**
- **SP disagreed with the national run.** The scope test on record keys
  (2026-10-03) found the SP slice of `sih_deaths_to_sim` missing 578 of the
  national run's 134,059 SP pairs. The SE and RR slices were within 0.2%.
- **Not marginal pairs.** Their national scores had a median of 25.6 bits,
  against a threshold of 21.13. In the slice, their records were neither
  linked elsewhere nor taken.
- **The cause is the channel.** The slice estimated m from SP's own 120,000
  anchors; the national run used one m for all of Brazil. SP's channel is
  different. For example:
  - a residence in the same state but another municipality: −1.07 bits in
    SP, −0.05 nationally;
  - a different hospital: −6.26 against −5.27;
  - a birth year off by one: +2.53 against +3.88.
- **Confirmed.** With the national m forced on the slice, it reproduced
  134,059 of 134,059 national pairs.
- **So the national run, not the slice, departed from the theory.** §2.3
  calls for channels per setting, pooled toward the system's. One national
  channel mis-scores a state whose recording differs.

**Decision.**
1. **Each dataset declares its `setting`** in `curation/roles.yml`: the
   municipality role whose state is the unit that publishes the record.
   - SIH-RD and CIHA: `admission.facility_municipality`, since their files
     are by hospital.
   - SIM-DO: `deceased.residence`; SINASC-DN: `mother.residence`. Their
     files are by residence (DORES, DNRES).
2. **Every run estimates m per setting.** A setting's anchors are shrunk
   toward a reference m with `POOL_PSEUDO_ANCHORS` (200) pseudo-anchors.
   - The reference is the national m: the run's own in a national run, the
     stored national one in a slice. So a state's channel is the same
     whichever run estimates it.
   - A setting with no anchors on some comparison scores with the overall
     channel.
3. **Each candidate pair is scored with its left record's setting's
   channel.**
   - u stays national: chance agreement is a property of the comparison
     population.
   - The threshold and the calibration curve stay national.
4. **The run's summary carries `models_by_setting`.**

**Evidence.** EVALUATION 2026-10-03 "Error channels per setting: the scope
test".
- **Slices against the national run:** SE 4,770 of 4,770 identical; RR
  1,217 of 1,217; SP 133,476 of 133,476, plus 2 pairs only in the slice.
  Before: SP disagreed on 578.
- **National yield is unchanged:** 551,181 pairs at an FDR upper bound of
  1.03%, against 551,613 at 1.01%.

**Consequences.**
- **A national run's scores now depend on the record's state's recording
  habits.** That is the point: the same disagreement is weaker evidence
  where it is common.
- **The stored national parameters keep the overall m.** A slice re-derives
  its own state's channel from its anchors, shrunk toward that m. This is the
  same computation the national run makes for the state.
