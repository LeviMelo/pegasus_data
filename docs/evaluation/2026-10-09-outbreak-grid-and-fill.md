# SINAN-SDTA's ill counted by sex and band; SIM-DO's spans against their fill

**Date and regime.** 2026-10-09; pegasus-core-fixes; the repository's own data home; national reads through the lake.
Scripts: `data/probes/p3_outbreaks/grid_totals.py` and `scripts/audit_role_years.py`, plus one `field_fill` call (SIM-DO,
2012–2023).

## The outbreak grid (ADR-0156)

**What was counted, and why.** SDTA's people live in the 21 grid columns (sex × band) and two totals, so a declaration
that reads a column with the wrong sex or band would count the wrong people without failing. The test is the form's
own arithmetic: each band's male, female and ignorado cells must sum to the band's total column, and each sex's bands
to its total.
- **Grid consistency.** The equations hold in every row that fills the grid. The rows that fill it: 2010, 458 of 498;
  2015, 617 of 673; 2019, 571 of 771; 2023, all 1,162.
- **Partial rows.** 0–3 rows a year (2007–2024) leave a single cell blank. The margin NU_F_TOT solves each, and a
  2017 row's blank solves to 42 males aged 10–19.
- **The grid against NU_TOT.** The grid sums to the ill who were interviewed (field 28), not to NU_TOT:
  - 2010: grid 7,694 against NU_TOT 8,628;
  - 2023: grid 18,313 against 19,671, and above NU_TOT in 10 rows.

**Against the published figure.** The Ministry of Health reports 19,671 ill in 1,162 outbreaks in 2023, and 9,586
in 2019 (as cited in the literature). These are NU_TOT's sums exactly, so NU_TOT is the count.
- **The 2023 excess.** PegaSUS counted 19,879 in 2023. The 208 extra people are in 10 outbreaks whose NU_TOT is 0 and
  whose grid holds them.
- **Zero is not a total.** An outbreak has two or more ill, or one for botulism and cholera (Nota Técnica, §2.1), so
  NU_TOT 0 is declared not recorded.
  - It is written in 84 outbreaks in 2022, 116 in 2023 and 135 in 2024, against 0–2 a year before.
  - Only one row in 2007–2024 has a grid above a recorded total (2015). That row's total counts, at unknown sex and age.
- **The count is the published figure plus the people in grids with no recorded total:**
  - 2023: 19,879 (+208);
  - 2019: 9,645 (+59);
  - 2010: 8,746 (+118).

**Through PegaSUS** (`gateway.event_counts('SINAN-SDTA', 'case', y)`; the 2010 and 2019 rows are unchanged by the
total rule; 2023's 106 zero-total outbreaks with an empty grid are now never counted, not zero people):

| year | allocated | sex unknown | age unknown | outbreaks never counted |
|---|---|---|---|---|
| 2010 | 6,866 | 1,797 | 72 | 39 |
| 2019 | 8,440 | 1,182 | 23 | 201 |
| 2023 | 16,819 | 2,404 | 608 | 106 |

- **2019's band split:** 136 under 1, 940 aged 1–4, 548 aged 5–9, 1,383 aged 10–19, 4,459 aged 20–49, 974 aged 50+.
- **Assembly.** The 2015–2023 block assembles on the bands the population and the grid share: 6 bands × 2 sexes,
  80,909 cases.
- **Account population.** Under the account population, which has no band edge at 1, the bands are 0, 5, 10, 20 and 50.

## SIM-DO's declared years against fill (OQ-71)

`field_fill` over every year 2012–2023:
- FONTESINF and NUDIASINF fill records in 2014 only: 1,227,039 and 32,223.
- NUDIASOBIN fills 2012–2015 and nothing after.
- DTCONCASO fills 2012–2013 and 2017–2023 and is empty in 2014–2016.

Their spans are corrected to 2014, 2014, 2012–2015 and 2017–2026, each with its fill noted. A span cannot hold
DTCONCASO's gap, so it keeps the years filled without one.

## SDTA's counts declared (P1)

`data/probes/p3_outbreaks/count_domains.py` (log beside it) read SDTA's 47 undeclared count columns over every year,
2007–2024 (no 2014).
- **What the records hold.** Every value is a whole number, and none sits at a sentinel. At or above 999 are only
  outbreaks' own sizes: NU_ENTR up to 6,190 interviewed, and QT_TOTAL_C at round 1,000–10,028 exposed.
- **What the dictionary says.** Each count is numeric(4) with no code for "not recorded"; QT_TOTAL_C is varchar2(5).
- **What was declared.** Each takes missing [] and domain [0, 9999], or [0, 99999] for QT_TOTAL_C.
- **What remains undeclared.** 11 coded SDTA columns with no table in the form, which the rule leaves undeclared: the
  incubation units, sample results and venue type.

`field_fill` now reports a year whose files could not be fetched or decoded as unread (null records), not as no
publication. The FTP's port 21 was unreachable from 13:40 (DNS answered, and datasus.saude.gov.br answered 200 over
HTTPS), and SINASC's uncached years had been dropping out of the audit silently.


