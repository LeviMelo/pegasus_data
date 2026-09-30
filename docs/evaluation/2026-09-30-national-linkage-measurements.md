# National linkage measurements: bits of identity, error channels, travel flows, SIH/CIHA coverage, join grains

**Date:** 2026-09-30. **Regime:** branch `linkage`, home `~/pegasus_linkage`
(national) and `~/pegasus_fresh` (joins), live FTP. Plan phase A2 (and A1's
OQ-20). Script: `scripts/linkage_study.py` (`bits`, `channels`, `flows`,
`coverage`, `joins`). Artifacts: `data/probes/linkage/*.json`.

**Why these quantities.** They decide what a linkage can achieve before one
is built:
- **Bits of identity:** can a key single out a record at all?
- **Error channels:** how does the same person's data disagree?
- **Travel flows:** how much evidence does place carry, and where must
  geography never filter?
- **Coverage:** does SIH ∪ CIHA cover admissions, and do they overlap?
- **Join grains:** does a row count equal a key count?

All are computed on roles (ADR-0109): on the property a column states, not
on the column.

## Bits of identity (2022, national)

Share of records whose key is unique; bits needed = log2(records).

| dataset | records | needed | key, adding one role at a time → unique share |
|---|---|---|---|
| SINASC | 2,561,922 | 21.3 | birth date + sex 0% · + mother's residence 25.1% · + mother's birth date **97.9%** · + weight 99.96% |
| SIM-DO | 1,544,266 | 20.6 | birth date + sex 0.4% · + residence 87.0% · + death date **99.8%** · + facility 99.9% |
| SIH-RD | 12,520,914 | 23.6 | birth date + sex 0.01% · + residence 44.9% · + discharge date **98.4%** · + facility 99.1% |
| CIHA admissions | 2,591,222 | 21.3 | birth date + sex 0.06% · + residence 37.6% · + discharge date **97.9%** · + facility 99.2% |

- **Per role, SIH:** birth date 14.9 bits, sex 1.0, residence 10.5,
  discharge date 8.7, hospital 11.1.
- **CIHA's residence carries 6.4 bits and is missing in 18.6%.**
- **SIM's death facility is missing in 27.8%** (deaths outside
  facilities).
- **Residence ↔ care place (mutual information):** SINASC 8.3 bits, SIM
  8.0, SIH 8.1, CIHA 6.6.
- **By state (SIH, birth date + sex + residence).** DF is lowest at 15.2%
  unique: one municipality, so residence says almost nothing. RJ 33.4%, SP
  36.8%, SE 61.7%.

## Error channels (SIA-PS 2022, national, true pairs by encrypted CNS)

13,354,137 records, 1,384,491 people, 1,071,384 with several records;
2,386 people appear in several states.

- **Disagreement among people with several records:** birth date 1.04%
  (11,167 people), sex 0.47%, residence 0.95%.
- **Birth-date errors by kind:**

  | kind | people |
  |---|---|
  | unrelated dates | 3,481 |
  | one digit (year / day / month) | 6,018: 2,545 / 1,903 / 1,570 |
  | year differs otherwise | 473 |
  | day and month differ, same year | 470 |
  | day differs by more than one digit | 120 |
  | day and month swapped | 115 |
  | neighbouring digits swapped | 222 |
  | year off by one | 11 |
  | century differs | 4 |

- **Of single-digit errors, 59.9% hit an adjacent key** (numeric keypad or
  top row); 28.9% would by chance. Errors follow the keyboard, not a numeric
  distance: the design principle of ADR-0111's comparison levels,
  confirmed nationally.

## Travel flows (SIH-RD 2022, national)

| care | admissions | same municipality | same state | residence ↔ place (bits) |
|---|---|---|---|---|
| deliveries (0310/0411) | 1,975,469 | 70.0% | 98.6% | 8.6 |
| infections (A, B, J1) | 1,567,105 | 75.7% | 99.1% | 9.0 |
| oncology (C) | 707,675 | **46.3%** | 97.6% | **6.3** |
| all | 12,520,914 | 65.3% | 98.7% | 8.0 |

- **Leading interstate flows:**
  - Goiás → DF: 45,684 admissions;
  - BA → PE: 9,375;
  - MG → SP: 6,551;
  - MA → PI: 6,214.
- **For oncology:** MG → SP 2,551, GO → DF 2,186, MS → PR 1,349, GO → SP 1,273.

Cancer care travels most, which is why candidates are never blocked on
geography (ADR-0107).

## SIH and CIHA admissions (June 2022, national)

- **CIHA by modality:** 1,759,931 records; 215,649 admissions (02),
  1,347,993 individualised outpatient (01), 196,289 consolidated (00). SIH:
  1,034,013 admissions. CIHA's admissions are about 17% of SIH + CIHA.
- **CIHA admissions by payer:** private plan 148,074, private individual
  35,817, public-sector plan 18,897, private company 5,773,
  municipal-financed 3,457, state-financed 2,120, free 1,351. Residence is
  missing in 18.1%. RR published none.
- **Overlap.** 387 CIHA admissions (0.18%) match an SIH admission on birth
  date, sex, facility, start and end: free 133, public-sector plan 98,
  state-financed 74, municipal-financed 71. SIH ∪ CIHA is nearly disjoint:
  together they approach every admission, with a small overlap to remove.

## Join grains (OQ-20; SP and AC 2023-01, AC 2023)

| member | rows | keys | keys with several rows | grain |
|---|---|---|---|---|
| SIH-RD `N_AIH` | 210,225 | 210,161 | 56 | many: each repeat is a principal AIH plus long-stay parts (IDENT 5) |
| SIH-SP `SP_NAIH` | 3,469,842 | 210,161 | 210,118 | many (16.5 acts per AIH) |
| SIH-RJ `N_AIH` | 11,599 | 11,588 | 10 | many (8 long-stay, 2 re-presented) |
| SIA-AQ `AP_AUTORIZ` | 80,069 | 74,756 | 4,551 | many (one APAC, several competences) |
| SIA-AM | 1,065,659 | 1,048,509 | 14,028 | many |
| SIA-AD | 69,397 | 68,671 | 623 | many |
| SIA-ATD | 27,285 | 27,042 | 198 | many |
| SIA-ABO | 760 | 754 | 6 | many |
| SIA-AR, ACF, AMP | 2,723 · 498 · 642 | same | 0 | one |

- **AC 2023, the whole SIH-RD year:** 59,835 rows on 59,782 AIHs; the 20
  repeated AIHs are all a principal plus long-stay parts, each within one
  monthly file.
- **RD 2023 carries AIH types 1 and 5 only.**
- **Written into `curation/joins.yml`** with the measurements.

**Findings for the plan.**
- **Every spine key is identifiable nationally** with one event fact. The
  bits accounting predicts where not: DF and large capitals, on
  demographics alone.
- **The error model is keyboard-shaped**, and nationally measurable from SIA's
  encrypted CNS.
- **The next evidence to add to the model is the travel flows by care
  type** (oncology differs).
