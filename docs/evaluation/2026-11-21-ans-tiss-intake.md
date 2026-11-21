# ANS TISS (D-TISS) intake: private-plan hospital and outpatient events (2026-11-21)

**Regime.** Branch `worktree-agent-aa340d4e1a7200bdd` off 826e272, a scratch data home (deleted after), `pegasus-data fields` restricted to AC and RR, 2022-2023, by a driver that cuts the intake's units to those two states
(the intake has no state filter). Sources `ans_tiss_{hosp,amb}_{cons,det,rem}` in `curation/intake.yml`; layout and sizes in DATA_SOURCES §15.

**Landed (AC and RR, 2022-2023).** Rows equal the files' own lines less the header in every one of the 240 state-months (the landing enforces it before the swap):

| source | files | rows | note |
|---|---|---|---|
| hospital CONS (events) | 48 | 13,313 | 69 with no residence (also no sex), 0 unallocated; events unique |
| hospital DET (items) | 48 | 93,391 | every item's event is in CONS and every CONS event has items |
| hospital REM | 24 (2023) | 7,380 | |
| outpatient CONS | 48 | 1,734,407 | 10,413 unplaced, 22 unallocated (codes 140000, 350000); 1,723,972 in the field |
| outpatient DET | 48 | 5,103,349 | |
| outpatient REM | 24 (2023) | 742,847 | |

Queried back by `query("ANS-TISS_*", period=...)`: 2022 plus 2023 give the same totals (hospital CONS 5,921 + 7,392; outpatient DET 2,315,853 + 2,787,496). `info` lists the six datasets and the seven fields.
Labels read: modality (`22` as Cooperativa médica), character of care (`1` as Eletivo), pre-established-value flag, CBO as the occupation; TUSS-numbered columns stay as filed.

**Found and fixed on the way.** 2022 hospital DET files the stay length as `1,0` (6,276 values unparsed as integers; now a number with a decimal comma, 0 unparsed). A register field (`rows:`) was read whole
into memory by every build (5.1 million rows for two states): a build now leaves a register as the view it is. A register declared from 2023 (REM) asked for 2022 raised "nothing published": it now answers
empty outside its declared years.

**Known fact, TUSS 40814220 (mechanical thrombectomy, expected from 2022-04).** 0 items with this code in the hospital or outpatient DET of AC and RR for 2022 and 2023 (93,391 and 5,103,349 items; the
neighbouring 4081xxxx procedures are present). The slice is two small states, where the procedure is not expected, so this neither confirms nor refutes the date; a larger state-year is the test (not landed:
the check was held to a small slice).

**Not done.** Roles files (`curation/roles/ANS-TISS_*`) for the six datasets: the fields read through the landing's own bindings; no event type is declared. The TUSS terminologies (23, 57, 41, 39, 50, 76, 52, 24, 77, 36, 60, 79)
are not in the dictionary, so their codes stay undecoded. PLANOS.zip (the plans) is not landed. The full source is 203 GiB zipped (outpatient 197.6), declared on request for the outpatient sources.
