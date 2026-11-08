# Column documentation sweep: what "undescribed" meant (2026-11-08)

**Regime.** Branch `worktree-agent-a0d4f00248db2ef0c` on master 009e129; a scratch home holding a copy of the shared
catalog, curated with this branch's files (`pegasus-data curate`); the lake read from `C:\Users\Galaxy\pegasus_core_data\lake`.
Every lake Parquet directory's schema was bound to its dataset with `Ontology.bind` and each column looked up in the
curation's variable docs (`load_variable_docs`, `INHERITS` included) and the catalog's `field_documentation`.

- **`DADOS_ABERTOS.DOSES_RESIDENCIA` read 0/16 described, and was documented.** The curation had held 16 entries since
  2026-09-29. `info` and `compendium` compared the Parquet's lower-case column names (`co_dose`) with the curation's
  upper-cased keys (`CO_DOSE`). Fixed in `_info.py` and `_compendium.py`: 16/16. Any dataset whose file spells columns in
  lower case was affected.
  The entries themselves were rewritten: the Ministry's only dictionary is the per-dose one (`dbbni/Dicionario_tb_ria_rotina.pdf`, 60
  variables), not this Parquet's. Three row groups (300,000 rows; 2023, 2024, 2026) read by ranged FTP requests showed that
  `co_estrategia`, `co_racacor`, `co_sexo` and `co_transcricao` hold labels, not codes, that `nu_idade` mixes years, "N meses",
  "< 30 dias" and "80 anos ou mais", and that 30% of rows have `qt_dose` above 1; the earlier text had said codes.
- **Five description-less entries** (SIH `CNES`, `SEXO`; SIM `DTNASC`, `NECROPSIA`, `SEXO`) were single entries with a name,
  codelist and notes but no `description`; there was no second key. Written from IT_SIHSUS_1603 §2 and the SIM `DO`
  dictionary. Three SIASUS entries in `_unobserved.yml` (`SP_COMPLEX`, `SP_DES_HOS`, `SP_PTSP`) remain without one: they are named
  as the SIH `SP` layout names its fields, but `SP_PTSP` is there a points quantity and the entry calls it a participation
  indicator, so each needs its own source check.
- **Lake columns with no documentation, 42 datasets:** all 42 hold the eight pipeline columns (six were already described in
  `_dictionary.py`, `_competencia` and `_source_resolution` now are) and, for intake sources, `__RAW`/`__FLAG` shadows
  (explained in the typed column's notes) and `_MONTH`, `_MUNICIPALITY`, `_READ_ON`, `_SOURCE_PATH`. The only source
  columns left undocumented were SISAGUA CADP (14) and CADT (10); they are now in the shared `sisagua` dictionary of
  `intake.yml`, from `dicionario_cadastro_populacao_abastecida.odt` and `dicionario_cadastro_carro_pipa_populacao.odt`
  (neither was among the dictionaries copied under `registries/sisagua`).
- **Four built context fields with no declaration:** `sisagua_surveillance_cyanobacteria` and `sisagua_surveillance_other`
  are the names of intake *sources*; their fields are `..._cyano_analyses` and `..._other_analyses` (built 2026-10-15,
  against 2026-10-10 for the old directories, which carry the older column layout). `vaccine_doses_residence` and
  `vaccine_doses_establishment` appear in no commit of any branch, hold 2023 only and a layout (`dose_code`,
  `strategy_code`, `document_status`, `deleted`) no current declaration produces. All four are stale.
