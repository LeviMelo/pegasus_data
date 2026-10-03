# Exact chance agreement on equality, national SIH deaths → SIM

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`, uncommitted ADR-0132 code;
- data home `C:\Users\Galaxy\pegasus_linkage` (2022 lake, stored national
  runs);
- `link_probabilistic("sih_deaths_to_sim", period=2022, geography="BR")`,
  called directly so the stored run is not replaced.

**Script and artifact:** the run's parameters are in
`data/probes/linkage/exact_u_sih_deaths_to_sim_BR_2022.json`, next to the
stored run's u for each level.

**Why.** u(equal) for a rare agreement carried sampling noise (EVALUATION
2026-10-03 "Chance agreement"). Counting it exactly removes that noise. What
matters is whether the link changes beyond that noise.

**Result.**

| | stored (sampled u) | exact u(equal) |
|---|---|---|
| pairs | 551,005 | 551,012 |
| threshold | 21.17 bits | 21.17 bits |
| FDR (upper 95%) | 1.00% (1.03%) | 1.00% (1.03%) |
| u, birth date equal | 4.900e-5 | 4.710e-5 (+0.057 bits) |
| u, death date equal | 2.613e-3 | 2.613e-3 |
| u, sex equal | 0.5027 | 0.5027 |

- **The other levels moved by at most 0.04 bits:** "year off by one" by
  -0.042, "day and month swapped" by 0.023. They are rescaled shares of the
  remainder.
- **Residence given the place of care is unchanged.** It is excluded by
  design.
- **The run took 9.6 minutes.** The stored run took 2.4, but this one ran
  beside a semantics rebuild and two agents' downloads. The exact counts are
  two GROUP BY queries per comparison.

**Reading.** The link is the same within the noise already documented: 7
pairs of 551,005. The gain is that the equality levels are now
deterministic.
