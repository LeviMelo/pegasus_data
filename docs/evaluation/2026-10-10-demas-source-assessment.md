# DEMAS open-data API: source assessment (BACKLOG 5.1)

**Regime.** 2026-10-10, commit `d2f6f3f`, `https://apidadosabertos.saude.gov.br` (Swagger 2.0, "DEMAS - API de Dados Abertos"
v1.8.32, 113 paths), the repository's own data home. About 630 requests in all (222 first probes, ~390 measurements, a few
`curl`), one at a time, at least 1.5 s apart, browser User-Agent; the origin files were read from the Portal de Dados
Abertos (below). Scripts and raw output in `data/probes/demas/` (gitignored): `assess.py` (limit 5 at offsets 0 and 5),
`measure.py` (size by galloping/bisecting over offset, limit 1), `portal.py` (the origin files per dataset), `equality.py`
(DEMAS against an origin on slices), `classify.py` (-> `classified.json`, one record per endpoint, and `table.md`).

**What was counted, and why it matters.** BACKLOG 5.1 applies "the most complete source wins" (ARCHITECTURE §2.3): DEMAS is
used only if it serves the original's full breadth (microdata, every column, every year). So for each endpoint: its origin
system, grain, columns, rows, years, and, where an origin can be counted cheaply, whether DEMAS equals it.

## Result

| verdict | endpoints | meaning |
|---|---|---|
| use DEMAS | 35 | no other bulk route (or equal to the origin); 1 verified equal (SIES), the rest "only route, not compared" |
| original, DEMAS fallback | 49 | the origin (DATASUS FTP or Portal file) is complete or DEMAS was found incomplete/defective/unreachable |
| not relevant to epidemiology | 29 | education, ombudsman, HTA, workforce, works, one-off survey |

1. **DEMAS is not the full source on most epidemiological tables.** Of the comparisons below, two matched (SIES, all rows:
   137,914 = 137,914; SISAGUA vigilância, AC 2014: 42 = 42 and 333 = 333) and the rest found a table incomplete (cianobacterias
   10%, carro-pipa 60%, UBS), truncated at 5,000 rows (plano-amostragem, SG leve 2023 and 2024), restricted to 2025-2026 (SIM),
   empty (SINASC) or with a wrong date column (SRAG). This reverses the working assumption that SISAGUA, PNI and the like
   are best read from DEMAS.
2. **Where the origin is a bulk file, the file wins on practicality too.** The API pages 1,000 rows per request, offset is a row
   offset, no total is returned, and deep offsets cost seconds: 1e6 ≈ 2 s, 1e7 ≈ 15-35 s, 3e7 ≈ 42-60 s, and 5e7 returns
   `502 Proxy Error` after 60 s (PNI 2024). Three of the 14 SISAGUA tables (≥ 1e7, 2e7, ≥ 3e7 rows), all seven PNI years (≥ 3e7 each),
   dengue and SISVAN (≥ 3e7) cannot be paged to their end (a filter slice can).
3. **The origin of the non-FTP datasets is the Portal de Dados Abertos do SUS** (`dadosabertos.saude.gov.br`, CKAN; the old
   `opendatasus.saude.gov.br` answers 302 to it). Each dataset page lists yearly or monthly files (CSV/JSON/XML, parquet for
   SRAG 2019+) on `s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/` (SISAGUA 2014-2026 annual zips, PNI monthly zips 2020-2026,
   SIM 1979-2026, SINASC 1996-2026, SRAG parquet, SISVAN 2008-2023, 28 CSV per SG year). Slugs differ from the DEMAS paths
   (`portal.json`).

## Comparisons made

Columns, DEMAS endpoint against the dataset pegasus_data reads (`roles()`, non-derived columns; `column_compare.json`):

