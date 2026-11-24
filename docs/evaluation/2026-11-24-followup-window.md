# A follow-up window is known only where the run covers it (2026-11-24)

Regime: stored `sih_admissions_to_sim` runs of the ABNc line (`abnc2027_neuro/work/deaths/`, 2012-2024), read through
`Followup.died_within` and the line's own joins. Reported by the t07 session; fixed in 4f2b8917, 98132b65, e0927413.

- **What was wrong.** `died_within(days)` returned True for a death within ``days`` even when the person was not followed
  that long, while a survivor in the same position was null: a complete-case rate counted the deaths and dropped the
  survivors. Two places produced the uncovered windows:
  - **The data's end.** Origins near the last day of deaths held. The stored ABNc runs end a year after their origins,
    so none changed.
  - **The run's reach.** A pass whose chance matches over the year are too many is kept to a shorter horizon
    (`passes[].reach_days`), or dropped. The run then finds no death after that horizon. Reach of the year pass:

    | Runs | Reach (days) | Year-pass chance |
    |---|---|---|
    | every 0415* AIH (sp0415), 2012-2024 | 90 | 34-38% |
    | chronic subdural | 90 (180 in 2020) | 31-38% |
    | aneurysm | 90-180 | 26-35% |
    | TBI, cranial core | 180 | 22-32% |
    | spine surgery, 10 of 12 years | 0 (dropped) | 48-62% |

    Before, everyone alive at the reach read as alive at 365 days: for subdural, 877 deaths at 90 days and 878 at 365
    (2024).
- **Now.** `Followup.reach_days` is the longest kept pass that is not `known_only` (0 when every such pass was dropped;
  the window for a run stored without its passes). `died_within` is null past the reach or the data's end, a death as
  much as a survival. It reads an event link's `event_data_end`, on which it raised KeyError.
- **The effect** in the line's joins: craniectomy main-route 1-year death 53.53%, against 49.64% when act-route stays
  were counted alive after day 90. Subdural, aneurysm and act-route stays keep no 1-year death. Spine surgery's
  "30-day" death was in-hospital death in 10 of 12 years.
- **Also measured** (the line's joins, not the library): a person matched on birth date, sex and residence to a run
  origin earlier in the year is a namesake by chance in 2.7-4.4% of matches when the origin is in the same hospital,
  and in 22-52% otherwise (birth-date-shift control).
