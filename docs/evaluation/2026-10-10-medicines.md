# Medicines under a condition's codes: SIA APAC AM and BNAFAR (2026-10-10)

Regime: branch `medicines`, data root `pegasus_core_data`, `concepts.dispensed` / `stock_by_state` / `sources/bnafar.py`.
Scripts: none kept (`concepts` and `sources/bnafar` are the code); artifacts are the caches `registries/concepts/authorisations_SIASUS-AM_2025.parquet`
and `registries/bnafar/` (981 KB: CATMAT PDMs and items, 297 probed product codes, 101 stock slices).

**SIA AM, 2025, nationally.** 322 DBC files, 1,874.4 MiB downloaded (a 2023 file set is 1.35 GiB, 2025 is the last full year);
`count_events` over the files took 18 min (download dominated), `build_lake` from the cached blobs 478 s: 40,045,528 rows,
27 partitions, 1.83 GB of Parquet; a lake read of the year is 23 s, `count_events` 41 s.
Counted: AP_TPAPAC 1 on 16,563,831 rows, 2 on 23,481,697, no 3 in 2025. The 40,045,528 rows hold 18,340,183 distinct AP_AUTORIZ; the
16,563,831 type-1 rows have 16,563,831 distinct numbers, so `count_events` (the event type's rule, one APAC once) equals the APACs
begun in 2025, and the other 1,776,352 APACs began before (their first row is in an earlier file). The year holds 2,530
(diagnosis, medicine) pairs over 381 diagnoses (2,483 pairs with a four-character diagnosis, 47 with three), every procedure in SIGTAP group 06.
Top pair: E78.0 / 0604360037, 563,823 APACs.

**Under B58, O98.6, P37.1: no APAC.** `dispensed()` returns no medicine and `scanned = {apacs: 16,563,831, cids: 381}`: a measured
absence. SIGTAP agrees independently: `rl_procedimento_cid` (202609) gives B58 20 procedures (12 group 02, 6 group 03, 2 group 09),
O98.6 3 and P37.1 3, none in group 06. Toxoplasmosis treatment is not in the specialised component. The machinery on codes that are:
G20 268,848 APACs (pramipexol 1 mg 83,622, pramipexol 0.25 mg 73,485, amantadina 100 mg 41,262, rasagilina 32,146); E10 512,739
(insulin analogues; rapid-acting, reusable cartridge system 383,633 across E10.0-E10.9).

**BNAFAR through DEMAS** (`sources/bnafar.py`). The filter `codigo_catmat` is an exact string: `BR` + 7-digit CATMAT item + a national
supply-unit suffix. The open CATMAT (Compras.gov.br `modulo-material`, 1,901 PDMs in class 6505, 500 per page) gives the items;
its per-PDM unit numbers are not BNAFAR's suffix (levotiroxina's comprimido is PDM unit 2, BNAFAR's U0042), so the suffix was read
from BNAFAR's rows (SP+RS 2025-06, 3,107 rows: U0042 on 106 products, U0041 on 16) and each (item, suffix) asked for one row
(first try with the PDM unit numbers found no pyrimethamine: 88 probes, 0 hits, a wrong form of the code, discarded). Codes with rows:

| drug (PDM) | item | BNAFAR product |
|---|---|---|
| pirimetamina (10768) | 268158 | BR0268158U0042, 25 mg comprimido |
| sulfadiazina (12314) | 267765 | BR0267765U0042, 500 mg comprimido |
| espiramicina (7021) | 343494 | BR0343494U0042, 1.5 MUI (500 mg) comprimido |
| folinato de cálcio (1930) | 268292 | BR0268292U0042, 15 mg comprimido |

(ácido folínico, PDM 2585, has no comprimido in BNAFAR; topical silver sulfadiazine is a different item and not read.) Corroboration
from outside the search: `sigla_programa_saude=TOXO` ("TOXOPLASMOSE") holds 3,862 rows, of which 3,851 are exactly these four codes
and 11 a Toxoplasma IgG reagent.

Stock by state and month (rows, establishments, month-end quantity in tablets; `monthly`, a lot's last position of the month):
- **2025**: few and scattered, none in Jan-Feb or Oct-Nov: pirimetamina 56 rows in 39 establishments in GO, MG,
  PR, RJ, RO, SP (months 3, 6, 7, 8, 9, 12); sulfadiazina 42 rows, 30 establishments, MG RJ RO SP; espiramicina 28 rows, 21,
  MG MS PR RJ RS; folinato 25 rows, 19, GO MG MS RJ. Peak July, MG: pirimetamina 6,544 tablets in 21 establishments.
  Earlier months (2023-12, 2024-06, 2024-12, 2025-01, 2025-02) hold none of the four, while the table has rows for each of those months.
- **2026-01 to 09**: 38 state-months, up to 7 states a month (ES, MS, PR, RJ, RS, SC, SP).
- **2026-10 (to the 9th)**: 2,079 / 2,065 / 1,306 / 1,672 rows (pirimetamina / sulfadiazina / espiramicina / folinato), 1,228 / 1,134
  / 746 / 974 establishments, all 27 states, month-end quantities 993,189 / 2,040,401 / 1,081,806 / 685,840 tablets; 1,218 of the
  2,079 pirimetamina rows are tagged TOXO. The programme's first appearance (6 rows 2026-01-21) is followed by a single-day load on 2026-10-09
  (3,849 of 3,862 rows): the series is a snapshot of the programme's start, not a month of stock movements.

So BNAFAR cannot give a 2025 series for toxoplasmosis medicines (a handful of reporting establishments in 3 to 6 months); it gives the
October 2026 stock picture by state. A month without a row is a gap, never zero (`monthly` omits it). Cost: about 450 requests at
>= 1.1 s with a browser User-Agent (297 product probes, 101 stock slices of 1 to 4 pages, TOXO 4 pages, the CATMAT PDM list and five PDMs' items and units);
no host failed; BNAFAR answers 1.4-3.6 s per request.

**Left:** SIA AM for earlier years (the lake holds 2025 only; B58 would not appear); the medicines of conditions where AM does hold
codes need their BNAFAR CATMAT (injectable or liquid presentations need their unit suffix: `products(units=)`); SNGPC retail sales and
BPS prices; CATMAT <-> SIGTAP crosswalk (none published; matching is by drug name).
