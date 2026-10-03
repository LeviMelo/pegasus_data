# SIH money is in one unit across every era (Acre, 1992–2023)

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`;
- the microdata are RDAC files read directly from the HTTPS mirror
  (ADR-0122) and decoded with `decode.dbc.read_dbc`;
- TabNet is read over HTTP (`sources/tabnet.tabulate`).

**Script and artifact:** `scripts/sih_money_units.py AC 1992 2023`, artifact
`data/probes/sih/money_units_AC.json`. A Sonnet agent ran it, and the
explanations below were re-checked by hand.

**Why.** OQ-21 asked whether SIH bills in centavos in some eras and in reais
in others. Any value measure spanning eras would then be off by 100 at a
boundary. Counted: per processing year, the sum of `VAL_TOT` against
TabNet's "Valor total". The row count against "Internações" checks that the
two describe the same population.

**TabNet forms.**
- 1992–2007: `sih/cnv/miac.def`, measure `Valor_Total`.
- 2008 on: `sih/cnv/niac.def`, measure `Valor_total`.
- Both read with row `Ano_processamento` and all of the form's files.

**Result.**
- **Money matches TabNet in every year from 1992 to 2023.** The ratio of
  the sums is 1 to about 1e-13, except 2022 (1.000035), 2023 (1.000004) and
  2009 (below). No ratio is near 100.
- **The median `VAL_TOT` per AIH runs from 114 to 526 reais** between 1995
  and 2023 (114.23 in 1995; 413.99 in 2008; 524.60 in 2022), with no step
  of 100. The 1998 and 2008 layout changes leave `VAL_TOT` and `US_TOT`
  unchanged.
- **1992–1994 are in the currency of their day,** and TabNet shows the same
  unrescaled values:
  - 1992 is in cruzeiros (median 434,746);
  - 1993 is in cruzeiros reais (843,532);
  - 1994 mixes cruzeiros reais with reais from July (median 31,927.5);
  - `US_TOT` (dollars) stays at 80–120 per AIH over 1992–1998, so it is the
    comparable measure across 1994.

**Where rows differ, and why.**
- **1999–2018 and 2023: 0.04–0.5% more rows, with money equal.** These are
  long-stay continuation AIHs (`IDENT` 5), which TabNet's "Internações" does
  not count but whose money it does. Without them the counts equal TabNet
  exactly: 2000 gives 44,858 against 44,858, and 2017 gives 44,002 against
  44,002. 2022 is off by one AIH. The same held for SE 2022-01 (EVALUATION
  2026-10-03 "Municipality and procedure dimensions").
- **2009: 9.4% more rows and money.** TabNet's file for September 2009
  (`niac0909.dbf`) returns no table, so its 2009 total omits that month. The
  microdata's September holds exactly the 4,540 missing AIH
  (53,140 − 48,600). Every other 2009 month equals TabNet. The defect is
  TabNet's.
- **February 1994 (RDAC9402) is absent from the mirror and from TabNet**
  alike.

**Found on the way, and fixed (ADR-0133).** `query("SIH.RD")` on a fresh
home returned nothing for AC 2008 and 2010–2012, and one month of 2009. It
planned the XML/CSV representations of those years, which the mirror does
not hold, while the `.dbc` files are there.

**Consequence.** OQ-21 is resolved: `VAL_TOT` sums across 1995–2023 need no
unit correction. Before July 1994, money is in another currency and is not
comparable without conversion; `US_TOT` is. A count of admissions that is
to match TabNet excludes `IDENT` 5.

**After ADR-0133** (fresh home, through the mirror):
`query("SIH.RD", geography="AC")` gives 2008: 46,087 AIH and R$ 22,365,143.69;
2011: 52,269 AIH and R$ 33,510,058.61. Both equal the direct `.dbc` reading.
