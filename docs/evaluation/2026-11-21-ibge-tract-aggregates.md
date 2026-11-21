# Census 2022 tract aggregates: literacy, household characteristics, colour or race (2026-11-21)

**What.** `tract_aggregates(topic)` and `tract_dictionary(topic)` (`sources/ibge_tracts.py`, ADR-0203's mechanism) read five more
themes of IBGE's *Agregados por Setores Censitários* into `registries/ibge_tracts/`: `alfabetizacao` (362 variables),
`domicilio1` (89), `domicilio2` (406), `domicilio3` (148), `cor_ou_raca` (95), each one wide parquet of 458,772 tracts (the
tracts with residents), 240 MB in all, built in 3 minutes from 1.5 GB of zips read in batches. Wide, not long: a column per
variable as IBGE publishes it (long would be 1.4 billion rows), and an `X` is the only null, so null is the suppressed flag.
`census_tracts` now also keeps `v0005` (mean residents per household), `v0006` (share imputed) and the favela and urban community
code and name (`cd_fcu`, `nm_fcu`). IBGE's dictionary (xlsx of 2026-11-13) has 1,109 variables for these themes and the basic file; the basic file
has nothing beyond `V0001`-`V0009` (the household head's income is a separate IBGE folder: [tract income](2026-11-21-ibge-tract-income.md); this entry first called it unpublished, which was wrong). Each variable's IBGE description and
unit (people or households) is in `tract_dictionary_2022.parquet`; IBGE publishes no separate universe field, the description states it.

**Counted.** The tracts' sums against the municipal values `load_field` serves from SIDRA (Census 2022), one quantity in two IBGE
products; a suppressed cell is null and left out of the sum.

| Quantity (variables) | Brazil: tracts / SIDRA | Maceió 2704302 | São Paulo 3550308 | municipalities within 1% |
|---|---|---|---|---|
| households on the general water network, `households_water_network` (V00111) | 60,749,055 / 60,775,085 (-0.04%) | 227,505 / 227,599 (-0.04%) | 4,270,787 / 4,271,130 (-0.01%) | 5,480 of 5,570 |
| persons declared black (preta), `population_black` (V01318) | 20,554,615 / 20,656,458 (-0.49%) | 106,661 / 107,251 (-0.55%) | 1,156,511 / 1,160,073 (-0.31%) | 4,006 of 5,570 |
| literate persons aged 15+, `persons_15_plus_literate` (V00748-V00760, 13 age bands) | 150,625,845 / 151,547,694 (-0.61%) | 696,355 / 700,070 (-0.53%) | 9,229,455 / 9,253,336 (-0.26%) | 4,261 of 5,570 |

In all three the tracts fall short of IBGE's municipal figure, by the suppressed cells (as ADR-0203 found for demography); the
shortfall grows with the cells summed (13 bands lose most) and in small municipalities. **Suppressed share of cells**: literacy
14.4% (23.9 M of 166 M), colour or race 11.7%, household part 2 8.8%, part 3 7.6%, part 1 6.4%. Never filled; the municipal series
are the whole-municipality answer.

**Learned.** The bare age bands `V00644`-`V00656` ("15 a 19 anos" ...) are all persons aged 15+, not the literate: their sum is
162.1 M, 7.0% over the 151.5 M literate, while the "Pessoas alfabetizadas" variables (`V00748`-) match to 0.6%. The dictionary's
description does not say so; the reading is the figure's. Read the label before the code.

**Regime.** Branch `ibge-tract-aggregates`, shared data home, 2026-11-21; an ad hoc comparison of `tract_aggregates` sums with
`load_field` (not kept).
