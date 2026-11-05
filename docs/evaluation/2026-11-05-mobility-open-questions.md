# The mobility layers' three open questions, and ANAC's re-stamped file (2026-11-05)

Regime: `pegasus_core_data` as built on 2026-10-25 (ADR-0211), code at af84b94 and this change; read 2026-11-05.

**ANAC's file is re-stamped, not re-released.**
- **What the server showed on 2026-11-05.** `Dados_Estatisticos.csv` had Last-Modified 2026-11-05 and first line
  "Atualizado em: 2026-11-05".
- **What the bytes show.** The size was the same 361,057,599 bytes as on 2026-10-25, and ranged reads of the middle
  and the tail equal the held file; the data still ends in 2026-09.
- **Change.** A date therefore says nothing about a release. `anac_air.build` now compares the size and 16 ranged
  windows after the first line (18 s), and downloads again only when they differ.
- **Correction.** The 2026-10-25 note said the file "is replaced about the 20th of each month"; it is corrected there.

**OQ 94: Brasília's ignored work codes are commuting between its administrative regions.**
- **The code.** Of the DF residents working "em outro município" (V0660 = 3), 96,623 of 113,076 (weighted) carry
  `8888888` in both V6602 (UF) and V6604 (municipality). That is IBGE's "Não sabe UF nem país estrangeiro", the
  entry the documentation prescribes when the person cannot name the place (Descrição das variáveis, V0660).
  - DF holds 96,623 of the country's 242,628 such workers; Goiás holds 3,511.
- **Commute time and daily return** (V0662; V0661 = 2 leaves V0662 blank) tell the readings apart:

  | DF workers | Not returning daily | 30-60 min | 1-2 h |
  |---|---|---|---|
  | in the own municipality | 3.0% | 33% | 14% |
  | in another municipality, coded | 31.2% | 25% | 14% |
  | in another municipality, ignored | 4.3% | 50% | 25% |

  - **Graded explanation (strong).** The ignored workers return home daily like those working inside the DF, not
    like those coded to another municipality, and travel the long metropolitan trips between satellite towns and
    the Plano Piloto. They are best read as commuting between administrative regions of the one municipality,
    which is no inter-municipal edge.
  - **Not ruled out.** A share of genuine don't-knows; no IBGE note states the rule.
  - **Effect on the layer.** It is right to leave them out, and `commute_work_2010` out of Brasília is not 85%
    short.

**OQ 95: the 2020 gap is LATAM's November-December.**
- **Month by month.** The Anuário 2021 edition (`anuario_2021.zip`, Fig 3.9: each 2021 month and its change on 2020)
  gives the Anuário's 2020 months. Against the file's paid domestic passengers, every month agrees within 0.1%
  except two: November (Anuário 4,792,940, file 4,413,051) and December (5,642,530, 5,232,835).
- **By airline** (Fig 3.11/3.12: 2021 minus the change):

  | Airline | Anuário 2020 | File 2020 | Difference |
  |---|---|---|---|
  | Azul | 14,105,122 | 14,105,122 | 0 |
  | Gol | 16,216,083 | 16,216,444 | +361 |
  | Latam | 14,489,055 | 13,736,486 | −752,569 |

- **Reading.** The open file lacks about 750 thousand of LATAM's domestic passengers in November-December 2020.
  The layer keeps the file's figures and does not fill the gap.

**OQ 96: the book's tables are not the workbook's.**
- **Rebuilt from the workbook.** Tabela 3 (waterway frequency by REGIC 2007 class of either end, note 2) was rebuilt
  from the workbook's own VAR01/VAR02:

  | Class | Workbook | Printed |
  |---|---|---|
  | Centro Local | 8,835.75 | 10,260.0 |
  | Metrópole | 3,629.5 | 3,748.5 |
  | Centro de Zona | 1,488.5 | 1,635.3 |
  | Centro Subregional | 1,559.25 | 1,608.3 |
  | Capital Regional | 1,775.75 | 1,168.0 |

  - Capital Regional lies above the book; the others below. No hierarchy mapping closes this.
- **Road totals differ too.** The workbook's road total is 1,146 below the book's.
- **The book contradicts itself.** It prints RS = PR = 260,613.3.
- **Reading.** The printed tables were computed on another version of the data. The layer reproduces the published
  workbook (65,638 pairs, the top pair, the seven countries).