## Aggregate recipes against their datasets' columns

SDTA's withdrawn recipe named columns SDTA lacks. So every recipe's dimensions and bindings were checked against its
dataset's roles.
- **The template's columns.** 31 SINAN recipes named columns their datasets do not have. The generator gave every
  agravo CLASSI_FIN, CRITERIO and EVOLUCAO, which ACBI, AIDA, HANS, TUBE and 24 others lack. A recipe naming a missing
  column cannot be built.
- **The repairs.**
  - Those dimensions were removed.
  - TRAC binds its residence to its own ID_MUNI_RE (its roles: patient.residence).
  - The ESPO (animal epizootics) and NTRA (survey batches) recipes are withdrawn: they have no person and no residence.
- **The check.** `sinan_hepa_municipality_month` builds for 2019 with 40,874 notifications. TRAC's 2019 file was not
  cached and the FTP was unreachable, so it was not built.

## SINASC-DN's declared years against fill, and years a span cannot hold

`field_fill` on PegaSUS's data root, which holds every year: the repo's home lacks them, and the FTP was unreachable.
- **CODPAISRES** fills 2.5–2.9 M records a year, but none in 2014, 2015 and 2017.
- **NATURALMAE** fills none in 2010 and 1.6 of 2.9 M in 2011.
- **DTRECORIGA** fills no record in any year from 2014 to 2023.

**What changed.** A role may now list `unfilled:` years inside its span. They were declared for CODPAISRES (2014,
2015, 2017), DTRECORIGA (2014–2023) and SIM-DO's DTCONCASO (2014–2016, its span restored to 2012–2026). NATURALMAE
starts in 2011.
- **Misspelt keys.** A role key the loader does not know now raises. A misspelt `fill:` had been ignored silently.


## A lake in PegaSUS's data root

PegaSUS's data root had no record lake, so every raw read in a new process decoded the DBC files again.
- **The cost of decoding.** One CIHA state-month (SP 2013-06, 689,806 records) took 22.4–30.6 s in a fresh process.
  A national year (324 files) took 30–60 min, which was most of a link year.
- **The first lake.** CIHA 2015–2022, without labels: 2,488 files, 149.0 M records, 3.9 GB, no errors.
  - A national year now reads in 12.2 s (2016, 18.9 M records); an SP month in 7.7 s.
  - The births-to-CIHA-delivery link for 2015 still took 4,547 s, so decoding was not that link's only cost.
- **`build_lake(dataset, years, root=)`.** It is the command's lake build for callers that are not the command line,
  and a second call keeps every partition (CIHA 2016: 26 kept, 52 s).
- **The decode admission.** It holds every decode while free RAM is under max(4 GB, 15 %), 4.8 GB on this machine. With
  five heavy jobs that floor stalled the 2014 link year for 5.5 h.
- **The admission now waits for a decode's own need.** It waits until free memory covers 30× the source's
  compressed bytes plus 0.5 GB, capped at the floor. A 16.3 MB DBC had peaked at 450 MB (evaluation
  2026-10-05-decode-memory), so most files are admitted under a gigabyte, and SIH's largest at about 3.5 GB.
