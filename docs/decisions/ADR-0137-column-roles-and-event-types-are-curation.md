## ADR-0137: every column has a declared role, and every dataset declares the events its rows become

**Date:** 2026-10-04. **Status:** active. **Request:** PegaSUS handoff §2–§3 (DESIGN §3.2–3.3).

**Context.**
- **A record is not always the event.** An SIH AIH is a billing document, and a SINAN row is a notification.
- **Roles were partial.** Linkage named about 60 columns of 5 datasets, as `entity.property` (ADR-0107). Nothing said which of a record's columns describe the person and which describe the event.

**Decision.**
1. **Column roles.** `curation/roles/<dataset>.yml` gives each column three things:
   - `role` (`entity.property`), from the test "if the same person had a different event, would the value change?";
   - `kind`;
   - `model`.

   Validation (`semantics/column_roles.py`):
   - a **stratum** is only age, sex, race or residence (what a population account carries);
   - an **identifier** is `link_only`;
   - every **linkage role** names a column whose declared role, or `also`, is the same.
   - A column whose meaning no document settles stays `review: draft` with its reason.
2. **Event types.** They sit under `event_types:` of the dataset curation (`curation/datasets/*.yml`, beside `what_one_row_is`). Each has:
   - a `kind`;
   - its classifiers, one primary and any alternatives;
   - a `status`, either the codes that count or the codes that do not, with its evidence;
   - a `consolidation` key.

   `count_events()` applies them, so a count of hospitalisations or probable cases is one rule.
3. **Never guessed.** A status rule comes from the form's or layout's own table. Where none exists (SINAN TUBE, HANS, SIF*, VIOL, ZIKA confirmed cases), no case type is declared.

**Evidence.** `docs/evaluation/2026-10-04-roles-and-event-types.md`:
- SIM deaths, SINASC births and dengue probable cases equal TabNet for 2022 in all 27 states;
- SIH hospitalisations are within 76 of 12.4 million (OQ-68).

**Amended 2026-10-14: a place's model says whether the event happened there.** A `place` column is modelled `where`
when the event, its care or its infection happened there (SIM's place of death, SIH's and SINAN's hospital, SINASC's
place of birth, SINAN's place of infection and notification), and `mark` when the record only names it (SIM's
registry office and death-verification service, SIH's managing authority, travel and exposure places). The infection
and hospital places of 27 SINAN forms had been `mark` beside `where` in SINAN-LEPT and SINAN-IEXO; 98 declarations were
made consistent. PegaSUS reads only `where` places as an event's other supports and care flows: SIM's
death-verification municipality had been read as a field of Alagoas's infarction deaths. A filter of `query(rows=)` on
a column a generation lacks no longer returns that generation as empty: it is skipped unread and recorded as
structurally absent.
