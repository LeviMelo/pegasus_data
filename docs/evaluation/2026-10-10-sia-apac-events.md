# SIA's remaining APAC families typed (2026-10-10)

`data/probes/apac/measure6.py` reads one year of each family's raw records. Then `count_events` reads the declared
event through the API. The count that matters is the APACs counted once, because a row is an APAC-month. Regime:
branch `pegasus-core-fixes`, repo data home.

| family | year, state | rows | APACs | type 1 / 2 / 3 rows | type-1 rows on the start month | `count_events` |
|---|---|---|---|---|---|---|
| AB | 2015 SP | 13,141 | 8,223 | 7,783 / 5,358 / 0 | 7,783 of 7,783 | 7,783 |
| ABO | 2023 AC | 34 | 22 | 17 / 17 / 0 | 17 of 17 | 17 |
| ACF | 2023 AC | 28 | 28 | 0 / 0 / 28 | — | 28 |
| AD | 2023 AC | 8,585 | 8,579 | 631 / 8 / 7,946 | 631 of 631 | 8,577 |
| AM | 2023 AC | 43,217 | 15,887 | 15,430 / 27,787 / 0 | 15,430 of 15,430 | 15,430 |
| AMP | 2023 SP | 8,365 | 6,469 | 1,180 / 1,949 / 5,236 | 1,180 of 1,180 | 6,416 |

- **APACs without a type-1 or type-3 row began in an earlier file.** This is the same rule as AQ, AR, AN and ATD.
- **Classifiers follow the columns the records fill.**
  - AD and AM fill AP_CIDPRI on every row.
  - AB, ABO, ACF and AMP leave it 0000: there the procedure, AP_PRIPAL, is the primary classifier.
  - AP_CIDCAS, where it is filled, is the alternative (AB 2015 43%, ACF 50%, AMP 4%).
- **SIA.AB is not bariatric surgery.**
  - Every row read carries 0301120056, ACOMPANHAMENTO DE PACIENTE POS-GASTROPLASTIA (APAC operational manual 6.5).
    The surgery is an AIH, in SIH.
  - ABO continues the same procedure from 2014.
  - `declared.yml` and DATA_SOURCES said "bariatric surgery"; both are corrected.
- **The age stratum was declared and found broken.**
  - The six role files gained IDADE_anos, the stratum the other APACs carry. Through `query(select=["IDADE_anos"])`
    it came back null on every row.
  - Cause: SIA holds two recipes of that name, AP_NUIDADE/AP_COIDADE (APAC) and IDADEPAC/TPIDADEPAC (other layouts).
    `retrieve._derived_inputs` kept only the last, so a narrow projection read the wrong inputs.
  - The name now takes every recipe's inputs. A recipe is skipped where another's inputs are present and its own were
    null-filled.
  - After the fix, AM 2023 AC returns 43,217 ages (0.25-97) and AQ 8,417 (2-103), with none null. PS (the other
    recipe) returns 28,749 (0-113).
  - No PegaSUS count of a SIA dataset was in the store, so no stored result carried the null ages.
