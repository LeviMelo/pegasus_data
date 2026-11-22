# Verification of the revision - paper 5 (violence)

Read: manuscript.txt, supplement, response_2, review_2, violence.json (birth_cert, three_records, terminal, person, placebo_shifts, hospital_race_missing, with_admission, deaths_total), figures 2 and 4, cause definitions in violence.py. Nothing edited.

## 1. "Done" items

| Item | Status | Evidence |
|---|---|---|
| Three records, same deaths | Done | Text: birth to hospital -14 natural, -17 transport, -15 firearm; hospital to certificate +5, -0, -6 assaults; contrasts +0.1 (-4.8; +5.1) and -11.5 (-15.6; -7.3). Recomputed: -14.5, -16.6, -15.0; +5.2, -0.2, -6.3 (all assault); 5.2+6.3 = 11.5. Correct. |
| Title and "darker in life" withdrawn | Done | New title; Discussion argues the opposite. |
| False sentences | Done | The exchange is now asymmetric (Brown to White 0.30 vs 0.13; White to White 0.74 vs 0.46; match). "16-17" now per cause (suicide -15.0 in Table 1). "More steeply" and "net, not darker" removed. |
| Clerk coding | Partly | Third reading stated. Missing race 29%/37% (0.289/0.371) and placebo +12%/-4% (396/3,187; -363/9,564) recomputed. Admission age and gap not done. |
| One population, groups, contrast, intervals | Mostly | Deaths sum to 87,391 = Figure 1. S/T moved; Y10-Y34 separate. Primary contrast declared. Bootstrap intervals. But `natural` in the code is `ELSE 'natural'`, so U, Z and missing causes fall in it; Methods says A00-R99. Figure 3 stays on another municipality set (disclosed). |
| Not done (disclosed) | Rates by birth race, strata, SIM autopsy/informant, size sensitivity, new references. |

## 2. The new central inference

Same admitted deaths, share White at birth / hospital / certificate: natural .561/.416/.468; transport .565/.400/.398; firearm .408/.258/.209; all assault .420/.276/.213; suicide .649/.497/.422.

- Supported as a contrast. Birth to hospital, assaults against natural: +0.2 pp. Hospital to certificate, assaults against natural: -11.5 (-15.6; -7.3); transport against natural about -5.4 (z about 2.2). The cause difference sits mainly on the certificate leg.
- Overstated as equality. The b->h interval is +-5 points, about 40% of the 11.5-point total; suicide (-15.2, se 3.9) and other external (-10.9, se 4.1) have +-8. "The same for every cause" and "whatever the cause" should read "within about 5 points"; for legal intervention and undetermined intent b->h is -8.5 and -10.9 with wide intervals.
- Selection by admission has a free answer not printed: among admitted deaths birth to certificate, assault against natural is -20.7 against -9.3 = -11.4, equal to -11.5 for all deaths found. Add it. (Admitted persons are lighter at birth, natural .56 against .50; say so.)
- **The terminal admission qualifies size and sign, and the Discussion misreads it.** In the admission of death (no chance agreement) hospital to certificate is natural +9.1, transport +5.1, firearm +4.3, all assault +3.5. The assault-against-natural contrast is about -5.6, half of -11.5, and assaults regain White (+3.5) where earlier admissions lose it (-6.3). The Discussion states "the certificate would depart from the last record of life by cause ... it did, by about 11 points": the last record of life gives about 5-6 points, not printed with an interval or n. And "between the last hospital record and the certificate" is wrong: admissions ending 30 or more days before death are not the last record; the gap in time by cause (natural deaths have recent chronic admissions) is untested and could produce part of the leg.
- "the hospital's record was darker than the certificate for every cause" is false for undetermined intent (-1.1) and legal intervention (n=12, hospital .58 vs certificate .25, opposite).

## 3. Rival readings

- Clerks code darker: acknowledged, and the cause comparison is correctly said to carry the inference. But b->h is shared by "reclassified in life" and "clerks code darker" and the design cannot separate them; replace "it was not [darker for them]" by "cannot be separated here".
- Chance-agreement residual: disclosed with its sign. It affects the hospital leg differently by cause (+12% firearm, -4% natural) so the +0.2 contrast is uncorrected; say the direction cannot be signed. Fair.
- Selection by admission: limitation only; add the -11.4 check. Missing hospital race differs by cause (29% against 37%), changing the compared sets; mention.
- The product estimator assumes the chance parts of the birth and hospital estimates are independent; unvalidated, name it as a limitation.

## 4. Other claims and numbers

- "the same deaths" (title, Strengths) overstates: records are unlinked, keyed, about half unfound. Use "deaths with the same key".
- Table 1 intervals no longer exceed 1; found share 43-52% correct; Table 1 -> abstract "-15 to -16" correct (-14.7 to -16.5; firearm -16.5 prints as -16).
- Abstract "assaults no more than the others": -16.4 against -15.4, fine.

## 5. Abstract numbers in a main item

Levels are in Table 1, Figure 2A and 4B. The abstract's contrasts with intervals (-11.5 (-14.7; -8.4), -10.6 (-13.6; -7.6), -11.5 (-15.6; -7.3), "+5 and -6") appear in no table or figure; Figure 4B shows levels only. The display plan's "every abstract number is in Table 1, Figure 2 or Figure 4" is therefore false for them. Add a contrast table (or print the contrasts on Figures 2A and 4B).

## Verdict

**Not yet PASS. Required fixes:**
1. Rewrite the Discussion "departs from the last record of life ... by about 11 points": report the terminal-admission contrast (about -5.6, with n and interval) and its sign difference, and replace "last hospital record" with "an earlier admission".
2. State the birth-to-hospital equality as "within about 5 points" (its interval), not "the same for every cause".
3. Correct "darker than the certificate for every cause" (undetermined intent, legal intervention).
4. Add the admitted-subset birth-to-certificate contrast (-11.4), the unequal missing-race share, the independence assumption and the untested admission-to-death gap.
5. Put the abstract's contrasts and intervals in a main table or figure; align Methods "natural (A00-R99)" with the code; change "the same deaths" in the title and Strengths.
