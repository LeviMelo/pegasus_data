# Response to review 2 - paper 5, `violence/`

`analysis/violence.py` now adds:
- `birth_cert`: birth against certificate for one population, with bootstrap intervals;
- `three_records`: birth, hospital and certificate for the same deaths, the product of the birth and hospital estimates death by death;
- `placebo_shifts`: shifts of -14, -7, +7 and +14 days;
- `hospital_race_missing`.

S/T codes move to other external causes, and Y10-Y34 form their own group. The conclusion changed: the difference by cause arises after the hospital record, on the certificate. The change from birth to hospital is the same for every cause.

| Item | Done |
|---|---|
| 1 Same deaths in three records | Done (Figure 4B, Results). Birth to hospital: natural -14.5, transport -16.6, firearm -15.0 points; assaults against natural -0.0 (interval includes 0). Hospital to certificate: natural +5.2, transport -0.2, assaults -6.3; difference -11.5 (95%CI -15.7; -7.2). The title and every "already present in life" claim are withdrawn. The new title is "Where the race of young people who die violently changes". |
| 2 False statements | "Agreed less in both directions" is replaced by the asymmetric exchange: Brown in hospital, certified White, 0.30 natural against 0.13 firearm. "16-17" is now interpolated per cause from `birth_cert`. "More steeply" is removed. "Net, not darker" is removed. |
| 3 Clerk coding | Stated as a third reading. The hospital record is darker than the birth record for every cause, and darker than the certificate at the admission of death for every cause; the inference therefore rests on the comparison between causes. Hospital race missing is reported (29-37%), the empirical null from four placebo shifts is reported (+12% firearm, -4% natural), and the 180-day window is reported. Not done: admission age and gap. |
| 4 One population, groups, contrast, intervals, figures | One municipality set (births 2000-2009) for Table 1 and Figures 2 and 4; Figure 3 stays on the youth tabulation and says so. The cause groups are fixed. The primary contrast is declared (birth to certificate, external against natural), with a difference and its interval. Bootstrap intervals are used throughout the main items. Figure 4B has intervals. The Figure 1 box text fits, and its count (87,391) equals the sum of the groups. |
| 5 Rates, references, wording, ledger | The Introduction's account of who records race is corrected ("often completed by the medical examiner ... records race from the body or from whoever informs it"). "We found no study". The ledger rows are updated. Not done: rates by birth race against certified race; age, cohort and sex strata in the text; SIM autopsy and informant fields; the size-threshold sensitivity; a new literature search for the reference list. |
