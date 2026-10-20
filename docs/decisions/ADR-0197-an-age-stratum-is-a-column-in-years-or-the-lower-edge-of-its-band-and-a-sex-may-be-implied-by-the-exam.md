# ADR-0197: an age stratum is a column in years or the lower edge of its band, and a sex may be implied by the exam

**Date:** 2026-10-19. **Status:** accepted. **Request:** the engine places and standardises events through `stratum` roles; `gateway._strata` raised "no age stratum" for all 15 SISCAN datasets.

**Context.** The engine reads the age stratum as a number of years (`TRY_CAST` of the column) and the sex by the labels of the codes present. Five SISCAN datasets hold the age only as a band code (SISMAMA's `CO_FX_ETAR` in CM, HM, MM; `CO_FAIXA_ETARIA_PACIENTE` in CITO_MAMA; `CO_FAIXA_ETARIA` in HISTO_COLO), two hold the age in years under the name of a bracket, and SISCOLO's cervical files (CC, HC) have no sex column.

**Decision.**
1. A dataset's age stratum is a column holding years (`unit: years` with its evidence) or, where the file holds a band, a derived column `IDADE_faixa_anos`: the band's **lower edge** in whole years, made by the `band` encoding of `_age.years_column` from a `lookup` (code to edge) on the band column's variable note, taken from the source's own band table and proved against an age in years where one exists. A code outside the table is null; a lower bound, never a guess inside the band (as CIH's decades). A band table belongs to a column of a dataset family: SISMAMA's and SISCOLO4's differ, and the recipe is SISMAMA's.
2. A file with no sex column may declare `implied_sex` (1 or 2) with `implied_sex_evidence` beside its other dataset declarations (`dataset_implied_sex`, `dataset_facts(...)["implied_sex"]`). It is never a column and never a default; a dataset with a sex column does not declare it. SISCOLO's CC and HC declare 2 (the exam is of the cervix).
3. The result codes confirmed by counts (`CO_LAUDO_CITOPATOLOGICO`, `NU_LAUDO_HISTOP`, `CO_LAUDO`, `TP_LESAO`, `TP_LESAO_CARAT_NEOPL_MALI`, the age bands) are bound as the column's own code table; a column whose two datasets disagree on its table (`TP_AVALIACAO_AMOSTRA`) or whose names are swapped (SISCAN_HISTO_COLO_PACNT's squamous and glandular results) is not.

**Evidence.** `docs/evaluation/2026-10-19-siscan-event-types.md`, "Strata and labels": 13 of 15 datasets return residence, sex and age from `gateway._strata`; CC and HC return implied sex 2 with the engine's one line; the derived ages sum to the events (666, 596, 1,210).

**Not done.** The engine's one line for implied sex lives in pegasus_project. A lower edge puts SISMAMA's first band (up to 10) in the engine's under-one class; the datasets hold no one that young.

**What would overturn it.** An age band whose lower edge misplaces many events in the engine's bands (a coarse band across several of its classes); a dataset whose engine reading must tell an unknown sex from an implied one.
