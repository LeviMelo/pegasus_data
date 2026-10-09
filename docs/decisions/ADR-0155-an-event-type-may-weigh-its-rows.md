# ADR-0155: an event type may weigh its rows

**Date:** 2026-10-09. **Status:** accepted. Resolves OQ-75.

**Context.** Each event type counted one event per row after status and consolidation. In SIA's production files a
row is a quantity of one procedure. PA's consolidated BPA holds up to 95,404 procedures on a row: AC 2023-01 has
95,414 rows and 1,192,449 approved procedures. A row count of PA is not a count of procedures.

**Decision.** An event type may declare `weight: {column, evidence}`. Each row then stands for that column's value in
events.
- `count_events` and PegaSUS's counts sum the weight (`event_weights`).
- A weight that is not a non-negative integer raises: an unknown quantity is not zero events.
- A weight excludes consolidation, which makes a row one event.
- Computations per record (a mark's moments, a link's pairs) refuse a weighted event: its mark (PA_VALAPR) belongs to
  the row.
- A new kind, `procedure`.

**Declared.**
- SIA PA, weighted by PA_QTDAPR, the approved quantity (PA_QTDPRO, the presented one, differs).
- BI, weighted by QT_APROV, and PS and SAD, weighted by PA_QTDAPR. They are PA's I, B and A rows republished with the
  patient's fields, row for row (BI and PS in AC 2023-01; SAD in AC 2014-01 and TO 2015-10, published 2012-2018), so
  they are never pooled with PA.
- Classified by procedure (SIGTAP), with the diagnosis (ICD-10) as the alternative.
- The consolidated BPA records no residence or sex, so a count by residence leaves it unallocated.
- PA's age stratum is PA_IDADE: years, with 998 and 999 missing by its own table. BI, PS and SAD derive `IDADE_anos`
  from IDADEPAC and TPIDADEPAC with SIH's units.
- The month of care is property `competence` in all three.
