# Sentinel sweep: not-recorded codes per column (2026-11-23)

**Regime.** Real home `pegasus_core_data`, master f6f325fb..06a70f75; read through `open_lake()` (one reading per year).
Script and outputs: `data/probes/sentinel_sweep/` (`sweep.py`, `sentinel-sweep-2026-11-23.md` and `.csv`, every column-year
in `-allcolumns.csv`; the declarations by `declare.py` from `cands.json`).

**Why.** A code that means "not recorded" counted as a value is an invisible error. `field_fill` gave SIH-RD's CID_MORTE
share 1.0 while every record from 2015 held '0000' (2fba6333). The question was how many such columns there are.

**What was counted.** 150 datasets with a roles file and lake data (32 more have no lake data), 5,801 coded columns
(category, code_tree, place, institution), 13,528 column-years (first held year, 2015, last; three dataset-years cut to
one state above 20 M rows). For each column: values not in its codelists (exact width), fill-shaped values (2+ zeros,
2+ nines, symbols), and the modal value's share. 224 undeclared fill-shaped values in 182 columns.

**Declared** (`missing:` in 54 roles files, 127 columns, each with its evidence in a comment):
- the codelist itself labels the value not recorded: S_CID '0000' "CID NAO INFORMADO" (SIA CID columns, SIH-RJ, SIH-SP);
  RACA_COR '99' "SEM INFORMAÇÃO" (12 SIA series); CBO2002 '000000' "Não informado" (SINAN ID_OCUPA_N, SIH-SP); SIM's
  occupation '000' "IGNORADO";
- the value is no code of the column's codelist and fill-shaped: zero or nine CNES codes (AP_UNISOL, SINAN ID_UNIDADE,
  SINASC CODESTAB), municipality and birthplace fills (SIM NATURAL '000'/'999', SINAN ID_MN_RESI '9999999'), SIGTAP
  '0000000000' (SIA-AB AB_PRCAIH2/3), CNAE zeros, stray symbols.

**Left as values** (a real state, or no source decides): PA_INCOUT/INCURG '0000' "Sem Incremento", PA_REGCT "SEM REGRA
CONTRATUAL", DESTINOPAC '00' "Permanência", CNPJ_CC zeros "SEM CESSAO DE CREDITO", maintainer CNPJ zeros (no maintainer),
TP_ATEND '00' "LAUDO GERAL", ESCFALAGR1 '00' "Sem Escolaridade"; SUBFIN, FONTE_ORC, GESTOR_COD, SERV_CLA, TPUPS, IMUNO,
GRAU_HIS '99'/'00' undecided. Five columns already carry `missing_unknown` and were not touched. The 1,377 constant-dominant
columns (one value at least 95%) are mostly recorded constants (SIM_NAO "Não", PAIS "BRASIL"): `field_fill`'s `modal_share`
shows them; none was declared on dominance alone.

**A defect found on the way.** `field_fill` and the event grid looked roles up by `dataset_key`, which names SIA.AQ
"SIA-AQ" while its file is SIASUS-AQ: every SIA dataset's declared codes were ignored. Both now use `declared_columns`
(the role files' resolver), as does `chain_sql`'s person check. SIA-AQ SE 2019 (18,309 records): AP_CIDCAS filled 1.0
before, 0.0 after (all '0000'); AP_RACACOR 1.0 to 0.848 ('99' in 15.2%).
