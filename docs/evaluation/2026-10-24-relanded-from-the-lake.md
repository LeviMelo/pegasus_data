# Stale intake units derived again from the lake, nothing downloaded (2026-10-24)

**Why.** Four declared sources held units landed before declaration changes: the month derivation
(`PERIOD_DERIVATION['parts']`), SNGPC-IND's `TP_RECEITUARIO` read as `int_code` (OQ 90), and the yellow-fever and
SRAG declarations. `build_source(fetch=False)` (16ff861) lands such a unit again from its own records in the lake when
they hold every value as filed. The question was whether this changes nothing but what the declarations changed, at no
download.

**Regime.** `scratchpad/reland_all.py` on 16ff861, home `C:\Users\Galaxy\pegasus_core_data`. SRAG was re-run on
24ead55 after a memory fix, and FA-HUM was landed from its source on ee434cc. Totals were compared against the catalog
backup of 2026-10-23.

| source | units re-landed | rows (before = after) | time | fields re-derived |
|---|---|---|---|---|
| SNGPC industrialised | 94 | 528,478,139 | 49 min | sales; sales by CID |
| SNGPC compounded | 34 | 11,758,269 | 47 s | units |
| SISAGUA control: basic, other, outside standard | 13, 1, 1 | 118,949,333; 3,857,900; 867,963 | 20 min | counts; analyses; outside standard |
| SRAG | 10 | 4,666,910 | 2 min | (none declared) |
| yellow fever, epizootics | 1 | 2,637 | 1 s | epizootics |
| yellow fever, humans | 1, then landed from the file | 2,912 | 2 s | 2,904 cases, 1,067 deaths |

**What was found and fixed.**
* **FA-HUM was landed twice over.** The lake held FA-HUM's one file in two families: a leftover of 2026-10-11, 2,911
  rows each. The re-landing read both as the unit's records and wrote 5,824 rows. `_held_records` now takes the
  family written last (ee434cc). FA-HUM was landed from its file, which has 2,913 lines (2,912 records), and its fields
  were re-derived. The doubled state lasted about 30 minutes and no engine run read it.
* **SRAG ran out of memory** under the intake's fixed 2 GB DuckDB limit. The parquet writer's buffers for its roughly 190
  text columns do not spill. The limit is now a decode slot's share of the machine, 7 GB here (be9bde0).
* **Catalog rows naming no file.** 29 such `lake_partitions` rows were removed: 27 from two superseded SIH-RD 2009
  generations, one REGIAO-MUNICIPIO and one more SIH-RD 2009. Reads were already unaffected (the planner re-plans a
  missing file), but the rows claimed SIH-RD 2009 was held. The catalog was backed up first.

**OQ 90, half settled.** `TP_RECEITUARIO` now decodes on every landed month. In 2014-01, 4,543,907 rows, all with
`_MONTH` 1, read 5 / 1 / 2 / 3 / 4 = 2,953,904 / 1,073,743 / 341,651 / 144,096 / 30,513; 2021-10 is likewise
complete. Code 5's label still names GLP-1 for months before GLP-1 entered the SNGPC, so the question stays open on
that window.

**Also found.** A one-month SNGPC query is planned as the whole year ("publication resolution: year"), and rendering a
54-million-row result overflows Arrow's 2 GiB string offsets. Both are being fixed separately.
