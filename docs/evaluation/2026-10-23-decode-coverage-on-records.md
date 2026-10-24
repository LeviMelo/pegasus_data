# Decode coverage on real records, after the metadata work of 2026-10-19

**Regime.** `scripts/decode_coverage.py --root C:/Users/Galaxy/pegasus_core_data`, pegasus-core-fixes `a694f30`,
2026-10-23; artifact `data/probes/decode_coverage/2026-10-23.json`. Every lake family's latest partition, its first
20,000 records through the renderer (`view.render_table`, what `query` applies), every column whose role is coded
(kind category or code_tree). It measures what a reader meets, not what the catalog's stored decisions say: those date from
2026-10-08 and predate the week's curation (they had counted SINAN-DENG 31 columns undecoded; rendered, 1 is).

**Counted.** 81 families, 40 datasets (the others hold no records on this machine), 2 families unreadable (the catalog
lists partitions no longer on disk: REGIAO-MUNICIPIO, one SIH-RD generation). Coded columns holding values: 1,063.

| state | columns |
|---|---|
| labelled ("Label (code)"; every labelled column at 100 % of its cells) | 927 |
| words as filed (SISAGUA's sample points, leptospira serovars, SIES's supplies): read as they are | 70 |
| codes left bare | 66 |
| empty or constant in the sample | 95 |

The 66 bare: CIH-CR's basics (SEXO, COBRANCA, NATUREZA, GESTAO, COD_IDADE, MORTE, FONTE); SINAN-SDTA (TP_LOCAL, the
incubation flags; NU_* are counts with a category role), SINAN-SIFG (TPMOTPARC, TPESQPAR, TRATPARC), SINAN-TUBE
(IN_VINCULA, TRATAMENTO), SINAN-SIFC ANT_IDADE (an age with a category role); SRAG-NOTIF (COD_IDADE, CS_ETINIA, RAIOX_RES,
HISTO_VGM, PAC_COCBO, RES_IGG/IGM/IGA, TP_POV_CT, REINF; several `review: draft`, no document names their codes); SNGPC's
TP_RECEITUARIO (OQ 90) and CO_CID10; SIA's AP_CODEMI and AP_MNDIF on the APAC files, NACION_PAC, PERMANEN, CO_INE;
BNAFAR's CODIGO_CATMAT and TIPO_PRODUTO; SIM's and SINASC's VERSAOSIST/VERSAOSCB (software versions); SINAN FLXRECEBI;
FA's MONITORAMENTO season strings. Open question 3 carries the list.
