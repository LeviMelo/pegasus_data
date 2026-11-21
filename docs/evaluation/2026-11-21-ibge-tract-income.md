# Census 2022 income by tract, a declaration per topic, and the weighting areas (2026-11-21)

**What.** (1) `ibge_tracts.aggregates` in `published_tables.yml` now names, per topic, its folder (relative to the Census root), zip, dictionary
(file, sheet, the column of each field), the theme in it and the value type (`integer` count or `decimal` float64); the code assumes no folder, dictionary or
int32. The five existing topics rebuilt with the same rows (458,772 each), the same sum of every column and the same non-null cell count as the files
built before (literacy 2,561,425,760 / 142,210,175 cells; household 1-3 1,450,645,294 / 1,765,172,816 / 2,649,714,960; colour or race 1,021,974,452).
(2) New topic `renda_responsavel`, IBGE's folder `Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/` (release 2026-05-08; my earlier note that
tract income is unpublished was wrong and is corrected in the 2026-11-21 aggregates entry and DATA_SOURCES §6.3a): 458,772 tracts, `V06001` heads,
`V06002` residents, `V06003` variance of residents, `V06004` mean and `V06006` median monthly income of heads with income, `V06005` its variance (labels
from IBGE's dictionary, read, not assumed); decimal point in the tract file. `X` is suppressed and `.` not applicable, both null: 53,424 of 2,752,632 cells
(1.94%) `X`, 1,136 `.`. The district, neighbourhood, subdistrict and municipality versions are in the same folder, not integrated (the municipal one is the check).
(3) `build_weighting_areas`: the sample's tables by weighting area and the tract composition (below).

**Counted: tracts against IBGE's municipal file of the same release.** Municipal sums of `V06001` and `V06002` equal the tracts' in all 5,570 municipalities
(72,435,919 heads, 202,007,359 residents): the municipal file is the sum of the published tract cells, so the 8,904 suppressed tracts (1.9%, 531,151 residents) are
missing from both, and IBGE's whole population (203.08 M, basic file) is 0.53% above. Means and medians cannot be summed; the heads-weighted mean of the tract means
(V06001 weights, since the heads *with income* are not published) against the municipal mean:

| | heads | residents | municipal mean | tracts weighted mean | municipal median |
|---|---|---|---|---|---|
| Maceió 2704302 (1,571 tracts, 38 suppressed) | 335,721 = | 953,183 = | 3,087.00 | 3,008.56 (-2.5%) | 1,250 |
| São Paulo 3550308 (26,889 tracts, 212 suppressed) | 4,307,291 = | 11,394,012 = | 4,961.95 | 4,868.53 (-1.9%) | 2,500 |
| Brazil | 72,435,919 = | 202,007,359 = | 3,001.2 (municipalities weighted) | 2,972.1 | |

Over the municipalities where tracts hold 95% of the heads the weighted mean differs from IBGE's by a median 0.32%, 90th percentile 0.98%, maximum 11.8%: weighting by
all heads understates it when low-income tracts have more heads without income; an exact municipal mean is IBGE's, the tract means are for mapping and ranking.

**Weighting areas.** `tabelas_xlsx_20261106.zip` (44 MB) holds 34 tables (households, education, disability, religion, fertility, migration, work, income, commuting,
marital status, families), each a tidy sheet keyed by municipality code and weighting-area code (14,270 areas) with two to three title/header rows; the three income tables
(8.1 and 8.2 mean and median; 8.3 per capita household income, mean and median, by sex) are integrated through the same declaration (`weighting_area_table`, labels in
`tract_dictionary(table)`); the others need only their `header_rows`. Table 8.3's persons sum to 202,037,016 (IBGE's Brazil row 202,037,019) and the 14,270 areas have
no empty cell. `Composição das Áreas de Ponderação.xlsx` **does publish the tract to area map** (`tract_weighting_area`, 468,097 tracts; all are in the census tracts and
agree on municipality; 14,406 areas, 136 empty ones with 252 tracts and no residents are in no table); tract residents summed by area match Table 8.3's persons to a
median 0.15% (max 184%, a tiny area). So a record that reaches a tract (via CEP) reaches its area's income. **Sample microdata** (`Microdados_de_acesso_Publico`, 1.0 GB
all-UF zip, 3-182 MB per UF; not downloaded whole, AL read: 347,165 persons, 114,514 households): the public files carry only UF, a control number, the tract's
situation and the weight, **no municipality, tract or area**; areas are in the controlled-access version.

**Learned.** Income by tract is published and at the tract's own grain; the area tables are the sample's estimate. Nulls mix two reasons (`X`, `.`); `suppressed_share`
counts the first, `not_applicable` the second.

**Regime.** Branch `ibge-tract-income`, shared data home (`registries/ibge_tracts/`), 2026-11-21; ad hoc DuckDB comparisons of the parquet files with IBGE's municipal
CSV (not kept); `build_aggregates` 86 s, `build_weighting_areas` 141 s.
