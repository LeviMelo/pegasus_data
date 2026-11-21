# Cohorts named by a procedure, and a person's next admission (2026-11-21)

**Regime.** `master` after aed0d02 with this change; home `pegasus_core_data`; live runs of `link()`.

**What was added.** A cohort link's codes may name the procedure performed (`match="procedure"`: SIGTAP prefixes on
`admission.procedure`, declared `params.codes.procedure` in `links.yml`), so a cohort is the decompressive craniectomies
or the shunts, not a diagnosis. And `sih_readmissions`: a cohort's admissions to the same person's next SIH admission
of any cause within a year of the discharge. The engine gains two declared outcome options: `first` (a person with
several partners keeps the earliest, where a death's cohort drops a person with two candidates) and `differ` (a role
that must differ in a pair: the index AIH is not its own readmission). SIH-RD's `CEP` and `IDENT` are comparable roles
(`patient.postcode`, `admission.aih_type`); a type-5 AIH (a long stay's continuation) is neither index nor partner.

**Measured.**
- `sih_admissions_to_sim`, Alagoas 2019, `0403010020` (decompressive craniectomy): cohort 16, 8 linked deaths within a
  year, chance 0%; not viable at this size (no held-out validation compares 30 pairs). The mechanism runs; a state-year
  is too small.
- `sih_readmissions`, Pernambuco 2019, `0403010101` (ventricular shunt): 283 persons with a next admission within a
  year, 5 control pairs (chance 1.77%, upper 95% 4.12%); held out: same municipality of residence 283/283, same race
  211 pairs at 99.53%; viable at every horizon (7 days 178 pairs, 30 days 217, 365 days 283). A pass on the
  municipality in place of the CEP found 35 pairs against 38 by chance and was removed.
- What a partner is: 178 of the 283 began within 7 days of the discharge, 98% of them in the same hospital, often a
  clinical or multiple-surgery code (0303040157, 0415010012): an AIH opened for the same stay when the procedure
  changed. Counting readmissions joins consecutive AIHs into an episode by the discharge reason first (`links.yml`).

**Stays (same day; OPEN_QUESTIONS #96 resolved).** An event type may consolidate by a chain: a person's record
continues the previous one when it starts within `gap_days` of its end and that one closed with a stay reason at the
same facility or a transfer. SIH-RD's `stay` chains AIHs by birth date, sex and CEP, reasons 21-29 and 31, one day:
Pernambuco 2019-2020 971,336 stays against 1,065,304 hospitalisations (principal AIHs, unchanged; TabNet's
"Internações"). A stay crossing the period's edge is cut there.

**Surgery to radiotherapy (same day; OPEN_QUESTIONS #97 resolved).** `sih_admissions_to_radiotherapy` links a tumour's
admission to the first radiotherapy APAC (SIA-AR, its roles now comparable) whose pathology date falls within 60 days,
by sex and CEP. The control shifts the day by 180, beyond the window. Against every cancer's APACs the pass found 606
pairs and 310 by chance; the cohort's codes now filter the APAC's treated topography too (`params.codes.partner`):
São Paulo 2021, C71: 177 pairs, 11 by chance (6.2%, upper 11.1%: use with caution), the same municipality of
residence 177/177 and the APAC's age within a year of the SIH birth date 98.9%, neither a key. A national side read
state by state skips a state-year the catalog lists no file for (Amapá's radiotherapy 2021), recorded in the table's
`unpublished`; a listed file not read still raises.

National linked mortality for a procedure cohort (`sih_admissions_to_sim`, decompressive craniectomy, Brazil 2019):
viable at 30 days (1,075 pairs, 12 by chance) and 90 (1,348, 47), use with caution at 180 and 365 (chance 13.8% at a
year); in-hospital deaths' certificates in hospital 98.9%, in the hospital's municipality 99.2% (995 pairs).
