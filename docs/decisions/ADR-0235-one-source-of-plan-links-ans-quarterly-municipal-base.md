## ADR-0235: one source of private-plan links for the population without private coverage, ANS's quarterly municipal base

**Date:** 2026-11-22. **Status:** active. **Amends** the product's source (PDA-024 December files, 2021-2025). **Request:** the coordinating session.

**Context.** `population_without_private_coverage` subtracted PDA-024's December links and so began in 2021. ANS's TabNet base `tb_bb` (DBC, quarterly, 2000-2026) holds the same count by municipality, sex and age band.

**Decision.** The product reads `ans_beneficiaries_quarterly` (NR_BENEF_M, the December of each year) throughout, 2000-2025. Before 2010 the account's places are comparable areas: B is summed over the municipalities
each area holds, a post-2010 creation joining its first parent's area. The age bands are the CNV `cd_idade_faixa5` groups, read from the field's declared codes. The intake reads `format: dbc` with the package's decoder.

**Evidence** (evaluation 2026-11-22-ans-beneficiaries-history). December 2021: tb_bb 49,209,906 placed links, PDA-024 49,209,904, one municipality differing by 2; the 2021-2025 product equals `sus-dependent-3` but for 30-38 cells
a year (at most 10 links). Two sources of one count would add a break in the series at 2021 for no gain.

**Not decided.** The 2026 positions (only the September quarter is published) are not used: the account's reference date is 1 August and a December is the position that year's product reads.
