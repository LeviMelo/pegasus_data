# ADR-0214: SISAGUA's register of the population supplied and its tanker-truck register are context sources

2026-11-07. Status: active. Extends ADR-0162 (SISAGUA on the Portal de Dados Abertos).

## Context

SISAGUA's water-quality files were integrated by ADR-0162. Its registers were not (DATA_SOURCES §13). Two of them
answer questions the quality files cannot:
- **The population register** answers who drinks which water: the population each supply form serves, whether the
  form filters and disinfects, and whether it takes surface water.
- **The tanker-truck register** answers where water is trucked in.

The toxoplasmosis study (toxoplasmose_brasil, P2 and P3) needed both. Toxoplasma oocysts resist chlorine and are
removed by filtration, so unfiltered surface water is the relevant exposure. A drought study needs to know whether
tankers came.

## Decision

Two `curation/intake.yml` sources, files landed from the Portal's zips like the other SISAGUA families. The new columns
(filtration, disinfection, intakes, populations, tanker dates and purpose) join the shared `sisagua` dictionary.

- **`sisagua_supply_population`** (series CADP): `cadastro_populacao_abastecida_csv.zip`, one row per supply form x
  municipality x year (`NU_ANO`). Five fields sum `NU_VALOR_POPULACAO_ESTIMADA` by `TP_ABASTECIMENTO` (SAA, SAC, SAI):
  `sisagua_supply_population` (all forms), `_filtered` (`FILTRACAO` Sim), `_surface` (`CAPTACAO_SUPERFICIAL` Sim),
  `_surface_filtered` (both) and `_disinfected` (`DESINFECCAO` Sim).
- **`sisagua_tanker_population`** (series CADT): `cadastro_carro_pipa_populacao_csv.zip`, one row per tanker truck x
  municipality. Its year is that of `DT_TRANSPORTE_INICIO`. One field, `sisagua_tanker_trucks`, counts trucks by
  `DS_TIPO_FINALIDADE`.

The register's people supplied by tankers is not a field. Registrants enter the municipality's whole population on
each truck. Fortaleza 2023 has six trucks of 3,000,000 people each, and the 23 of 1,608 entries above 100,000 hold 96%
of the column's total. A sum would count the same people many times.

## Evidence

Landed 2026-11-07 into the shared home. The population register held 1,918,496 rows (the Portal's file had grown from
§13's 1,914,017), all dated and placed. In 2022 the forms supplied:
- SAA 147.6 million, SAC 8.1 million and SAI 2.2 million people;
- 121.6 million by forms that filter;
- 123.2 million by forms with a surface intake, 118.6 million of them filtered.

The forms overlap, as the dictionary warns: a SAC whose people also receive SAA water counts in both.

The tanker register held 2,174 trucks: 710 starting in 2023, 433 in 2024, 673 in 2025 and 357 in 2026, in 432
municipalities. 1,605 were Operação carro-pipa.

## Consequences

The treatment-plant and intake-point registers (82 and 55 MB) duplicate the population register's filtration and
intake flags at the plant level, and are still not landed. The tanker-origin register (`carro_pipa_procedencia`, which
water each truck loads) is small and not yet declared.
