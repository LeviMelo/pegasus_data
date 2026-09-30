## ADR-0107: Record linkage is a query, finds candidates by intrinsic properties, weighs evidence in bits learned from the data, and reports its own error

**Date:** 2026-09-30. **Status:** active. **Plan:** `docs/plans/linkage.md`.

**Context.**
- **The ladder.** pegasus_data connects values to meanings (labels), values to
  entities (registries, bridges, crosswalk; ADR-0100…0104) and records to
  records through published keys (`curation/joins.yml`). It did not connect
  records about the same person across systems: DATASUS's public files carry
  no common person identifier. SIH has no patient CNS, and SIA's encrypted CNS
  matches only within SIA.
- **Deterministic linkage with negative controls works where a shared event
  exists.** omnisus's study (EVALUATION 2026-09-30, "What omnisus teaches")
  linked RR 2022 with measured chance rates:
  - SIH in-hospital deaths → SIM: 0.1%;
  - SINASC deliveries → the mother's admission: 1.9%;
  - demographic keys alone (SIM → SIA): 58%.
  
  A negative control (the same join with a key shifted, whose pairs are
  coincidences by construction) separates the two cases, which look alike by
  raw pair count.
- **Identification is a budget of bits.** Measured on SIH-RD SP 2023-01
  (210,225 admissions; 17.7 bits single one out):

  | key | bits | unique |
  |---|---|---|
  | birth date + sex | 15.5 | 6.4% |
  | + municipality | 17.3 | 70.0% |
  | + discharge date | 17.7 | 98.5% |

  The separate bits sum to 36.9; the difference is mutual information,
  chiefly residence ↔ hospital (71.2% treated in their own municipality,
  99.2% in their own state).
- **Errors are symbol operations, not numeric noise.** Among 91,943 people
  sharing an encrypted CNS in SIA-PS SP 2023-01:
  - 51 carry two birth dates;
  - of the single-digit differences, 15 hit an adjacent key and 8 another key (about 30% would be adjacent by chance);
  - 6 differ in day and month within the same year;
  - 1 swaps neighbouring digits.
- **Scale is not the obstacle it seemed.** National compressed downloads for
  2023:

  | dataset | size |
  |---|---|
  | SINASC | 239 MB |
  | SIM-DO | 242 MB |
  | SIH-RD | 955 MB |
  | CIHA | 353 MB |
  | SIA-PA + BI | 46 GB (the only giant) |

  Blocking on birth date + sex leaves about 180 admissions and 23 deaths per
  block nationally: about 270 million comparisons for SIH × SIM per year.
- **CIHA completes the admissions.** CIHA carries birth date, sex, residence,
  dates, CNES and death flag. SP 2023-01: 580,210 records, 454,301 paid by
  private plans.

**Decision.**
1. **A link is a query.** `link(spec, period, geography)` uses the planner,
   fetch path and lake; "national" is a geography. Links persist in the lake
   with provenance: source blobs, spec version, model version, measured rates.
2. **Candidates come from intrinsic properties** (birth date, sex, mother's
   birth date, birth weight), with typo-tolerant variants drawn from measured
   error channels and several keys combined. Geography is never a filter; it
   is evidence through learned travel flows.
3. **Evidence is measured in bits.** Each comparison contributes
   log2(P(obs | same) / P(obs | different)). Dependence between fields is
   modelled by conditioning (facility given residence), not by assuming
   independence. Before running, feasibility is computed: bits available
   after errors against bits needed to single out a record.
4. **Meaning is declared; numbers are learned.**
   - Declared, in `curation/roles.yml`: which column states which property of
     which entity (roles), and which facts are impossible.
   - Learned and measured: error channels, frequency weights, travel flows,
     blocking keys and thresholds.
5. **Self-supervision.** True pairs come from exact identifiers inside
   systems; false pairs come from negative controls. Models are trained on
   both by minimising cross-entropy and judged on fresh controls and on
   held-out variables.
6. **Every linkage reports its error and a verdict,** with thresholds fixed
   before results:
   - **viable**: every kept pass ≤ 5% estimated chance and the strongest
     held-out agreement ≥ 90%;
   - **use with caution**: ≤ 20% and ≥ 75%;
   - **not viable**: otherwise.

   A pass whose control finds as many pairs as the pass is dropped. A
   non-viable linkage raises instead of returning pairs.
7. **People, not pairs.** Resolution enforces cardinality (born once, dies
   once, one delivery per pregnancy) and temporal order (no care after death).
8. **Record identity.** A record is `(_blob_sha256, member, _row)`. The blob
   store is content-addressed, so the identity survives re-downloads.
9. **Flagship: the pregnancy spine.** Births ↔ delivery admissions (SIH and
   CIHA) ↔ infant, fetal and maternal deaths ↔ neonatal admissions.
10. **Records.** Every measurement is an evaluation entry, every method choice
    an ADR, and every unresolved question an OPEN_QUESTIONS row. The plan's
    progress table is kept current.

**Consequences.** A new package `src/pegasus_data/linkage/` behind the API,
the CLI and later `serve/`. A roles layer in the curation. `_row` added to
decoded tables. Linkage scenarios in `scripts/live.py`.
