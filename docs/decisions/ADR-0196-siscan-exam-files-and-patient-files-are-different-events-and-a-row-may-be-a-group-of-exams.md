# ADR-0196: SISCAN's exam files and patient files are different events, and a row may be a group of exams

**Date:** 2026-10-19. **Status:** accepted. **Request:** give the 15 SISCAN datasets, which had roles and no event type, the event a study can read (ADR-0137).

**Context.**
- SISCOLO/SISMAMA (2006-2015) rows are groups of exams with identical published attributes; the Ministry's TabWin definitions sum `QTDEXA` / `QUANTEXAME` as "Quant. Exames". One 2013-onwards CSV (CITO_MAMA) merges identical exams the same way (`QT_EXAME`); the other four exam CSVs are one exam a row.
- The 2013-onwards CSVs come as the exams by residence and as patients (`_PACNT`): Notas Técnicas 1, 4, 9, 10 and 14 tabulate women and not exams, a woman with several exams in the year counted with her worst result. The patient file republishes the exams the exam file holds.

**Decision.**
1. Two kinds, `exam` and `examinee` (`event_types.KINDS`).
2. Each exam dataset declares event `exam`, weighted by its quantity column where a row is a group (CC, HC: `QTDEXA`; CM, HM, MM: `QUANTEXAME`; SISCAN_CITO_MAMA: `QT_EXAME`) and unweighted otherwise; no status rule (rejected and unsatisfactory samples are exams, as Nota Técnica 3 counts them); identical rows are never removed as duplicates.
3. Each `_PACNT` dataset declares event `examined_patient` (kind `examinee`), consolidated on (`CO_PACIENTE`, competence year): a woman a year. It is another event: the exam files are counted for exams, the patient files for women, and the notes of both say they are never added.
4. `semantic_axes` are declared per dataset (`curation/datasets/siscan.yml`), not for the system: residence for all, the collecting unit's municipality only for SISCOLO/SISMAMA, whose CSV successors publish it empty.
5. 2013-2015 are in both SISCOLO and SISCAN, each neither containing the other (RN 2013-09 by municipality); the datasets say not to add the two.

**Evidence.** `docs/evaluation/2026-10-19-siscan-event-types.md`: `count_events` equals the raw files and TabNet's own base for the 2013 exams of the five CSVs (CITO_MAMA's 666 exams in 604 rows, equal to the kit in 13 of 14 states), the weighted sums of the six SISCOLO/SISMAMA state-months, and the women of five patient files.

**Not done.** Women have no independent figure (TabNet's SISCAN pages fail); no label table is bound to the new result codes; whether an exam is in both SISCOLO and SISCAN is untestable without a key.

**What would overturn it.** TabNet's patient tabulation giving counts of women that differ from the (`CO_PACIENTE`, year) distinct count; a later year where the facility columns of the CSVs are filled (a facility axis would then be declared); an exam key shared by SISCOLO and SISCAN.
