# CNES neurosurgery context fields (2026-11-21)

Regime: branch `cnes-neuro-fields`, shared data home, December registers read through `load_field` (cube caches written).
Declared in `curation/fields.yml` (`cnes:` families `accreditations` and `specialised_services` are new; professionals, beds
and equipment gained groups). No new reader.

| Fields | Codes (source) | 2023 national | Sao Paulo |
|---|---|---|---|
| `cnes_neurosurgeons_{professionals,jobs,hours,hours_sus}` 2008-2023 | CBO 225260, and 223140 before 2011 (CBO 2002 label pack: both "Medico neurocirurgiao") | 7,082 persons; 13,965 jobs; 160,449 h | 743 persons |
| `cnes_neurologists_{professionals,hours_sus}` | CBO 225112, 223142 ("Medico neurologista"; 225350 is the neurophysiologist, not used) | 14,791 | 1,334 |
| `cnes_interventional_radiologists_professionals` 2020-2023 | CBO 225355; absent from the files before 2020 | 1,418 | 136 |
| `cnes_accreditation_{neuro_high_complexity,neuro_reference_centre,stroke_centre,thrombectomy}` 2014-2023 (thrombectomy 2023) | HB SGRUPHAB 1601+1602, 1602, 1615-1617, 1618 (HABILITA) | 288, 36, 109, 13 establishments | 8, 5, 4, 2 |
| `cnes_services_neurology_neurosurgery` 2014-2023 | SR SERV_ESP 105 (SRN_ORD_N) | 785 | 50 |
| `cnes_equipment_{hemodynamics_xray,eeg}[_sus]` | EQ 110 raio X para hemodinamica, 442 eletroencefalografo (EQUIP_TP) | 1,093 (543 SUS); 8,790 | 112; 1,375 |
| `cnes_beds_{neurosurgery,neurology}[_sus]` | LT CODLEITO 09 NEUROCIRURGIA, 42 NEUROLOGIA (ESP_LEIT) | 5,006 (3,595 SUS); 4,619 (3,161 SUS) | 366; 242 |

## Findings

- **HB validity.** In the December files of 2014, 2017, 2020, 2023 and 2024 every row has CMPT_FIM at or after December
  (ended accreditations are absent), so a December row is "in force" and no validity filter is applied. 2 to 39 rows a year
  (0.1 %) start after December (CMPT_INI later) and are counted as CNES registers them.
- **Only 1601, 1602, 1615-1618 occur in the 16xx range of the December files.** The codelist also names 1603-1614 (neurosurgery
  I-III, vascular, functional...), but no December file 2014-2024 holds them; they are not guessed into a group. 1618 first
  appears in 2023. 1601 and 1602 never co-occur (252 + 36 = 288 establishments).
- **CBO 2231 to 2252.** Persons holding 223140 (4,284, 2010) and 225260 (4,214, 2011) are continuous; likewise 223142 to 225112
  (8,854 to 8,551). Interventional radiologists: none under any named code before 2020.
- **No neurological ICU bed code** exists in ESP_LEIT (09 neurosurgery, 42 neurology are the only neuro codes).

## Against an independent figure

Neurosurgeons: 7,082 CNES persons (2023) against 4,145 specialists with title in "Demografia Medica no Brasil 2023"
(FMUSP/AMB), found only in a secondary article (not checked against the report table). CNES is 1.7 times higher, the same
direction as physicians (805,369 against about 570,000): it counts registrations in establishments, summed over municipalities,
including physicians who work as neurosurgeons without the title. An upper bound for comparing places. No published list of
accredited establishments was found to compare the accreditation counts with. Sao Paulo capital 743 neurosurgeons, most small
municipalities none (590 of 5,570 with any), 1 municipality with no CNES record.
