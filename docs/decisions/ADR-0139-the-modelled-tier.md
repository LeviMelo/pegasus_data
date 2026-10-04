## ADR-0139: a modelled tier, typed and versioned, never in place of an official series

**Date:** 2026-10-04. **Status:** active. **Request:** PegaSUS handoff §7 and DESIGN §2.

**Context.** PegaSUS needs estimates any epidemiologist would want as data. Examples:
- the population by municipality, age, sex and race between censuses;
- SINASC and SIM completeness;
- race misclassification;
- the SUS-dependent population.

These are estimates, not observations. pegasus_data's rules forbid recomputing an official series.

**Decision.** A modelled product is written and read only through `modelled.py`:
1. **Place.** It lives under `<lake>/modelled/<product>/<version>/`. A version is never overwritten.
2. **Manifest.** It says `tier: modelled` and gives:
   - the model;
   - every observed input with its data version;
   - each estimate column with its uncertainty columns (an interval or draws), since a point estimate alone is refused;
   - where the validation evidence is written.
3. **Naming.** No product takes an official series' name. POPSVS stays served as published (`load_population`), and an estimate of the population is a separate product beside it.
4. **Shipping.** A product ships only with validation evidence against the baseline it claims to beat. For the population account (§7.2) that means predicting the 2022 census better than RIPSA's pre-census series, by municipality size and age.

**Evidence.** The module refuses an official series' name, an estimate without uncertainty, and an overwritten version.

**Not yet done.** The products themselves (§7.1 sources, §7.2 the account, §7.3 race) are phase 2–3 work.
