## ADR-0125: An establishment's attributes are read from CNES.ST at the record's own month, through `query()`, and an empty attribute says so

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0045, ADR-0100.
Supersedes the lake-only path of the CNES attribute enrichment.

**Context.**
- **The question the registry gets wrong.** `joins.yml` names it: joining a
  2015 admission to today's CNES record answers "what is this hospital now",
  not "what was it when the patient was treated".
- **The enrichment for it existed** (`CNES.TYPE`, `NATURE`, `LEGAL_NATURE`,
  `OWNERSHIP`), matching each record's competence month in CNES.ST. It could
  not run, for two reasons:
  - **It demanded the `cnes_registry` resource.** That is the compiled
    establishment-name history, which the attribute path never reads. Every
    attribute request on an install without it failed with "query requires
    missing local resource(s): cnes_registry".
  - **It read CNES.ST from the lake only** (`api.scan`), so it failed with
    "no lake data for system='CNES' series='ST'" until someone built the
    national CNES.ST lake by hand.
- **An empty attribute read as "matched".** `ESFERA_A` is published, and
  empty, in 2022: all 8,512 Sergipe admissions of 2022-01 came back
  `matched` with a null value.
- **Four attributes only.** CNES.ST carries what hospital-level analysis
  needs: management, SUS link, bed counts, and obstetric, neonatal,
  emergency and surgical installations.

**Decision.**
1. **CNES.ST is read through `query()`** (ADR-0073), at the query's own
   period and geography: the lake when built, the publications (or the
   mirror, ADR-0122) otherwise. It is filtered to the establishments the
   records name.
2. **No resource is required** for an attribute enrichment.
3. **An attribute that is empty that month resolves as `not_recorded`.** It
   is counted unmatched, never as a value.
4. **Thirteen attributes join the four**, each a CNES.ST column published in
   2022, read as of the record's month:
   - `CNES.MANAGEMENT` (`TPGESTAO`), `SUS_LINK` (`VINC_SUS`),
     `PROVIDER_TYPE` (`TP_PREST`), `CARE_LEVEL` (`NIV_HIER`), `CLIENTELE`
     (`CLIENTEL`);
   - `HAS_HOSPITAL_BEDS` (`LEITHOSP`), `SURGICAL_BEDS` (`QTLEITP1`),
     `CLINICAL_BEDS` (`QTLEITP2`), `COMPLEMENTARY_BEDS` (`QTLEITP3`);
   - `HAS_EMERGENCY` (`URGEMERG`), `HAS_OBSTETRIC_CENTRE` (`CENTROBS`),
     `HAS_NEONATAL_UNIT` (`CENTRNEO`), `HAS_SURGICAL_CENTRE` (`CENTRCIR`).

**Evidence.** EVALUATION 2026-10-03 "Establishment attributes as of the
record". SIH-RD Sergipe 2022-01, 8,512 admissions:
- **Matched:** type, management, SUS link, surgical beds, obstetric centre
  and neonatal unit, all 8,512.
- **`not_recorded`:** ownership and care level, which are empty in 2022.
- **Time:** 101 s with the first CNES.ST fetch; 16.5 s with it cached.

**Consequences.**
- **An attribute is as current as the record.** A hospital that changed
  type between two admissions is reported as it was at each.
- **A national query reads CNES.ST nationally for its months.** A built
  CNES.ST lake makes that fast.
