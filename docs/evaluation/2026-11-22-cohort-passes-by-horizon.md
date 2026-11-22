# A cohort link's passes judged horizon by horizon (2026-11-22)

**Regime.** Real home, commit after b6e86fa (LINKAGE_VERSION 5). `linked_deaths("SIH-RD", ["0403010314"], years=2019,
geography="BR", match="procedure", link_name="sih_admissions_to_sim", refresh=True)`: chronic subdural haematoma
drainage, Brazil 2019. Reported by the ABNc science session.

**The defect.** A pass was kept or dropped on its chance share over the whole window. The main pass (birth date, sex,
residence, day of death in the year after the admission) found 1,049 pairs with 365 coincidences (34.8%) and was
dropped. The run then linked 303 of 5,025 persons, every one an in-hospital death. It reported a 30-day mortality of
5.6% at 0% chance, called viable: every death after discharge was lost, silently. The aneurysm cohort lost the pass the
same way (30.1%), and craniectomy kept it (15.5%). A cohort with few deaths after discharge has many chance pairs per
true one within a year, even when its 30- and 90-day pairs are mostly true.

**The rule (`engine._pass_reach`).** A cohort pass is kept as far as it is admissible at every horizon (7, 30, 90, 180,
365 days): pairs found, fewer coincidences than pairs, chance under `chance_drop`. It contributes its pairs and its
coincidences within that reach only. A horizon past a pass's reach names it (`short_passes`) and is at most "use with
caution": deaths only that pass would find are missing there.

**Result.**

| Horizon | Pairs | Coincidences | Chance | Verdict |
|---|---|---|---|---|
| 7 days | 146 | 6 | 4.1% | use with caution |
| 30 days | 444 | 30 | 6.8% | use with caution |
| 90 days | 649 | 91 | 14.0% | use with caution |
| 180, 365 days | 650 | 91 | 14.0% | use with caution, past the main pass's 90-day reach |

- 650 persons linked, against 303. The main pass reaches 90 days; the discharge-day pass reaches the whole window.
- 30-day mortality is 8.8% (444 of 5,025; 414, or 8.2%, less the chance pairs), against the 5.6% of in-hospital deaths.
- 90-day mortality is 12.9% (558 less the chance pairs, 11.1%).
- 30-day mortality after drainage of a chronic subdural haematoma is reported at roughly 5-10% in the literature, so
  8.8% is in range; the earlier figure was the in-hospital part only.
