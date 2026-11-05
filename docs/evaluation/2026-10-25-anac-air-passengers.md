# ANAC air passengers between municipalities (2026-10-25)

Scenario: `pegasus_data.sources.anac_air.build()`; artifact `<home>/registries/mobility/air_passengers.parquet`, report
`<home>/registries/anac/air_passengers_report.json`. Regime: branch `mobility` (from `a1b70be`; placement by coordinates, ADR-0211), data home
`C:\Users\Galaxy\pegasus_core_data`, run 2026-10-25, `Dados_Estatisticos.csv` Last-Modified 2026-10-25 04:12 GMT (361,057,599 bytes,
"Atualizado em: 2026-10-25", 1,102,983 rows, 200001-202609).

**What a row is.** ANAC's variable page (gov.br/anac, *mercado-do-transporte-aereo/demanda-e-oferta/descricao-das-variaveis*) defines
the file's unit as the *etapa basica* (flight stage, take-off to next landing); ASK, RPK, DISTANCIA, DECOLAGENS are stage columns. A
passenger on A-B-C is counted on A-B and on B-C: the parquet is flow carried per segment, not the traveller's origin-destination.
`weight = PASSAGEIROS_PAGOS + PASSAGEIROS_GRATIS` (both are people occupying seats offered; free = no revenue). `flights` = DECOLAGENS.
`NATUREZA` "Domestica" means both ends in Brazil **and** a Brazilian operator.

**Rules.**
- **Domestic.** A leg is domestic when both airports are in Brazil, of any nature. Foreign-operator Brazil-Brazil legs carried
  240,327 of the 1,870,919,659 domestic passengers.
- **Placement.** The airport serves the municipality whose IBGE boundary contains its coordinates (`geography.place_points`, the
  maxima mesh).
  - Coordinates come from the ANAC registers: 320 airports from the public one, 104 from the private one.
  - Airports the registers no longer list take OurAirports' coordinates: 56. SBNT Natal-Augusto Severo is one of them; it lies
    in Parnamirim.
  - 480 of the 505 airports in Brazilian legs land in a municipality, one of them within 2 km of the coast. 24 have no
    coordinates anywhere; one lies in no municipality.
- **Code reuse.** ANAC reuses a code for another aerodrome over the years. OurAirports' SNQY is an airfield of Ribeirão Preto,
  the file's is JUAZEIRO DO NORTE/CE; SWJH is in Tapejara/RS, the file's in JUARA/MT.
  - So a placement holds only for the legs whose named city (the file's own `..._NOME`/`..._UF`) is the placed municipality
    (415 code-name pairs) or its neighbour by contiguity (13: CURITIBA for São José dos Pinhais, NATAL for Parnamirim).
  - Where the named city is not a municipality, the placement holds if the UF matches (2).
  - 50 pairs contradict their named city and stay unplaced, rather than being put in the wrong state.
- **Names are checked, never used to place.** The registers' *Município* differs from the placement for 7 of 423 airports, for
  example CUIABÁ for Várzea Grande (SBCY) and BAURU for Arealva (SBAE).
- **Same municipality.** Legs between two airports of one municipality are counted apart.

**Counts.**
- **The file.** 351,105 rows over 321 months, with 379 origin and 385 destination municipalities.
- **Domestic passengers per year** (both ends in Brazil), millions:

  | 2000 | 2005 | 2010 | 2013 | 2015 | 2016 | 2019 | 2020 | 2022 | 2024 | 2025 | 2026 (to Sep.) |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | 29.8 | 39.7 | 71.4 | 91.9 | 97.9 | 90.3 | 97.2 | 45.5 | 84.1 | 95.4 | 103.3 | 78.6 |

- **International legs**, millions: 24.5 in 2019, 6.9 in 2020, 29.6 in 2025.
- **By group** (domestic): regular 1,801,989,746, non-regular 68,136,468, improdutivo 793,445.
- **Cells neither empty nor integer:** 0.
- **Same-municipality legs:** 690,102 passengers, not in the file.

**Unplaced.** 3,132,430 passengers (0.17%).
- **No coordinates in any source**, so no placement:
  - SBQV Vitória da Conquista's old airport, 2.38 M;
  - SBMH Maringá, 0.32 M;
  - SBPM Palmas, 0.25 M;
  - SBRG Rio Grande, 0.02 M.
- **Contradicting their named city:** SNQY, 35 thousand, and SNDM, 32 thousand.
- **What is kept.** The passengers kept (placed, different municipalities) are 99.1-99.9% of each year's domestic total from
  2000 to 2019, and 99.8% or more from 2020.
- **Natal across the airport move.** Its departures run continuously through the 2014 move to São Gonçalo do Amarante:
  1.17 M in 2013 and 1.20 M in 2014.
- **Superseded.** An earlier name-matched build left 25.1 M unplaced, Natal 21.0 M of it.

**Check against an independent figure.** ANAC's audited *Anuario do Transporte Aereo* (domestic paid passengers, xlsx of the 2019
edition Fig 3.1 and the 2022 edition Fig 3.7) against the file's `PASSAGEIROS_PAGOS` with NATUREZA Domestica:

| year | Anuario | file | difference | % |
|---|---|---|---|---|
| 2013 | 89,961,794 | 89,969,709 | +7,915 | +0.009 |
| 2015 | 96,092,687 | 96,102,281 | +9,594 | +0.010 |
| 2018 (2019 ed.) | 93,609,121 | 93,615,132 | +6,011 | +0.006 |
| 2019 (2019 ed.) | 95,250,162 | 95,059,259 | -190,903 | -0.200 |
| 2019 (2022 ed.) | 95,049,348 | 95,059,259 | +9,911 | +0.010 |
| 2020 (2022 ed.) | 45,249,296 | 44,507,029 | -742,267 | -1.64 |
| 2021 (2022 ed.) | 62,583,717 | 62,580,997 | -2,720 | -0.004 |
| 2022 (2022 ed.) | 82,228,992 | 82,257,882 | +28,890 | +0.035 |

2010-2019 (2019 ed.) and 2013-2022 (2022 ed.) all within +-0.04% except 2019 against its own first edition (the Anuario revised it
by 0.2% the next time) and 2020 (-1.64%: LATAM's November-December 2020 are missing from the open file, about 752 thousand; found 2026-11-05).

**Facts for DATA_SOURCES.** `sistemas.anac.gov.br/dadosabertos/` is an nginx index (no auth, works with a browser UA); the series file is
rewritten with a new date line on days the data does not change (2026-11-05: the same bytes after the first line; corrected 2026-11-05, this note had said "replaced about the 20th of each month"); `Dados_Estatisticos.csv` is UTF-8 with BOM, a dated first line, `;`-separated, quoted, header
in upper snake case, 36 columns; the aerodrome registers (`Aerodromos/Aerodromos Publicos/Lista de aerodromos publicos/AerodromosPublicos.csv`,
`.../Aerodromos Privados/.../AerodromosPrivados.csv`) are cp1252, a dated first line, carry ICAO, CIAD, municipality and UF (full name in
the public one, sigla in the private one) and "Municipio Servido", and no IBGE code; gov.br answers HEAD with 403 (GET works). The
Anuario xlsx report their dimension as A1, so a read-only openpyxl pass sees no data unless `reset_dimensions()` is called. Download
speed was ~0.3 MB/s (20 minutes for 361 MB).
