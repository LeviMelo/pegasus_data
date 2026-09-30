# CIHA's residence field tested against SINASC

**Date:** 2026-09-30.

**Regime:**
- branch `linkage`, live FTP;
- data homes:
  - `~/pegasus_fresh` for AC and SE;
  - `~/pegasus_linkage` for BA, PR, MG and SP, 2022.

**Script:** `scripts/ciha_residence_check.py`. **Artifacts:**
`data/probes/linkage/ciha_residence_test_{AC_SE,BA_PR_MG_SP}.json`,
`data/logs/ciha_residence_test.log`.

**Why this was run.** The entry
[private-sector links](2026-09-30-private-sector-links-and-ciha-residence.md)
found that, where filled, CIHA's `MUNIC_RES` equals the hospital's
municipality (`MUNIC_MOV`) in 92–100% of admissions. From that alone it
concluded that the field "is mostly the hospital's municipality" and wrote this
into the curation and into DATA_SOURCES.

The user challenged the inference, and rightly. A high match rate fits two
explanations, and the match rate cannot tell them apart:
- **(a)** the field is filled with the hospital's municipality;
- **(b)** people treated in private hospitals mostly live where those hospitals
  are.

The layout (`sources/ciha/Layout_Arquivos_CIHA.pdf`) defines `MUNIC_RES` only
as "Município de residência". No source supported (a).

**The test.**
- **Pairs.** Births are linked deterministically to CIHA delivery admissions
  (spec `sinasc_births_to_ciha_delivery`). The keys are the mother's birth
  date, the hospital and the day. Residence is **not** a key, so it cannot
  have selected the pairs.
- **Two residences per woman.** Each pair gives two residences for the same
  woman: SINASC's `CODMUNRES` and CIHA's `MUNIC_RES`.
  - Under (b), SINASC also places most of these mothers in the hospital's
    municipality.
  - Under (a), the two disagree, and they disagree exactly where SINASC places
    the mother elsewhere.

**Counted** (2022, deliveries only):

| UF | linked pairs (verdict) | SINASC: mother lives in hospital's municipality | CIHA filled | CIHA filled = hospital's municipality | mothers living elsewhere per SINASC, CIHA filled | … CIHA = hospital | … CIHA = SINASC residence |
|---|---|---|---|---|---|---|---|
| AC | 531 (viable) | 80.0% | 53 | 98.1% | 7 | 6 | 1 |
| SE | 725 (viable) | 35.4% | 508 | **100%** | 330 | **330 (100%)** | 0 |
| BA | 6,518 (not viable) | 58.3% | 5,418 | 93.9% | 2,033 | 84.5% | 15.1% |
| PR | 17,573 (caution) | 58.7% | 10,821 | 94.4% | 4,177 | 86.0% | 13.5% |
| MG | 30,047 (viable) | 56.4% | 25,561 | 95.2% | 11,075 | **89.7%** | 9.7% |
| SP | 69,255 (viable) | 62.9% | 61,297 | 94.3% | 22,788 | **85.0%** | 14.6% |

**Findings.**
- **(b) does not hold for deliveries.**
  - SINASC places 35–63% of these mothers in the hospital's municipality;
    CIHA places 94–100% there.
  - Where SINASC puts the mother in another municipality, CIHA still records
    the hospital's municipality in 85–100% of cases.
  - Linkage error cannot produce this. MG and SP are viable (≤5% chance
    pairs). Even BA's pairs could not turn an 85% disagreement into chance.
- **Not a universal rule.** 10–15% of those mothers do carry their SINASC
  residence in CIHA (SE: none). The field is a mixture: mostly the hospital's
  municipality, sometimes the real residence. Nothing in a record says which.
- **Which form is right is not proven here.** Both are filled at the hospital.
  SINASC's `CODMUNRES` is the residence the official birth statistics use. The
  direction of the disagreement is consistent with CIHA defaulting to the
  hospital, not with SINASC defaulting to anything.
- **Scope.** Deliveries only.
  - For other CIHA admissions, the aggregate 92–100% match fits the same
    behaviour but is not tested. No independent residence exists for them
    except through the death link (SIM), and SE's residence agreement on
    those pairs was 35–60%.
  - Other years are not tested.

**What changed.**
- The curation description of CIHA `MUNIC_RES` and the DATA_SOURCES fact now
  state the tested finding with its scope. The earlier wording rested on the
  match rate alone.
- The earlier evaluation entry carries a correction note pointing here.
- Linkage is unaffected. The probabilistic model learns residence's
  agreement per link from the anchors, so a weak residence carries little
  weight on CIHA links. The deterministic CIHA specs never use residence as a
  key.
