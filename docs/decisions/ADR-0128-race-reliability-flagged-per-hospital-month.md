## ADR-0128: SIH race is flagged per hospital and month, by measured rules; never relabelled

**Date:** 2026-10-03. **Status:** active. Resolves OQ-66.

**Context.**
- **Two hospital practices produce SIH's excess "asian" (`RACA_COR` 04).**
  EVALUATION 2026-10-03 "SIH's excess asian":
  - a **default fill**, where code 04 is given to everyone, whites and
    blacks included (CNES 2499363, CE: 90–97% every month of 2022);
  - **SIM's code for brown written into SIH's field**, where SIM numbers
    brown 4 (CNES 2705982, SP: 03 unused until 2022-08, fixed by
    2022-10).
- **Nothing was relabelled.** Recoding 04 as brown would be a guess for every
  hospital not measured. OQ-66 asked for the rule and how to expose it.
- **What counts as implausible.** People of Asian origin are about 0.4% of
  Brazil's population (Census 2022). Across SIH-RD 2022, among 43,945
  hospital-months with 30 or more admissions, the share coded 04 has a
  median of 0, a 90th percentile of 2.4%, a 99th of 25% and a 99.9th of 85%.

**Decision.**
1. **`race_reliability(table)`** (`quality.py`, exported) adds
   `RACA_COR_reliability`, judged per (CNES, month of discharge):
   - **`unreliable`:** 04 is over 50% of the hospital-month (default fill),
     or brown (03) is under 1% while 04 is over 10% (the swap signature);
   - **`suspect`:** 04 between 10% and 50% otherwise;
   - **`ok`:** neither;
   - **`too_few`:** fewer than 30 admissions in the hospital-month.
2. **The raw code stays;** the flag says what to read with care.
3. **It is computed within the result.** SIH publishes by the hospital's
   state and month, so a query of a state's months holds each hospital-month
   whole.

**Evidence.**
- **SIH-RD 2022, national:**
  - the either-rule flags 329 hospital-months in 64 hospitals (89,003
    admissions);
  - the default rule alone flags 124 hospital-months in 24 hospitals, and
    the swap rule alone 236 in 50;
  - 1,297 hospital-months in 278 hospitals are suspect.
- **The function, CE and SP 2022:**
  - all of CNES 2499363's months with 30 or more admissions are
    `unreliable`;
  - CNES 2705982 is `unreliable` through 2022-08, `suspect` in 2022-09 and
    `ok` from 2022-10: the software fix, month by month.

**Consequences.**
- **A race analysis over SIH can exclude or reweight flagged
  hospital-months,** and say how many.
- **The rules are specific to code 04.** The 928 hospitals that record most
  of SIM's and SINASC's blacks as brown are a different question: the
  direction of that disagreement is not tested.
