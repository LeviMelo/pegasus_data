## ADR-0126: Health macroregions and current health regions come from TabNet's current territorial tables; comparable areas from IPEA

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0049, ADR-0052.
Reverses ADR-0049's exclusion of the health macroregion, on the condition
that ADR-0049 itself named: "a Ministry source for health macroregions".

**Context.**
- **Macroregions were not shipped** (ADR-0049, OQ-9). The kits' copies
  contradict each other: `BR_MACSAUD` names a different macroregion for 66%
  of municipalities depending on the publishing system, and `MSAUDBR` for
  4%.
- **TabNet uses one current table.** Its current population tabulation
  (`ibge/cnv/popsvs2024br.def`) classifies municipalities by health
  macroregion and health region, with `territorio\br_macsaud.cnv` and
  `territorio\br_regsaud.cnv`. TabNet serves both over HTTP at
  `http://tabnet.datasus.gov.br/cgi/territorio/<table>.cnv`, while the FTP
  data channel is down. That is one current table per classification, with
  no per-system copies.
- **Long series break when municipalities split.** The PegaSUS lineage
  used minimum comparable areas (AMC) for this; the project had none. IPEA's
  geobr publishes them for any pair of census years up to 2010, generated
  with Ehrl's routine (2017, Estudos Econômicos 47(1)), as GeoPackages.

**Decision.**
1. **`curation/geography.yml` gains `tabnet_classifications`:**
   - `health_macroregion`, from `br_macsaud`;
   - `health_region_current`, from `br_regsaud`.

   `sources/tabnet.fetch_territorial` reads them, and the one CNV parser
   parses them. `health_region` keeps each system's own CIRBRN assignment,
   which reconciles with that system's totals. `health_region_current` is
   the one current regionalisation for system-neutral roll-ups.
2. **`ipea_classifications`:** `comparable_area_1980_2010`, `_1991_2010`
   and `_2000_2010`, from IPEA's GeoPackages read as SQLite
   (`sources/ipea_amc.py`). Only `code_amc` and the 2010 member list are
   read, so no GIS library is needed.
3. **The pack records each row's authority:** `datasus`, `ibge`, `tabnet`
   or `ipea`.
4. **`pegasus-data geography` compiles the pack from all four.** It
   replaces a pack built by hand once, which had fallen behind the label
   pack it is compiled from: health colegiado 27,790 rows from the pack's
   own codelists, against 32,241 today.
5. **What stays unassigned is left unassigned.**
   - Alta Floresta D'Oeste (110001) is absent from TabNet's macroregion
     table.
   - Municipalities created after 2010 belong to no published AMC.
   - Neither is given a guessed parent.

**Evidence.** EVALUATION 2026-10-03 "Geography from TabNet and IPEA".
- **Macroregions:** 124 over 5,569 of 5,570 municipalities, plus 36
  Federal District administrative regions (5300xx).
- **Current health regions:** 446.
- **AMCs:** 3,829 (1980–2010), 4,298 (1991–2010) and 5,476 (2000–2010). The
  PegaSUS record gives 3,830 for its 1980s version.

**Consequences.**
- **OQ-9 is settled for today's division.** History is not: OQ-11 still
  holds for both TabNet tables, which carry no vintage.
- **The pack depends on three network sources at build time** (IBGE,
  TabNet, IPEA). The registries cache under `<root>/registries/`.
