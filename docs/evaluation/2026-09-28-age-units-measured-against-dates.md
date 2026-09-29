## 2026-09-28 — Age units measured against the records' own dates: SIM's layout document is wrong, and SINAN hides plain years

**Question.** What does each age-unit code mean in SIH, SIM and SINAN? The
converter (`_age.py`) had taken them from layout documents, which disagree
with each other and are partly garbled in extraction. The user asked for one
fractional `IDADE_anos`, so every sub-year unit now needs its exact meaning,
not just "under a year".

**Regime.**
- Live home `~/pegasus_live/home`, seeded (ADR-0067), branch `redesign` after
  `6e4e3d4`.
- Data: `fetch("SIM-DO", uf="AL", years=2022)` (23,122 records);
  `fetch("SIH-RD", uf="AL", years=2023, months=1)` (14,340);
  `fetch("SINAN-DENG", years=2022)` (1,405,095).
- Scripts inline in the session. The method is reproducible from this entry:
  compute the true age from the record's dates, then divide by the stated
  quantity.

**What was counted.** For each unit code:
- the number of records and the range of the stated quantity;
- the true age from the record's own dates, as days per stated unit: birth to
  death (SIM `DTNASC`→`DTOBITO`), birth to admission (SIH `NASC`→`DT_INTER`);
- for SINAN, the birth year (`ANO_NASC`) against the year of `DT_SIN_PRI`.
  SINAN-DENG's current files carry no full birth date; see the correction
  below.

The dates are independent of the age field, so they are the ground truth
available here.

**Result: SIM** (`IDADE`, 3 characters, all 23,122 records).

| unit digit | n | quantity | days per unit, median (p10–p90) | meaning |
|---|---|---|---|---|
| 0 | 31 | 1–52 | 0 | **minutes** |
| 1 | 107 | 0–23 | 0 (0–0.08) | **hours** |
| 2 | 253 | 0–28 | **1.0** (1.0–1.0) | **days** |
| 3 | 189 | 1–11 | 35 (31–47) | months |
| 4 | 22,244 | 1–99 | 368 (366–371) | years |
| 5 | 284 | 0–16 | age ≈ 103.6 years | 100 + years |

`sources/sim2025.txt` (Estrutura do SIM, 07/2025) states "1 = minuto, 2 =
hora". **The data says 0 = minutes, 1 = hours, 2 = days.** `999` occurs once
(unknown). No quantity of `000` occurs.

**Result: SIH** (`IDADE` + `COD_IDADE`).

| unit | n | quantity | days per unit | meaning |
|---|---|---|---|---|
| 2 | 692 | 0–30 | 1.0 | days |
| 3 | 215 | 1–11 | 33.5 (31–42) | months |
| 4 | 13,426 | 1–99 | 370 (366–381) | years |
| 5 | 7 | 1–9 | age ≈ 105 | 100 + years |

This agrees with the USP dictionary (`sources/sih_batch/usp_dict.txt`).

**Result: SINAN-DENG 2022** (`NU_IDADE_N`).

| leading digit | n | quantity | year-of-onset − birth year − quantity | meaning |
|---|---|---|---|---|
| 4 | 1,372,774 | 1–122 | 0 or 1 | years |
| 3 | 8,257 | 1–11 | infant | months |
| 2 | 5,492 | 1–30 | infant | days |
| (none) | **11,505** | 0–103 | **0 (0–1)** | **plain years, no unit digit** |

11,505 values (0.8%) are one to three characters long ("24", "7"). They carry
no unit digit, and they match the birth year as years. The old packed decoder
read "24" as unit 2 (days) × 4: a 24-year-old became four days old.

**Consequences.**
- The converter was rewritten on these tables (ADR-0070).
- `IDADE_anos` is fractional years for SIH, SIM and SINAN.
- SIM `000` and `999` are unknown.
- SINAN values under four characters are plain years.
- The completed-years rule (ADR-0064) is superseded.

**Also found on the way.**
- `SINAN-TUBE` 2022 was refused as a representation conflict. The chooser
  compared containers (`zip`), not what they hold (`csv.zip`, `json.zip`,
  `xml.zip`), and a stored conflict row it had written itself kept gating
  after the fix (ADR-0071).
- A `MissingColumnError` message is garbled: "column 'DT_NASC' is not present
  in family X lacks DT_NASC". Fixed: the call site now passes family ids.

**Correction (2026-09-28, the same day).** A first draft of this work said
"public SINAN files carry only the birth year". That generalised from one
dataset, and the user recalled full dates of birth in SINAN. The catalog and
the harvested documents give this picture instead:
- The notification form collects `DT_NASC` (`sources/dic_notif_indiv.txt`).
- A Ministry technical note on a public export states that the birth date is
  "configurada para ANO_NASC (classificação como dado pessoal sensível)"
  (`sources/nota_chagas.txt`).
- Every SINAN file on the server, whatever its data year (1999 onward), is
  dated 2021-11 or later. The archive was rewritten after the LGPD took effect
  (2020-09), and no earlier version survives on the tree.
- In the current files, 63 of 98 SINAN families carry `ANO_NASC` only, and 7
  still carry `DT_NASC`: BOTU 2007–15, COLE 2007–19, TETN 2014–20, DERM 2019,
  IEXO 2006, and a 2023 PRELIM SIFC. So the reduction was applied unevenly.

What the pre-2021 files carried cannot be measured from today's tree
(OQ-56). The recorded fact is in `DATA_SOURCES.md`.
