# ADR-0154: a number declares whether it is a measurement

**Date:** 2026-10-07. **Status:** accepted.

**Context.** A column of kind `number` is either a quantity, whose sums and logs mean something (length of stay, value,
birth weight, prenatal visits), or a code written in digits (an age packed with its unit, a clock time, a year, an
epidemiological week). Consumers (PegaSUS's mark fields) must tell them apart without naming columns.

**Decision.** `ColumnRole.measure` for every `number`:
- false when its property is in `NOT_MEASURES` (age_coded, year, birth_year, epi_week, onset_week, time);
- false when the column declares `measure: false` (SIH-RD and CIHA `IDADE`, whose property is age but whose value
  packs its unit);
- true otherwise.

**Consequence.** SIH-RD has 39 measurements, SIM-DO 8, SINASC-DN 14, SINAN-DENG 7 and CIHA 4. A newly curated number
is a measurement unless its property or its own declaration says otherwise.

**Addendum (same day): missing codes and domain.** A measurement also declares `missing` (the codes meaning "not
recorded"; `[]` when its layout names none) and, where documented, `domain: [lo, hi]`. A measurement whose `missing`
is undeclared is not to be modelled: its sentinels are unknown. Declared so far from the layouts: SIH-RD's 38
quantities `missing: []` (IT_SIHSUS_1603, numeric, no such code; `TOT_PT_SP` is "Zerado", so not a measurement);
SINASC-DN's Apgar `domain: [0, 10]` (Estrutura_SINASC_2019).

**Addendum: categories.** A category column declares `missing` too. `scripts/propose_missing.py` proposes it from
DATASUS's own labels for one year's values (the codes labelled Ignorado / Não informado), writes it with the labels
as a comment, and leaves undeclared a column whose values carry no label; the proposal is reviewed in the diff.
SIH-RD's categories declared from 2022 (ETNIA 0000, NATUREZA 00; the rest none).
SINASC-DN's and SIM-DO's from 2022. The labels read are the year's values and every other code of the column's
codelists (catalog and curated) of a width the year shows: a code DATASUS defines may be absent from one year
(PARIDADE 9, KOTELCHUCK 6). "Not classified" for null, ignored or absent inputs counts as not recorded
(KOTELCHUCK 6/9, TPROBSON 11).

**Addendum: measurements' domains (2026-10-07).** A measurement with no declared `missing` takes as its `domain` the
range its TabNet band `.CNV` labels as values (the band calls everything outside it "Ign"), with `missing: []`
(`propose_missing.py`, the numbers pass): SINASC-DN's PESO, SEMAGESTAC, IDADEMAE, IDADEPAI, QTDGESTANT, QTDPARTNOR,
QTDPARTCES; SIM-DO's PESO, IDADEMAE, SEMAGESTAC, DIFDATA, NUDIASOBCO, NUDIASOBIN. A band that excludes a value the
files hold as one stays undeclared with both claims written beside it: SIM's QTDFILVIVO/QTDFILMORT (`00` labelled
Ignorado, a real zero) and SINASC's CONSPRENAT (a band borrowed from gestational weeks).

**Addendum: a band bounds only the records that stop at its edges (2026-10-08).** Two band shapes are not a domain:
- a linear `.CNV` (an `L` entry: a display format whose one or two sample codes gave SIA-AN's AN_ALBUMI [1, 2]);
- a band the records run across, meaning an edge value and its outside neighbour are both held: TabNet's display
  width, not the column's (AQ_TOTMAU 1–99 months, the files hold 0 and 100–120).
A code beside an edge that the records do not reach is outside (SIM SEMAGESTAC 99). A column with no value in the
year read is left undeclared. Five earlier domains were withdrawn: SINAN-ACGR HORA_JOR, SIM PESO, SINASC IDADEPAI and
QTDPARTCES, SINAN-IEXO NUTEMPO.
