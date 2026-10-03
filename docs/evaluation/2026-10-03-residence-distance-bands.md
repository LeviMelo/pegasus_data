# Residence compared by distance between population centres

**Date:** 2026-10-03.

**Regime:**
- `linkage/levels.py`: a "municipality" comparison now splits different
  municipalities into within 25 km, within 100 km, same state (farther) and
  different state, by the great-circle distance between their Census 2022
  population centres (`geography.municipality_point`);
- national 2022 links on `pegasus_linkage`, run with `link_probabilistic`
  and not stored (`data/logs/distance_test.py`).

**Why.** OQ-63 asks which evidence the model lacks. A residence written as
the neighbouring town is a common error; a residence 500 km away is not.
Before this change both were "same state".

**Learned weights.** m and u are per link, from the data.

| level (residence given the place of care) | bits, SIH deaths → SIM | bits, births → deliveries |
|---|---|---|
| equal, elsewhere | +9.74 | +9.96 |
| equal, at the place of care | +6.85 | +7.33 |
| within 25 km | **+2.70** | **+2.56** |
| within 100 km | +0.73 | +0.56 |
| same state, farther | −1.72 | −2.33 |
| different state | −6.77 | −7.52 |

**Effect:**

| link | stored | with distance bands |
|---|---|---|
| SIH deaths → SIM | 551,005; 21.17 bits; FDR upper 1.03% | 550,703; 22.37 bits; FDR upper 1.03% |
| births → deliveries | 1,529,614; FDR upper 0.74% | 1,531,549; FDR upper 0.74% |

- **The bands carry about 4.4 bits** between a neighbour and a far town.
- **Recall moves little at a 1% FDR:** +1,935 deliveries and −302 deaths.
  The death link's threshold rose; the stored national runs change only
  when relinked.
