## ADR-0035: Joins are declared as keys with each side's grain, not as dataset pairs

**Date:** 2026-08-21. **Status:** active.

**Context.** How datasets connect existed only as prose inside gotchas ("joins
to SIH.RD on the AIH number"), readable by a person and by nothing else
(`docs/history/pegasus_data_ARCHITECTURE.md` §14.8). Declaring pairs explodes:
the CNES code alone would be sixty-odd. What decides whether a join is correct
is the key's identity and each side's grain. `SIH.RD` is one row per AIH and
`SIH.SP` many; joining them and counting rows counts professional acts, not
admissions. CNES is versioned by competence, so joining a 2015 admission to
today's CNES answers "what is this hospital now". Added in `aafb874`
(2026-08-21).

**Decision.**
- `curation/joins.yml` declares **keys**: AIH (4 datasets), CNES (18, as-of
  competence), APAC (10).
- Each member carries `rows_per_key`. `unmeasured` is allowed and is a
  statement about our evidence, not about the data.
- `as_of` names the versioning axis.
- What is **not** established is recorded under `not_established`: a
  longitudinal SISCAN patient (`CO_PACIENTE` exists only in `SISCAN.PACNT`),
  SIH deliveries to SINASC births (no shared key; any link is probabilistic
  record linkage, which is a re-identification method and out of scope),
  SISPRENATAL to SIH or SIA.
- `verify` check 19 keeps every key column measured against
  `schema_presence`, and skips rather than passes when nothing is decoded.

**Alternatives.** Dataset pairs. Rejected: they explode and omit grain.

**What would reverse it.** Nothing foreseen. The file later also carried typed
relations (ADR-0044). All ten APAC members were still `unmeasured` at the last
count (ARCH §22.4).