| DEMAS | pegasus_data | DEMAS cols | origin cols | shared | only DEMAS | only origin |
|---|---|---|---|---|---|---|
| mortalidade | SIM-DO | 86 | 99 | 83 | cb_alt, opor_do, tp_altera | 16 (codbaiocor, codbaires, codcart, crm, estabdescr, numerodn, tpassina, ufinform...) |
| arboviroses/dengue | SINAN-DENG | 196 | 195 | 195 | acido_pept_c121 | 0 |
| arboviroses/chikungunya | SINAN-CHIK | 125 | 122 | 122 | cs_suspeit, in_vincula, tpuninot | 0 |
| arboviroses/zikavirus | SINAN-ZIKA | 41 | 38 | 38 | cs_flxret, cs_suspeit, flxrecebi | 0 |
| cnes-estabelecimentos / leitos / equipamentos / profissionais / servicos | CNES-ST / LT / EQ / PF / SR | 21 / 10 / 12 / 26 / 18 | 208 / 28 / 28 / 40 / 32 | | | |
| sia- / sih-procedimentos | SIA-PA / SIH-RD | 17 / 17 | 75 / 127 | | aggregates by facility x procedure x month | the record columns |

Rows and years, against an origin counted outside DEMAS (`equality.json`, `equality_followup.json`, `orig_*`):

