# IBGE road and waterway links 2016 (2026-10-25)

`sources/ibge_links.py` `build()`: IBGE's *Ligações Rodoviárias e Hidroviárias 2016* (65,638 municipality pairs) as two weighted
graphs, `registries/mobility/road_links_2016.parquet` and `waterway_links_2016.parquet`. Regime: branch `mob-links` at
`a1b70be` plus this change, data home `C:\Users\Galaxy\pegasus_core_data`, 2026-10-25; source files kept in `registries/ibge_links/`
(workbook, `leiame.txt`, centrality, "sem objeto" list, and the publication PDF `liv100602.pdf` read for the methodology).

**What a row means** (sources: `leiame.txt`; the book's Notas técnicas, PDF pp. 12-16; the workbook's dictionary sheet)
- Node = municipality seat ("A unidade espacial de investigação da pesquisa é o município"); arrangements are not nodes (their members
  keep individual links outward; legs inside one are out of scope).
- `weight` = weekly departures of the pair, **both directions summed** ("As frequências foram agregadas, ida e volta"): an undirected
  total, written in both directions with the full value (the table sums to twice the pair total). Fortnightly x0.5, monthly x0.25;
  vehicles weighted (bus 1, van/car 0.25; voadeira 0.25, lancha/catamarã 1, barco 1.5, navio 2): a capacity-weighted count.
- Road = `VAR06` > 0 (65,121 pairs), waterway = `VAR05` > 0 (405 pairs; 31 pairs have both). `VAR07` = `VAR05` + `VAR06` on all rows.
  Cost (R$) and time (min) are pair minima over all services; `weekly_without_cnpj` (`VAR12`) is the informal-transport proxy;
  `has_imputed_section` is `VAR13`.

**Counted.** 65,638 pairs, none repeated (not even reversed), none self-linked; 5,420 nodes: 5,385 Brazilian municipalities and 35
South American cities (codes 80xxxxx-92xxxxx). The 143 pairs touching those cities (981 departures) are *unplaced* (not IBGE
municipalities) and in neither graph. Written: road 130,242 rows over 5,322 municipalities (3,134,116 weekly departures over pairs),
waterway 810 rows over 140 municipalities (10,343.25). Every Brazilian code is in the municipality pack.

**Checks against the book's own figures**
| Figure printed | Built |
|---|---|
| 65,638 links (press release 2017-06-30) | 65,638 |
| 5,386 municipalities surveyed (centrality table) | 5,386 rows in the centrality workbook; the pairs hold 5,385 Brazilian nodes, 3 municipalities of the table (4313011, 1709807, 4304663) have no pair and 2 in pairs (5107800, 5101605) are absent from it |
| top pair Carpina-Paudalho, 2,855 weekly (p. 20) | Carpina-Paudalho 2,855 (next: Cabo de Santo Agostinho-Escada 2,424) |
| Tabela 2, South American countries (p. 22) | all seven equal (PAR 391, ARG 224, VEN 150, URU 123, BOL 76, PER 9, CHI 8; total 981) |
| Tabela 2, states (a pair counted under each state it touches) | 5 exact to 0.1 (AC, RR, AP, MT, DF); the rest within 0.6 % in either direction, except AM (-3.2 %) and RS; the sum over pairs 3,145,440 vs "Brasil" 3,148,078.8 (-0.08 %) |
| Tabela 3, waterway total 11,835.8 | 10,343.25 (-12.6 %), unexplained: the table is by REGIC hierarchy of the end points |

The state differences are small and mostly low (the book's tables were computed before the final workbook, a reading
not verifiable here). Two printed values are not reproducible: **RS is printed as 260,613.3, identical to PR** (built RS 235,391.5,
PR 260,388.25: a transcription slip in the book), and AM 7,541.3 vs 7,301.25. Nothing was adjusted to match.

**Not resolved.** `weight` of the 31 mixed pairs is mode-specific (road part in the road graph, boat part in the waterway one);
`min_cost_brl` and `min_travel_minutes` are the pair's minimum over both modes. The survey's date within 2016 is not stated in the
files read.