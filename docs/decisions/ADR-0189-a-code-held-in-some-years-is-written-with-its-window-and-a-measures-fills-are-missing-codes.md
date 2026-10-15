# ADR-0189: A code the records hold in some years is written with its window; a measure's fills are missing codes

**Date:** 2026-10-14. **Status:** active. **Amends:** ADR-0079 (inline codes had one vintage), ADR-0154 (a measure's missing codes: "no
meaning is given to 99"), ADR-0180 (a default fill is declared), ADR-0184 (`percent` joins the units).

**Context.** Two blind audits wrote papers from study folders (SINASC-DN, microcephaly Q02 in Pernambuco 2012-2019; SIA ATD, N18 in Alagoas
2014-2023) and read tables built on these declarations:
- SINASC `SEXO` is coded `1`/`2`/`0` in 2009, 2012-2013 and 2015-2024, `1`/`2`/`9` in 2010-2011 (878 births) and `M`/`F`/`I` in 2014
  (national files DNBR2009-2024, 44.9 million births). Its labels were the same in every year but `9` (undecoded), and a case-mix table keyed on the raw
  code listed Feminino twice.
- "Not recorded" was 0 and "outside the domain" held the missing values: the 2026-10-08 declarations read `99` of the two-digit fields as outside the domain
  and gave no code to the APAC laboratory fields, whose lines carry fills (ATD `9999` on 14,940 rows, 14,939 with it in five of the six fields at once;
  zero in 17-30% of the rows; mean haemoglobin 18.6).
- ATD's event-type evidence quoted a measurement of AQ (2,921 of 2,921).

**Decision.**
- **A curated code may carry a window.** In `codes:` a label is text, or `{label, from, to}` (`AAAAMM`, an end may be left out): the code decodes in the
  files of those years and is undecoded, visibly, in any other (`curation.inline_windows`, read by `persist.reference`; a request with no period decodes
  every code). `SEXO` of SINASC keeps `1 2 0 M F I` in every year (the 1996-2019 dictionary, the 2019 layout and TabNet's `SEXO.CNV` list them) and writes
  `9` Ignorado for 201001-201112: its births are those of the other years' ignored sex (Q56 on 41-46% against 32-42%; mean weight 2.4 kg against 3.2 kg
  for sex 1 or 2) and replace the `0` exactly where it is absent. The label is the category's identity: a table keyed on the raw value lists `1` and `M`
  apart, a table keyed on the label pools them.
- **A measure's `missing` holds** (a) the codes a tabulation kit or layout labels Ignorado for the field or its sibling of the same concept (APGAR `99`; PESO
  `0000` and `9999`; IDADEMAE `00` and `99`; NUMFILH `99` for the children counts); (b) a code the records hold as a spike no distribution has, written with
  the count and the neighbours it stands above, and where it is the same lines across fields (`99` on 223,344 CONSPRENAT births, nothing else above 80;
  ATD's `9999`; AN's all-nines of each field's width on 9,091 lines); (c) the zero an optional numeric field is exported as, for a quantity whose zero is no
  measurement (haemoglobin, albumin, TRU, phosphorus, PTH, Kt/V, glucose, height, weight, BMI, vessel diameters), in each spelling the records use; never for
  diuresis (an anuria), a count or the transplants. A conflict between a kit's band and the records is written beside the declaration (IDADEPAI `99`).
- **A measure's `domain`** is a document's where one exists (TRU 0-100 by the manual's formula; the kits' ranges); otherwise a plausibility bound of the unit,
  marked as such (haemoglobin 1-25 g/dL, albumin 0.5-7); none where no document gives unit or range (phosphorus, PTH, Kt/V). Values filed at another scale
  (tenths or hundredths without the decimal point: 10, 100 and 1000 are one 10.0 g/dL) fall outside the domain; they are no sentinels. A default that four establishments file in every laboratory field (an albumin of 10 g/dL on 99% of one clinic's authorisations) falls outside the albumin
  domain; their haemoglobin of 10 is not told apart (OQ 82).
- ATD's `AP_TPAPAC` evidence is ATD's own, and the dataset note says what `AP_CIDCAS` and `ATD_CARACT` are (a diagnosis on 12-24% of the authorisations; "caso
  novo" opens a treatment period at the clinic, it is no new patient); the first competence (2014-08) is a gotcha of the dataset, which `info` prints.
- The unit `percent` (TRU is a percentage by its formula).

**Consequence.** On the audit's 904 births, `99` on 5 of `CONSPRENAT` and on 3 each of `QTDFILVIVO`, `QTDFILMORT`, `QTDGESTANT`, `QTDPARTNOR` and `QTDPARTCES` moves from
"outside the domain" to "not recorded"; the rest that the audit saw outside (`APGAR1` 11, `IDADEPAI` 657, `SEMAGESTAC` 14, `CONSPRENAT` 13) are nulls, which PegaSUS counts there
(`_measures` tests the declared codes only: a null or blank belongs to "not recorded", a PegaSUS change). National 2012-2019: 153,019 `CONSPRENAT`, 16,392 `APGAR1`,
12,983 `APGAR5`, 4,117 `QTDFILMORT` move. SEXO of 2010-2011 (878 births, undecoded) decodes. Undecoded and left, for want of a document or a test: `RACACOR` `9`
(2010, 2014), `MESPRENAT` 10, `TPROBSON` 12, `TPDOCRESP` 0 (OQ 83); the scales of the APAC laboratory fields are OQ 82.

**What would reverse it.** A layout that gives `99` or a zero fill another meaning in one of these fields; a second code recoded across years (a window holds
one span a code).
