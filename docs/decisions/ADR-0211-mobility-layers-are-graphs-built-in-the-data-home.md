# ADR-0211: Mobility between municipalities is a set of graphs built in the data home, read by `proximity_graph`

2026-10-25. Status: active. Extends ADR-0203 (the shipped proximity graphs) and the care-flow format.

## Context

The dengue project (PEGASUS_ISSUES §9) needs the movement of people between municipalities as edges in the shape of
`proximity_graph` and `care_flows`: `(from, to, weight, kind, vintage)` with 7-digit IBGE codes. It named four
sources:
- the Census 2010 sample, commuting to work and to study;
- IBGE's *Ligações rodoviárias e hidroviárias* 2016;
- ANAC's air passengers by month;
- IBGE's *Arranjos Populacionais* (2nd edition), optionally.

The shipped graphs (contiguity, population distance, REGIC) live in the package. These sources are larger, are
refreshed by their publishers (ANAC monthly), or are read from microdata of several GB.

## Decision

1. **Each source is a module with `build(root, log)` that writes `<root>/registries/mobility/<kind>.parquet`.**
   - `pegasus-data mobility [--layer census_commuting|ibge_links|anac_air]` runs them.
   - `proximity_graph(kind, vintage=…)` reads a built layer as it reads a shipped graph; `graph_kinds()` lists the
     shipped graphs and the layers built in the home.
   - The CLI's `graph KIND --period A-B` filters the vintages.
   - The five kinds and what `weight` counts (`MOBILITY_LAYERS`):

     | Kind | Vintage | Weight |
     |---|---|---|
     | `commute_work_2010` | 2010 | persons resident in `from` who work in `to`, summed sample weights |
     | `commute_study_2010` | 2010 | persons resident in `from` who study in `to`, summed sample weights |
     | `road_links_2016` | 2016 | weekly coach departures of the pair |
     | `waterway_links_2016` | 2016 | weekly boat departures of the pair |
     | `air_passengers` | YYYYMM | paid and free passengers on the flight stages between the pair's airports |

   - Each layer keeps its source's own columns beside these.
2. **Each edge says what its weight counts, and nothing is converted to a common unit.**
   - **Census.** Commuting is directed and weighted, with the unweighted `persons_sampled` beside it. A worker in "more
     than one municipality", a foreign country, the ignored code and a blank code are counted apart, never mapped.
   - **IBGE links.** The workbook gives each pair once, both directions summed ("ida e volta"). Each direction carries
     the full pair total, never half.
   - **ANAC.** Flow is carried per flight stage: a passenger on A-B-C counts on both stages.
3. **An airport lies where its coordinates fall** (`geography.place_points`, the one placement of points in IBGE's
   mesh, now shared with INMET's stations).
   - **Coordinates.** They come from ANAC's aerodrome registers, else OurAirports for an airport the registers no
     longer list.
   - **Code reuse.** ANAC reuses codes. A placement therefore holds only for the legs whose own named city is the placed
     municipality or a contiguous neighbour (or, when the name is no municipality, the same UF). A contradiction leaves
     the legs unplaced, never guessed.
4. **Membership classifications.**
   - **Arrangements.** The arrangements and urban concentrations join the geography pack as IBGE classifications:
     `population_arrangement`, `urban_concentration_medium` and `urban_concentration_large`. They are read from IBGE's
     geodatabase with `access-parser`, now in the `geo` extra.
   - **Census 2022.** The commuting shares (SIDRA 10321, 10330-10333) need no new code: the SIDRA reader serves them
     per municipality, and their notes are declared as sample estimates.

## Evidence

Each evaluation below is dated 2026-10-25.
- **`ibge-road-waterway-links`.** The figures reproduce the book's: 65,638 pairs; the top pair, Carpina-Paudalho, at
  2,855; the seven countries exactly. Road has 65,121 pairs and waterway 405.
- **`anac-air-passengers`.** The domestic paid passengers agree with ANAC's Anuário within 0.04% in 2010-2022, except
  2020 (−1.64%: LATAM's November-December missing from the open file, OQ 95 resolved 2026-11-05). Placement by coordinates leaves 3.13 M passengers of 1.871 billion unplaced, where the earlier
  name match had left 25.1 M; Natal's departures run continuously across the 2014 airport move.
- **`arranjos-and-census-2022-commuting`.** 294 arrangements of 953 municipalities; 161 medium and 26 large
  concentrations; the rest of the pack is identical.
- **`census-2010-commuting`.** 128,937 work and 84,993 study edges. The persons answering "another municipality" agree
  with SIDRA 1615 and 1611 within one person in every municipality. The codes counted apart take 96,623 of Brasília's
  113,076 out-commuting workers: commuting between the DF's administrative regions (OQ 94, resolved 2026-11-05).
