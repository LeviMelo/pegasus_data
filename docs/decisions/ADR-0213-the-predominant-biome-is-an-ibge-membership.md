# ADR-0213: The predominant biome is an IBGE membership of the geography pack

2026-11-06. Status: active. Extends ADR-0211 (IBGE's arrangements join the geography pack).

## Context

Eco-epidemiological studies need each municipality's biome: toxoplasmosis, leishmaniasis, Chagas disease and
arboviruses all follow it. pegasus_data had no biome. IBGE publishes the predominant biome of every municipality
(*Biomas e Sistema Costeiro-Marinho do Brasil*, 1:250,000) as a plain CSV, `Bioma_Predominante_por_Municipio_2024.csv`,
under `geoftp.ibge.gov.br/informacoes_ambientais/estudos_ambientais/biomas/documentos/`. It is UTF-8 with a BOM,
semicolon-separated, with columns `Geocódigo`, `Nome do município`, `Sigla da UF` and `Bioma predominante`. Read on
2026-11-06, it held 5,579 rows. IBGE's note on the same page says that a municipality often spans several biomes, and
that the predominant one is the biome with the largest share of its area.

## Decision

`biome` is an IBGE classification (`ibge_classifications` in `curation/geography.yml`, `source: IBGE/biomas_2024`).
`sources/ibge_biomas.py` fetches the CSV into `registries/ibge_biomas/`. `geography._biome_rows` writes one row per
municipality into the geography pack, the same way the arrangements are written. IBGE gives a biome no code, so its
member code is its name. It is read like any membership: `memberships(code).as_dict()["biome"]`, or the pack's rows.

## Evidence

IBGE's table also lists two lagoon areas with territorial codes, Lagoa Mirim (4300001) and Lagoa dos Patos (4300002).
They are not municipalities, and at six digits both read as 430000, so they are left out (`NOT_MUNICIPALITIES`). The
rebuilt pack holds 5,570 municipalities in 6 biomes:

| biome | municipalities |
|---|---:|
| Mata Atlântica | 2,741 |
| Caatinga | 1,095 |
| Cerrado | 1,062 |
| Amazônia | 503 |
| Pampa | 160 |
| Pantanal | 9 |

Every other classification's row count is unchanged: 111,717 rows before, 117,287 after, and the only difference is
`biome`. Spot checks: Maceió (270430) is Mata Atlântica and Santa Maria (431690) is Pampa.

## Consequences

The pack's share of a municipality's area by biome (IBGE's `Lista_Municipio_Bioma_250mil.xls`) is not loaded. A study
needing mixed-biome shares reads that list, a further source when one asks for it.
