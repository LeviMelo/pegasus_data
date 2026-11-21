# One reading of a twice-published year, chosen on the files' widths (2026-11-21; ADR-0228)

**Regime.** `master` adc4285 → e5d8088; home `pegasus_core_data`; header census of 3,149 SIM and SINASC files
(`schemas --all-files -s SIM -s SINASC`, widths now in `file_schemas.widths_json`); rebuild by `build --uf` of every
state, then `prune`. Scripts: `data/probes/reading_rebuild/` (rebuild) and the ABNc study's `probes/p05_reading_effect.py`.

**Readings now held.** SIM-DO 2009, 2011, 2013-2017 and SINASC-DN 2006-2012 from the 27 state files; every other year
from the national file. Row counts equal the national files' (SIM 2013 1,210,474; SINASC 2010 2,861,868). SIM 2012
keeps the national file (ten state files lack 17 columns); SINASC 2013-2017 too (state files lack or narrow columns).

**What changed in a count that reads the cut columns** (deaths with S06 on any line under an external cause; births
whose anomaly codes hold a neural tube defect):
| year | SIM before | SIM now | | year | SINASC NTD before | now |
|---|---|---|---|---|---|---|
| 2009 | 80,656 (held twice) | 40,313 | | 2006 | 1,036 | 1,044 |
| 2011 | 42,178 | 42,654 | | 2007 | 1,068 | 1,070 |
| 2012 | 70,487 (held twice) | 45,229 | | 2008-2012 | equal | equal |
| 2013-2017 | 45,908 ... 48,470 | +214, +131, +150, +128, +31 | | | | |

The cut lines cost 0.1-1.1% of a multiple-cause count; the doubled years had doubled it. SINASC's anomaly list loses
little: in 2015-2019 (full width) cutting it at 9 characters would hide 0-4 NTD births a year and no hydrocephalus,
because these codes come first; the national files kept for 2013 (16 characters) and 2014 (9) lose about that.
