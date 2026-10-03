# SIH's excess "asian" is two hospital practices: a default fill, and SIM's numbering written in

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`
  (lake 2022 with record keys; stored national links).
- Scripts:
  - `scripts/race_settings.py 2022 BR`, artifact
    `data/probes/linkage/race_settings_BR_2022.json`;
  - `scripts/race_code_swap.py 2022`, artifact
    `data/probes/linkage/race_code_swap_2022.json`.

**Why.** EVALUATION 2026-10-02 (race across systems) found SIH recording as
asian many persons that SIM and SINASC record as brown. The hypothesis was
code mixing. SIM and SINASC number race 1 white, 2 black, 3 asian, 4 brown,
5 indigenous; SIH numbers it 01 white, 02 black, 03 brown, 04 asian,
05 indigenous. Software writing the SIM numbering into SIH's field turns
brown into 04 and asian into 03.

Noise, a swap and a default make different predictions:
- **A swap** moves brown to 04 and asian to 03, and leaves white and black
  in place.
- **A default fill** puts everyone at one code.
- **Noise** spreads across codes with volume.

**Concentration** (`race_settings.py`):
- 908,601 linked persons are brown in SIM or SINASC. SIH records 16,252 of
  them as asian.
- 1,111 of 3,783 hospitals record at least one as asian. The top two
  account for 21%, and 8 hospitals record more than half of their brown
  persons as asian.

**The test** (`race_code_swap.py`). It uses each hospital's raw `RACA_COR`
over all its 2022 admissions, by month. For the persons linked to SIM
(deaths) or SINASC (deliveries), it tabulates the SIH code against the
other system's race.

| CNES (UF) | admissions | brown elsewhere → 04 | white elsewhere → 01 | black elsewhere → 02 | reading |
|---|---|---|---|---|---|
| 2499363 (CE) | 15,871 | 2,883 of 3,176 | 6 of 75 | 0 of 12 | **default fill**: 04 for almost everyone, 90–97% every month |
| 7866801 (MG) | 17,774 | 605 of 669 | 59 of 483 | 32 of 240 | **default fill**: 86–91% every month |
| 2705982 (SP) | 18,873 | 567 of 991 | 2,734 of 2,960 | 328 of 400 | **swap, then a fix** (below) |
| 2362821 (PB) | 4,927 | 472 of 2,573 | 266 of 663 | 12 of 49 | mixed; neither pattern |

**2705982, month by month** (share of all its admissions):

| months | code 03 (brown) | code 04 (asian) |
|---|---|---|
| 2021-12 to 2022-08 | 0.0–0.7% | 18.5–23.5% |
| 2022-09 | 3.1% | 16.1% |
| 2022-10 to 2022-12 | 11.3–17.1% | 2.1–3.6% |

- **Before September 2022 the hospital never used 03.** Its browns sat at
  04, while its whites (92%) and blacks (82%) were coded correctly. That is
  the SIM numbering written into SIH's field for brown.
- **The switch in September–October 2022** is consistent with a software
  correction.
- **The reverse prediction cannot be tested here.** Only 6 persons there
  are asian elsewhere (1 coded 03, 3 coded 04).

**Findings.**
- **SIH `RACA_COR` 04 does not mean "asian" everywhere.** In some
  hospital-months it is a default given to everyone (race not recorded). In
  others it is SIM's code for brown.
- **Both are properties of the setting** (hospital, period), as the theory's
  annotator model treats them. They are not properties of the person.
- **Nothing is relabelled.** A code's meaning is never guessed, and a
  per-hospital recode would be a guess for every hospital not measured.
- **What follows is flagging.** A setting whose code distribution is
  degenerate (one code above 85% for a month) or swapped (brown absent, 04
  at the brown share) is marked unreliable for race. The rule is recorded
  as OQ-66, open.
- **A separate measure, not a finding yet:** 928 hospitals record more
  than half of the persons SIM or SINASC call black as brown.
  `race_settings.py` reports it; the direction (the clerk's checkbox or
  the source system) is not tested here.

## The flag, built (ADR-0128)

Measured over SIH-RD 2022 (`pegasus_linkage` lake), per (CNES, month of
discharge), on the 43,945 hospital-months with 30 or more admissions. Share
coded 04: median 0, 90th percentile 2.4%, 99th 25%, 99.9th 85%.

| rule | hospital-months | hospitals | admissions |
|---|---|---|---|
| 04 > 50% (default fill) | 124 | 24 | 46,878 |
| 03 < 1% and 04 > 10% (swap signature) | 236 | 50 | 47,572 |
| either (`unreliable`) | 329 | 64 | 89,003 |
| 04 in 10–50% otherwise (`suspect`) | 1,297 | 278 | 241,005 |

`race_reliability()` on the 2022 query results:
- **CE:** 495,883 `ok`, 15,853 `unreliable` (all CNES 2499363, whose rows
  are 04 for 14,708 admissions), 3,881 `suspect`, 14,341 `too_few`.
- **SP:** CNES 2705982 is `unreliable` 2022-01 to 2022-08, `suspect` in
  2022-09 and `ok` from 2022-10.