| slice | origin | DEMAS | reading |
|---|---|---|---|
| SISAGUA cianobacterias, all | 49,288 (Portal CSV, 2014-2026) | 5,000, paged to the end (2014-2025; 2026's 7,236 absent) | 10.1% |
| SISAGUA carro-pipa população / procedência | 2,129 / 1,954 | 1,274 / 1,156 (end verified) | 60% / 59% |
| SISAGUA plano-amostragem; SG leve 2023; SG leve 2024 | 5,000 is the end (offset 4999 yes, 5000 empty) | | a round-number truncation |
| SIES, all | 137,914 | 137,914 (offsets 137913 yes, 137914 empty) | equal |
| SISAGUA vigilância-parametros-basicos, AC 2014, mes 3 / mes 1 | 42 / 333 (2014 file: 1,985,693 rows) | 42 / 333 | equal on the slice |
| UBS, all | 47,989 | 24,001 to 47,987 | incomplete |
| SRAG 2019-2026, all | 4,666,910 (8 parquet files) | 4.22 to 4.5 M | near-complete |
| SRAG 3 rows at offset 3,950,000, found in the 2024/2025 parquet by nu_notific | dt_notific 2024-03-06, other columns equal | dt_notific 2023-12-31 | **dt_notific wrong**: at 5 spread offsets it is 2019-12-29, 2020-12-27 (twice), 2021-12-26, 2023-12-31; the day filter returns 0 for 4 of 5 days tried, anomes_notific=202406 returns 0 (origin 27,996) |
| SIM, 5 offsets 0 to 1,000,000 | 1979-2026 | dtobito all 2025-2026; 1.0 to 1.33 M rows | the latest two years only; dates lose leading zeros (`2082026`) |
| SINASC | 1994-2026 | 0 rows at offsets 0 and 5, again on retry | empty |
| dengue, municipality 110001, 2024 | pegasus_data aggregate 249 | 256 (nu_ano filter) | +7 (+2.8%), unexplained |
| CNES-ST via cnes-estabelecimentos | 223 monthly records of one establishment, 2008-01 to 2026-07 | limit 1000 returns 12 rows; nu_comp=201705 returns 1 | the limit is applied before de-duplication; page by `offset += limit` |

## Endpoints

`DEMAS rows` is exact when "paged to the end", otherwise a bracket from limit-1 probes at 1e3, 1e4... and bisection (">=" is
a lower bound: a deeper probe failed or the measure was spent). The endpoints from BNAFAR onward in the table (about 40) were measured with one 1,000-row
page and two limit-1 probes at 1e5 and 1e7, so their size is an order of magnitude. A short page is not an end on endpoints whose limit
applies before de-duplication (`municipio` returned 860 and more follow).

| endpoint | grain | cols | DEMAS rows | verdict | evidence |
|---|---|---|---|---|---|
| **SISAGUA** (14) | | | | | |
| `sisagua/vigilancia-parametros-basicos` | record (sample x parameter) | 34 | >=10,000,000 | original, DEMAS fallback | Portal annual zips 2014-2026 (13, 85-212 MB, about 2 GB); DEMAS slice uf=AC ano=2014 gives 42 (mes 3) and 333 (mes 1) = the 2014 file, but >=1e7 rows (502 at 3e7): a bulk pull by API is thousands of requests |
| `sisagua/controle-semestral` | record (system / registration) | 36 | 19,870,133 to 22,795,070 | original, DEMAS fallback | Portal annual zips 2014-2026; DEMAS 19.9-22.8 M rows, equality not counted |
| `sisagua/controle-mensal-parametros-basicos` | record (sample x parameter) | 22 | >=30,000,000 | original, DEMAS fallback | Portal annual zips 2014-2026; DEMAS >=3e7 rows (paging wall) |
| `sisagua/pontos-de-captacao` | record (system / registration) | 24 | 2,371,373 to 3,162,277 | original, DEMAS fallback | Portal 1 zip (55 MB); DEMAS 2.4-3.2 M rows, equality not counted |
| `sisagua/cadastro-carro-pipa-populacao` | record (system / registration) | 23 | 1,274 | original, DEMAS fallback | DEMAS ends at 1,274 rows (offset 1274 empty) against 2,129 in the Portal CSV (60%) |
| `sisagua/cadastro-carro-pipa-procedencia` | record (system / registration) | 13 | 1,156 | original, DEMAS fallback | DEMAS ends at 1,156 rows (offset 1156 empty) against 1,954 in the Portal CSV (59%) |
| `sisagua/controle-mensal-amostras-fora-do-padrao` | record (sample x parameter) | 31 | 749,893 to 1,000,000 | original, DEMAS fallback | Portal 1 file; DEMAS 0.75-1.0 M rows, equality not counted |
| `sisagua/controle-mensal-demais-parametros` | record (sample x parameter) | 28 | 2,371,373 to 3,162,277 | original, DEMAS fallback | Portal 1 zip (147 MB); DEMAS 2.4-3.2 M rows, equality not counted |
| `sisagua/controle-mensal-infraestrutura-operacional` | record (system / registration) | 28 | 749,893 to 1,000,000 | original, DEMAS fallback | Portal 1 file; DEMAS 0.75-1.0 M rows, equality not counted |
| `sisagua/controle-mensal-plano-amostragem` | record (system / registration) | 30 | >=4,216 | original, DEMAS fallback | DEMAS stops at exactly 5,000 rows (offset 4999 yes, 5000 empty); Portal annual zips 2014-2026 |
| `sisagua/populacao-abastecida` | record (system / registration) | 37 | 1,333,521 to 1,778,279 | original, DEMAS fallback | Portal 1 zip (77 MB); DEMAS 1.3-1.8 M rows, equality not counted |
| `sisagua/tratamento-de-agua` | record (system / registration) | 63 | 749,893 to 1,000,000 | original, DEMAS fallback | Portal 1 zip (82 MB); DEMAS 0.75-1.0 M rows, equality not counted |
| `sisagua/vigilancia-cianobacterias-e-cianotoxinas` | record (sample x parameter) | 30 | >=4,216 | original, DEMAS fallback | DEMAS stops at exactly 5,000 rows (2014-2025, none of 2026) against 49,288 in the Portal CSV (10.1%; its 2026 has 7,236) |
| `sisagua/vigilancia-demais-parametros` | record (sample x parameter) | 33 | 1,000,000 to 1,333,521 | original, DEMAS fallback | Portal 1 zip (106 MB); DEMAS 1.0-1.33 M rows, equality not counted |
| **SI-PNI** (8) | | | | | |
| `vacinacao/doses-aplicadas-pni-2020` | record (dose applied) | 31 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2021` | record (dose applied) | 30 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2022` | record (dose applied) | 29 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2023` | record (dose applied) | 29 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2024` | record (dose applied) | 48 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2025` | record (dose applied) | 49 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/doses-aplicadas-pni-2026` | record (dose applied) | 49 | >=30,000,000 | original, DEMAS fallback | Portal monthly CSV zips (12 per year); no FTP copy after 2019 (PNI.DPNI ends 2019); DEMAS >=3e7 rows, offset 5e7 gives 502 after 60 s, so a year cannot be paged to its end |
| `vacinacao/esavi` | record (adverse event) | 73 | 316,227 to 421,695 | use DEMAS | 73 columns, 316-422 k rows; no FTP copy (Portal 1 CSV, not counted against it) |
| **SIM** (1) | | | | | |
| `VMA/sistema-de-informacao-sobre-mortalidade` | record (death) | 86 | 1,000,000 to 1,333,521 | original, DEMAS fallback | 86 of the FTP DO's 99 columns (lacks codbaiocor, crm, codcart...); dtobito at 5 offsets spread over its length is 2025-2026 only (FTP DO 1996-2026, Portal 1979-2026); 1.0-1.33 M rows; dates lose leading zeros |
| **SINASC** (1) | | | | | |
| `VMA/sistema-de-informacao-sobre-nascidos-vivos` | record (birth) | - | - | original, DEMAS fallback | returns no rows (status 200, empty list) at offsets 0 and 5 and on later retries; FTP DN 1994-2026 and Portal 1996-2026 hold it |
| **SIVEP-Gripe** (3) | | | | | |
| `VMA/srag-2009-2012` | record (notification) | 108 | 17,782 to 23,712 | original, DEMAS fallback | 108 columns, 17.8-23.7 k rows; the Portal holds 4 yearly files, not counted against them |
| `VMA/srag-2013-2018` | record (notification) | 108 | 42,168 to 56,233 | original, DEMAS fallback | 108 columns, 42-56 k rows; the Portal holds 6 yearly files |
| `VMA/srag-2019-2026` | record (notification) | 194 | 4,216,964 to 5,623,412 | original, DEMAS fallback | 194 columns as the Portal parquet; 4.22-4.5 M rows against 4,666,910 in its 8 parquet files; dt_notific is wrong (2023-12-31 against 2024-03-06 for the same nu_notific, other columns equal) so the day and month filters fail |
| **e-SUS** (6) | | | | | |
| `VMA/notificacoes-de-sindrome-gripal-leve-2020` | record (notification) | 63 | 133,351 to 177,827 | original, DEMAS fallback | 63 columns; 133-178 k rows; the Portal holds 28 CSV for the year |
| `VMA/notificacoes-de-sindrome-gripal-leve-2021` | record (notification) | 63 | 177,827 to 237,136 | original, DEMAS fallback | 63 columns; 178-237 k rows; the Portal holds 28 CSV for the year |
| `VMA/notificacoes-de-sindrome-gripal-leve-2022` | record (notification) | 63 | 237,136 to 316,227 | original, DEMAS fallback | 63 columns; 237-316 k rows; the Portal holds 28 CSV for the year |
| `VMA/notificacoes-de-sindrome-gripal-leve-2023` | record (notification) | 63 | >=4,216 | original, DEMAS fallback | ends at exactly 5,000 rows (offset 4999 yes, 5000 empty): truncated; the Portal holds 28 CSV |
| `VMA/notificacoes-de-sindrome-gripal-leve-2024` | record (notification) | 63 | >=4,216 | original, DEMAS fallback | ends at exactly 5,000 rows (offset 4999 yes, 5000 empty): truncated; the Portal holds 28 CSV |
| `VMA/mpox` | record (notification) | 55 | 74,988 to 100,000 | use DEMAS | 55 columns, 75-100 k rows, no FTP copy; Portal has 5 CSV, not counted against them (check dates as for SRAG) |
| **SINAN** (4) | | | | | |
| `arboviroses/zikavirus` | record (notification) | 41 | 562,340 to 749,893 | original, DEMAS fallback | 41 columns = the FTP's 38 + 3; 0.56-0.75 M rows; FTP complete |
| `arboviroses/dengue` | record (notification) | 196 | >=30,000,000 | original, DEMAS fallback | 196 columns = the FTP's 195 + acido_pept_c121; >=3e7 rows (502 beyond ~3e7); municipality-year slice id_municip=110001 nu_ano=2024 returns 256 against pegasus_data's 249 |
| `arboviroses/chikungunya` | record (notification) | 125 | 2,371,373 to 3,162,277 | original, DEMAS fallback | 125 columns = the FTP's 122 + cs_suspeit, in_vincula, tpuninot; 2.4-3.2 M rows; FTP complete |
| `arboviroses/febre-amarela-humanos-primatas-nao-humanos` | record (human case / NHP event, season) | 14 | 2,913 | use DEMAS | 14 columns of its own (monitoramento, se_is, obito), none shared with the FTP's SINAN-FAMA (19); about 2,900 rows |
| **SVSA** (2) | | | | | |
| `arboviroses/febre-amarela-epzootias` | record (epizootic occurrence) | 10 | 2,637 | use DEMAS | 10 columns, about 2,600 rows, 1999-2026; no other public route |
| `VMA/svsa-populacao-residente` | aggregate (municipality x sex x age x year) | 5 | >=10,000,000 | original, DEMAS fallback | 5 columns, >=1e7 rows, years from 2006; pegasus_data already reads POPSVS 2000-2025 (TabNet's denominator) |
| **LEITOS** (1) | | | | | |
| `assistencia-a-saude/registro-de-ocupacao-hospitalar-covid-19` | record (facility notification) | 21 | 100,000 to 10,000,000 | use DEMAS | 21 columns, 0.1 M to 10 M rows, 2020-2022 events; Portal has 3 files; no FTP copy |
| **CNES** (11) | | | | | |
| `cnes/tipounidades` | reference (unit types) | 2 | >=39 | original, DEMAS fallback | 39 rows, no paging; the codelist is already in CNES.TP_UNID |
| `cnes/tipounidades/{codigo_tipo_unidade}` | reference (one unit type) | - | - | original, DEMAS fallback | key lookup, not probed |
| `cnes/estabelecimentos` | record (establishment) | 37 | >=20 | original, DEMAS fallback | 37 columns, 20 rows per request whatever the limit; CNES-ST has 208 columns and every month |
| `cnes/estabelecimentos/{codigo_cnes}` | record (one establishment by CNES) | - | - | original, DEMAS fallback | key lookup, not probed; same table as /cnes/estabelecimentos |
| `assistencia-a-saude/hospitais-e-leitos` | record (hospital, current) | 31 | 100,000 to 10,000,000 | original, DEMAS fallback | 31 columns, current snapshot (Portal: 20 monthly files); CNES-ST/LT on the FTP hold every month since 2005 |
| `assistencia-a-saude/unidade-basicas-de-saude` | record (UBS) | 8 | >=1,000 | original, DEMAS fallback | 24,001 to 47,987 rows against 47,989 in the Portal CSV (offset 47988 empty); CNES-ST carries the type |
| `assistencia-a-saude/cnes-equipamentos` | record (establishment x equipment x month) | 12 | - | original, DEMAS fallback | 12 columns against CNES-EQ's 28; same paging |
| `assistencia-a-saude/cnes-estabelecimentos` | record (establishment x month) | 21 | - | original, DEMAS fallback | 21 columns against CNES-ST's 208; limit 1000 returns 12 rows and nu_comp=201705 returns 1; a co_cnes lookup returns that establishment's 223 monthly records 2008-01..2026-07 |
| `assistencia-a-saude/cnes-leitos` | record (establishment x bed type x month) | 10 | - | original, DEMAS fallback | 10 columns against CNES-LT's 28; same de-duplicating paging |
| `assistencia-a-saude/cnes-profissionais` | record (professional x establishment x month) | 26 | - | original, DEMAS fallback | 26 columns against CNES-PF's 40; same paging |
| `assistencia-a-saude/cnes-servicos-especializados` | record (establishment x service x month) | 18 | - | original, DEMAS fallback | 18 columns against CNES-SR's 32; same paging |
| **SIA-PA** (1) | | | | | |
| `assistencia-a-saude/sia-procedimentos-ambulatoriais` | aggregate (facility x procedure x month) | 17 | - | original, DEMAS fallback | 17 columns against SIA-PA's 75; limit is applied before de-duplication (1 row for limit 5) |
| **SIH** (1) | | | | | |
| `assistencia-a-saude/sih-procedimentos-hospitalares` | aggregate (facility x procedure x month) | 17 | - | original, DEMAS fallback | 17 columns against SIH-RD's 127; limit applied before de-duplication |
| **SISVAN** (1) | | | | | |
| `sisvan/estado-nutricional` | record (nutritional follow-up) | 33 | >=30,000,000 | original, DEMAS fallback | 33 columns, >=3e7 rows (paging wall); the Portal holds 16 yearly files 2008-2023 |
| **BNAFAR** (1) | | | | | |
| `daf/estoque-medicamentos-bnafar-horus` | record (establishment x product x lot x day) | 25 | 100,000 to 10,000,000 | use DEMAS | 25 columns, 0.1 M to 10 M rows with daily data_posicao_estoque and filters (uf, municipality, cnes, catmat, month); the Portal has one CSV |
| **BPS** (1) | | | | | |
| `economia-da-saude/bps` | record (purchase) | - | - | use DEMAS | 400 unless codigoCatmat or cnpjInstituicao is given: a unit-price lookup by item or buyer, no bulk listing; Portal has 7 yearly CSV |
| **SISAB** (2) | | | | | |
| `atencao-primaria/cadastro-vinculado-programa-previne-brasil` | aggregate (municipality x team type x month) | 10 | 100,000 to 10,000,000 | use DEMAS | 10 columns, 0.1 M to 10 M rows; primary-care coverage context |
| `atencao-primaria/indicador-desempenho-programa-previne-brasil` | aggregate (municipality x indicator x quadrimester) | 16 | 100,000 to 10,000,000 | use DEMAS | 16 columns, 0.1 M to 10 M rows |
| **SIAPS** (2) | | | | | |
| `atencao-primaria/siaps-atendimento-individual` | aggregate (municipality x month x sex x age x CID/CIAP chapter x profession) | 19 | 100,000 to 10,000,000 | use DEMAS | 19 columns, 0.1 M to 10 M rows; only route |
| `atencao-primaria/siaps-cadastro-individual` | aggregate (registrations by municipality x month x sex...) | 17 | >=10,000,000 | use DEMAS | 17 columns, >=1e7 rows; only route |
| **SIES** (1) | | | | | |
| `vacinacao/sistema-de-informacao-de-insumos-estrategicos` | aggregate (immunobiologicals distributed, municipality x month) | 8 | 133,351 to 177,827 | use DEMAS | 8 columns; 137,914 rows = the Portal CSV's 137,914 (offset 137913 yes, 137914 empty) |
| **SIASI** (19) | | | | | |
| `saude-indigena/indicadores-enfrentamento-monitoramento-covid19-indigenas` | record (indigenous health event or person) | 5 | >=1,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sistema-de-atencao-a-saude-indigena-modulo-de-vigilancia-alimentar-e-nutricional` | record (indigenous health event or person) | 25 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/siasi-acompanhamento-gestacional` | record (indigenous health event or person) | 23 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/siasi-modulo-morbidades` | record (indigenous health event or person) | 24 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-atendimentos` | record (indigenous health event or person) | 19 | >=99 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/siasi-modulo-saude-bucal-ficha3` | record (indigenous health event or person) | 19 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/siasi-modulo-saude-bucal-ficha4` | record (indigenous health event or person) | 30 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/siasi-modulo-saude-bucal-ficha7` | record (indigenous health event or person) | 46 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-acidentes-ofidicos` | record (indigenous health event or person) | 11 | >=668 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-arboviroses` | record (indigenous health event or person) | 11 | >=588 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-cobertura-vacinal` | record (indigenous health event or person) | 21 | >=377 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-covid19` | record (indigenous health event or person) | 23 | >=1,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-demografico` | record (indigenous health event or person) | 18 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-doencas-diarreicas-agudas` | record (indigenous health event or person) | 11 | >=1,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-doencas-imunopreveniveis` | record (indigenous health event or person) | 11 | >=1,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-doencas-zoonoticas` | record (indigenous health event or person) | 11 | >=583 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| `saude-indigena/sesai-hepatites-virais` | record (indigenous health event or person) | - | - | use DEMAS | returns no rows at offsets 0 and 5 (status 200, empty list): nothing to ingest now |
| `saude-indigena/sesai-obitos` | record (indigenous health event or person) | - | - | use DEMAS | returns no rows at offsets 0 and 5 (status 200, empty list): nothing to ingest now |
| `saude-indigena/sesai-doencas-respiratorias` | record (indigenous health event or person) | 13 | 100,000 to 10,000,000 | use DEMAS | indigenous-health microdata, public only here and on the Portal (one file per module); empty at offset 0 where the rows column is blank |
| **SESAI** (3) | | | | | |
| `saude-indigena/sasisus-esgotamento-sanitario` | record (village) | 23 | >=35 | use DEMAS | about 35 rows: context for indigenous health |
| `saude-indigena/sasi-sus-gerenciamento-de-residuos-solidos` | record (village) | 22 | >=35 | use DEMAS | about 35 rows: context for indigenous health |
| `saude-indigena/planilha-de-fornecimento-e-monitoramento-da-qualidade-da-agua-acesso-a-agua` | record (village) | 22 | >=34 | use DEMAS | about 35 rows: context for indigenous health |
| **MS reference** (1) | | | | | |
| `macrorregiao-e-regiao-de-saude/municipio` | reference (municipality -> health region -> macroregion) | 11 | >=860 | use DEMAS | 11 columns; the first page gave 860 rows and offset 860 returns more (limit applied before de-duplication); no FTP copy of the mapping |
| **Not relevant** (29) | | | | | |

Not relevant (29): `economia-da-saude/sistema-de-apuracao-e-gestao-de-custos-do-sus-apurasus`, `outros-temas/ced`, `prevencao-e-promocao/distribuicao-epi-insumo`, `saude-indigena/acompanhamento-obra-infraestrutura-saude`, `saude-indigena/planilha-registros-habilitacao-recebimento-incentivo`, `atencao-primaria/enani-2019`, `atencao-primaria/pmmb-consolidado`, `educacao-em-saude/pvc`, `atencao-primaria/pmmb-serie-historica`, `atencao-primaria/pmmb-relacao-nominal-coparticipacao`, `atencao-primaria/pmmb-relatorio-historico-cadastro-cnes`, `atencao-primaria/pmmb-especialista-consolidado`, `atencao-primaria/pmmb-especialista-serie-historica`, `atencao-primaria/pmmb-relacao-nominal-ativo`, `saude-indigena/sesai-recursos-humanos`, `saude-indigena/sesai-assistencia-farmaceutica`, `ciencia-tecnologia/dgits-contribuicoes-consultas-publicas`, `ciencia-tecnologia/dgits-controle-demandas-conitec`, `ciencia-tecnologia/dgits-controle-pcdt`, `ciencia-tecnologia/dgits-tecnologias-diretrizes`, `ciencia-tecnologia/plataformabr-pesquisa-saude`, `ciencia-tecnologia/plataformabr-projeto-aprovado`, `ouvidoria/ouvidor2`, `ouvidoria/ouvidor3`, `atencao-primaria/pmmb-especialista-relacao-nominal-ativo`, `atencao-primaria/pmme-instituicoes-formadoras`, `educacao-saude/sig-residencia-medica`, `educacao-saude/sig-residencia-area-profissional`, `educacao-saude/pet-saude`.

## What pegasus_data should ingest

From DEMAS (35 endpoints, no other bulk route; compare with the Portal file when ingesting): ESAVI (316-422 k rows, 73 columns),
mpox (75-100 k), yellow fever monitoring and epizootics (2.9 k, 2.6 k), SIES (137,914, equal), BNAFAR stock (0.1-10 M, filters
by uf/municipality/cnes/CATMAT/month), COVID occupancy, the SIASI/SESAI modules (indigenous health; `sesai-obitos` and
`sesai-hepatites-virais` are empty now), SISAB Previne Brasil x2 and SIAPS x2 (primary-care context), the municipality ->
health region -> macroregion mapping, and BPS by CATMAT.

From the Portal files instead of DEMAS (the BACKLOG expected DEMAS): SISAGUA (14 tables; vigilância and controle series are
annual zips 2014-2026, the rest single zips), SI-PNI doses 2020-2026 (monthly zips), SRAG (parquet), SG leve (CSV), SISVAN
(annual). From the DATASUS FTP: SIM, SINASC, CNES, SIA, SIH, SINAN dengue/chikungunya/zika (DEMAS holds their columns but is
unusable in bulk).

## Open items

- SISAGUA's other ten tables, ESAVI, mpox, yellow fever and SESAI were not counted against their Portal files; their
  verdicts rest on the paging facts and the five SISAGUA tests, and "use DEMAS" ones are provisional.
- DEMAS SIM has `cb_alt`, `opor_do`, `tp_altera`, which `roles('SIM-DO')` lacks: look in the newest FTP DO files.
- Dengue 256 against 249 for one municipality-year: nu_ano against the notification-month binding, or later records.
- SINASC empty: retry after a DEMAS update.
- Not reported to DEMAS (that would be contacting someone): the SRAG `dt_notific`, the 5,000-row truncations, the empty SINASC.
