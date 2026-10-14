## ADR-0184: A measure states its unit, or says why it has none; an amount of money names the month it belongs to

**Date:** 2026-10-14. **Status:** active. **Amends:** the role declaration of ADR-0154 (what a numeric column declares).

**Context.** PegaSUS describes every declared measure of a study (mean, quartiles) and must put money in constant reais with the
IPCA of the month the amount belongs to (`price_index`, ADR-0183). The roles of SIH-RD's `VAL_*`/`US_*` and SIA's values said
`kind: number`, `model: mark` and nothing else, and the one place that carried a unit, the ledger's, labelled any money-shaped
column `BRL` by its values: SIH's `US_TOT` is dollars. SIM-DO's `SERIESCFAL`/`SERIESCMAE` (schooling grade) were categories with
no codelist, so every study printed them "(undecoded)".

**Decision.**
- A measure (`kind: number`, `measure` true) declares `unit` from the closed `UNITS` (BRL, USD, days, weeks, months, years, grams, kg,
  cm, ml, g/dL, mg/dL, score, count) with `unit_evidence`, the layout or dictionary line it rests on, and for a `count` `unit_of`
  (what is counted). A measure whose unit no document gives declares `unit_unknown` with the reason, never a unit read from its name
  or values; `undeclared_units()` lists those that declare neither (0 in SIH-RD, SIHSUS-RJ, CIHA, SIM-DO*, SINASC-DN*, SIA's lake
  datasets, PA and the APAC family; 681 elsewhere). `pg.roles` rows carry `unit`, `unit_of`, `unit_evidence`, `unit_unknown`.
- An amount of money (BRL, USD) names the column(s) of the month it belongs to, `competence`: SIH `[ANO_CMPT, MES_CMPT]` (the AIH's
  processing competence, the billing month), SIA `[AP_CMP]` (APAC) or `[PA_CMP]` (PA), the production competence, not the processing
  month `AP_MVM`. Where the currency changed inside the column's years, `unit_from` is the first AAAAMM in the unit: SIH's reais
  from 199501 (1992 cruzeiros, 1993 cruzeiros reais, 1994 both). A nominal amount is deflated by the competence month's index,
  never the year's, and an amount before `unit_from` is not put in reais.
- The ledger's unit is the role's, no longer the money-shaped guess; `pegasus-data roles` shows it.
- A number that is a grade, an ordinal 1-8 read with the schooling level, is `kind: number`, `measure: false`, `domain: [1, 8]`
  (SIM `SERIESCFAL`/`SERIESCMAE`, SINASC `SERIESCMAE`): nothing to decode, nothing to average, no longer reported undecoded. An
  age whose unit a companion column gives per row (`AP_NUIDADE` with `AP_COIDADE`, `IDADEPAC` with `TPIDADEPAC`) is `measure: false`.
- SIASUS-AN's `AN_HB` domain [1, 2] is removed: 99.1% of its 5,652,863 values lie outside it.

**Consequence.** PegaSUS reads `unit`, `competence` and `unit_from` from the roles rows (`fields.declared` builds on them). The US_*
columns other than `US_TOT` and `VAL_ACOMP`/`OBSANG`/`PED1AC`/`UCI`, `AN_TRU`, `ATD_*`, `IDADEPAI`, `PERMANEN` stay without a unit and say
why. Three SIASUS-AN measures (`AN_ALBUMI`, `AN_PESO`, `AN_HB`) carry the layout's unit but their records mix scales (tenths without
the decimal point), stated in their `note`.

**What would reverse it.** A document that gives one of the undeclared units (it is then added, with its evidence), or a currency
change inside a column's years the layout does not state (its `unit_from` moves).
