## ADR-0147: SIA APAC families are event types of kind `authorisation`, counted on the first row of each APAC

**Date:** 2026-10-05. **Status:** active. **Request:** PegaSUS ARCHITECTURE §12 phase 3 ("APAC families").

**Context.** The APAC files (chemotherapy AQ, radiotherapy AR, nephrology AN, dialysis ATD, ...) repeat one `AP_*` block, one row per APAC and competence month, and carry a pseudonymous patient number. PegaSUS reads event types and column roles through pegasus_data (`event_types`, `roles`, `count_events`).

**Decision.**
1. Each of AQ, AR, AN and ATD declares one event type of the new kind `authorisation` (`curation/datasets/declared.yml`, beside the dataset's description; the loader files `SIA` under `SIASUS`, so `SIA.AQ` and `SIASUS.AQ` are one key). An event is **an APAC**: rows with `AP_TPAPAC` 1 or 3 (the first or only row), consolidated on `AP_AUTORIZ`. Later-month rows (type 2) are not events; counting every row would count authorisation-months.
2. Classifiers: `AP_CIDPRI` (ICD-10) primary and `AP_PRIPAL` (SIGTAP) alternative, except **ATD, whose primary is `AP_CIDCAS`** (its `AP_CIDPRI` is `0000` on every row read).
3. Column roles for all columns in `curation/roles/SIASUS-{AQ,AR,AN,ATD}.yml`: residence `AP_MUNPCN`, sex, race and `IDADE_anos` as strata; `AP_DTINIC` the event's start date; `AP_CNSPCN` and `AP_AUTORIZ` link-only.
4. `IDADE_anos` is derived from `AP_NUIDADE` + `AP_COIDADE` with the SIH unit table; `AP_MUNPCN_municipio` maps Brasília's administrative-region codes (2008-2021); **`AP_MNDIF` loses its label** (constant `1`, the label "Sim (houve invasao)" was wrong on half the rows).

**Evidence.** docs/evaluation/2026-10-05-sia-apac-families.md; DATA_SOURCES §1.11.

**Not decided / known weaknesses.**
- Not an incidence of treatment: a regimen is a chain of APACs. `AQ_CONTTR` (continuity S/N) would separate new regimens but the status rule takes one column; a two-column status is not built.
- The year of an event is its **processing year** (file year), as TabNet; `AP_DTINIC` can precede it by up to a competence month (537 of 8,417 AQ AC 2023 rows have `AP_CMP` before `AP_MVM`).
- ACF, AM, AD, AB, ABO and AMP have the same block and could be declared the same way; ACF and AD use `AP_TPAPAC` 3 for nearly every row. Not done here.
- The CNS pseudonym's link to SIH, SIM or SIA-BI/PA was not tested.
