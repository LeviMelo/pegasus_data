# ADR-0204: CNEFE 2022 places a CEP: the addresses are landed whole, and the per-CEP table keeps counts, a median and its spread

2026-10-24. Status: active. Builds on ADR-0188 (the one transport) and ADR-0172 (a unit is replaced, never added to).

## Context

SIH-RD files the patient's CEP (eight digits, 100% filled in Alagoas 2023: 166,471 rows) and the municipality of residence,
and nothing that says where in the municipality the CEP lies. IBGE's `Agregados_por_CEP` gives counts per CEP and no
coordinate. The Census's own address list, the CNEFE 2022, gives each address its CEP, municipality, census tract and
coordinate (111,102,875 records of 106,814,877 addresses in 931,499 CEPs; 27 zips, 3.92 GB), public and in the Census's codes.

## Decision

1. **Landed whole, by UF, replaced as a unit** (`sources/ibge_cnefe.py`, `pegasus-data cnefe`). Each zip is streamed (no extracted CSV on
   a disk with 15 to 32 GB free) into `<lake>/cnefe_2022/uf=<UF>/` as zstd Parquet, all 34 columns. Identifiers, geography codes, `CEP` and
   the `COD_*` and `NV_GEO_COORD` codes are strings of the width filed, `NUM_*` integers, the coordinates doubles; a field that does not
   convert stops the landing, an empty one is null. The UF is swapped in only after its rows equal the file's own newlines (counted on the
   zip stream, not by the parser) and the zip's size and CRC hold: 27 of 27 equal, 111,102,875 rows. The last header is cut in the files,
   `COD_TIPO_ESPECI`, where the dictionary says `COD_TIPO_ESPECIE`: it lands under the dictionary's name and any other header is refused. A raw
   zip is deleted once its UF is landed and counted only when the disk has under 15 GB free; its size, sha256 and the server's validators
   stay in `registries/ibge_cnefe/manifest.json`.
2. **The address is the distinct `COD_UNICO_ENDERECO`, not the record.** A record is an address *species* (a dwelling and the shop under
   it are two records of one address). IBGE's `TOT_END` equals the distinct addresses of a CEP in 931,499 of 931,499 CEPs; the records
   equal it in 640,355. Every record of an address carries the same CEP, municipality, tract, coordinate and level (0 exceptions in 27
   UFs), so the table keeps one point per address.
3. **Derived per CEP and municipality** (`<lake>/cnefe_2022_cep/uf=<UF>/`, 931,938 rows): a CEP that spans municipalities is several rows with
   their own counts, never one chosen (398 CEPs span two to four municipalities, 6 span two UFs). Stored: addresses, records, the records of
   each species, the addresses at each `NV_GEO_COORD` level (counts, never shares: CLAUDE.md §6), the census tracts with their address
   counts, the median latitude and longitude (each coordinate's median) and the distance in metres from that point within which half and
   nine tenths of the addresses lie (haversine). `municipality_addresses` and `municipality_ceps` carry the municipality's totals, so a CEP
   that is its municipality's only one, which places nobody inside it, is read off the table. It is not the only general CEP: São Paulo's
   01001-000 holds 6,973 addresses with half of them within 17.8 km of its median, so the spread is the measure and no threshold is set.
4. **Read** with `cep_points(municipality=, uf=, cep=)` / `pegasus-data cep-points`: a six-digit DATASUS code or IBGE's seven is matched
   against its own column as given, never padded or cut; a UF not built raises, a place that holds no CEP raises, a CEP not found is
   absent from the answer, and with fewer than 27 UFs built a lookup that names no UF warns that the CEP may belong to another.
5. **Checked against IBGE's aggregate by CEP** at the end of every build (`check_against_aggregate`, stored in the manifest): the same
   931,499 CEPs in both, and 13 columns equal on every one (`TOT_END`, the eight species totals, `TOT_TIPO_101` to `_104`; sums
   106,814,877 addresses and 90,600,065 private households). `TOT_TIPO_k` counts the dwellings of species 1 and 2, not 1 alone (a read
   of species 1 differed in 338 Alagoas CEPs, the 1,042 collective households, all type 104); `TOT_DOM_COND` has no counterpart in the records.

## Consequence

SIH-RD Alagoas 2023, 166,471 rows (`scripts/live.py cnefe_cep`, docs/evaluation/2026-10-24-cnefe-cep.md): 95.4% of the rows have their CEP in
the CNEFE, and for every one the patient's `MUNIC_RES` is one of the CEP's municipalities (a shuffled `MUNIC_RES` agrees on 8.2%).
21.0% of the rows sit on the only CEP of their municipality (44 of the state's 102 have just one) and 70.0% of the found rows on a CEP whose addresses
spread over more than 2 km (p90): the CEP places a patient in the municipality, and a point is a centre with its radii. Of
the 5,570 municipalities, 1,694 have one CEP (8.0% of the addresses). The CEPs the CNEFE does not hold (4.6% of residents' rows,
62% of them Maceió's) are listed, not placed.

## What would reverse it

A CEP base with a coordinate per street segment (the Correios', licensed) or an address geocoder, which would put the patient's street
where the CNEFE puts a median; a later Census's CNEFE as a second vintage beside this one (the lake folders would take a year).
