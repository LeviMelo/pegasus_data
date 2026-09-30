# Private-sector links (CIHA) and what CIHA's "residence" really holds

**Date:** 2026-09-30. **Regime:** branch `linkage`, fresh home `~/pegasus_fresh`
(links) and `~/pegasus_linkage` (June 2022 residences), live FTP.

**What was run.** Two specs added to `curation/links.yml`, the non-SUS twins
of the SIH ones, run with both methods on AC and SE 2022:
- `ciha_deaths_to_sim`: CIHA admissions (modality 02) ending in death →
  death certificate.
- `sinasc_births_to_ciha_delivery`: births → the mother's CIHA delivery
  admission.

Then CIHA's `MUNIC_RES` was compared with `MUNIC_MOV` (the hospital's
municipality) for June 2022 in SE, SP, MG, BA and PR.

**Why this count.** The national coverage study found SIH and CIHA nearly
disjoint (0.18% overlap): SIH ∪ CIHA covers admissions only if CIHA's side
links. The residence check followed from a validation that looked wrong.

**Counted.**

| link | scope | deterministic | probabilistic |
|---|---|---|---|
| CIHA deaths → SIM | AC | 40 of 45, 0% (upper 9.2%), use with caution | 43 of 45, 0% (8.6%), use with caution |
| | SE | 194 of 314, 0% (1.9%), viable | **248 of 314 (79.0%)**, 0% (1.49%), viable |
| births → CIHA delivery | AC | 531 births (3.7%), 0.19% (1.05%), viable | 535, 0.75% (1.91%), viable |
| | SE | 725 (2.6%), 0.69% (1.61%), viable | 718, 0.14% (0.78%), viable |

- **Held-out checks.** Died in hospital 100% in every CIHA death run; obstetric
  diagnosis 98.9–99.6% in every delivery run.
- **Residence agrees only 35–60% in SE.** The CIHA pairs' residence agrees
  with SIM or SINASC in 35–60% of them, against 86–95% on the SIH links.

> **Correction (2026-09-30).** The conclusion below was first drawn from the
> match rate alone. A match rate cannot separate "the field holds the hospital"
> from "private patients live near their hospitals", and no source supported
> the first reading. It was then tested against SINASC on linked deliveries:
> [CIHA's residence field tested against SINASC](2026-09-30-ciha-residence-tested-against-sinasc.md).
> That test supports the conclusion for deliveries and limits its scope. The
> wording in the curation and in DATA_SOURCES now follows the test.

**The residence field.** Where it is filled, CIHA `MUNIC_RES` equals the
hospital's municipality:

| state (June 2022) | admissions | residence filled | filled = hospital municipality |
|---|---|---|---|
| SE | 416 | 197 | 100% |
| SP | 87,192 | 77,000 | 94.6% |
| MG | 28,545 | 26,458 | 92.3% |
| BA | 4,287 | 4,034 | 92.9% |
| PR | 21,799 | 14,706 | 92.5% |

SIH in SP: 71.8%.

**Findings.**
- **The private-sector links are viable** where there are enough records:
  SE with both methods. AC's 45 deaths are too few to certify (ADR-0113).
- **CIHA's residence is mostly the place of care.** Anyone reading it as
  residence would place private admissions at the hospital. The curation's
  description now says so (`curation/variables/ciha/ciha.yml`), and so does
  DATA_SOURCES.
- **The engine absorbed it.** The probabilistic model learns residence's
  channel per link from the anchors, so a residence that is mostly the
  hospital carries little evidence there. The "residence agrees" validation
  is uninformative on CIHA links and is not the strongest check that decides
  their verdict.

**Artifacts.** `data/logs/ciha_runs.log`; stored runs under
`~/pegasus_fresh/lake/links/`.
