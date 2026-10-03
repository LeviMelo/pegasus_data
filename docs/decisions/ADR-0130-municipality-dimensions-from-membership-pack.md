## ADR-0130: Municipality dimensions come from the membership pack, for any declared municipality column

**Date:** 2026-10-03. **Status:** active. Replaces the `MUNIC_RES`
relations to `CIRBRN` and `CAPITAL` in `joins.yml`.

**Context.**
- **Two mechanisms, one job.** A municipality roll-up in `query()` existed
  for one column only, `SIH.RD MUNIC_RES`, through `joins.yml` relations to
  two codelists (`CIRBRN`, `CAPITAL`). The membership pack
  (`resources/geography.parquet`) separately compiles every classification:
  - the per-system DATASUS tables with their conflicts reported;
  - IBGE's regions;
  - TabNet's current health regions and macroregions (ADR-0126, ADR-0129);
  - IPEA's comparable areas.
- **Every other column had no roll-up at all:** SIM and SINASC `CODMUNRES`,
  `CODMUNOCOR`, SINAN `ID_MN_RESI`, SIA `PA_UFMUN`, and the rest.
- **The catalog's codelist bindings cannot be trusted to say which columns
  are municipalities.** They also bind `CONTADOR`, `CODINST`, `MED_QUIMIO`
  and `NM_MUNIC_H` (a name) to municipality tables.

**Decision.**
1. **`geography.yml` declares `municipality_fields` per system.** These are
   the columns whose values are municipality codes.
2. **`dimensions=["<column>.<classification>"]` resolves through the pack**
   for any declared column and any classification it holds, when no
   `joins.yml` relation of that name exists.
   - The value is the member's label.
   - The publishing system's own claim is chosen when it has one.
3. **Vintage-exact, as the codelist path is:**
   - the membership is resolved for every month of the record's interval;
   - months that disagree yield null;
   - a membership the systems contest, with the querying system having no
     claim of its own, yields null and is counted;
   - an ignored-municipality code (`280000`) yields null.
4. **The `MUNIC_RES` relations to `CIRBRN` and `CAPITAL` are removed.**
   `MUNIC_RES.health_region` resolves through the pack (the same `CIRBRN`
   rows, per system); `MUNIC_RES.is_capital` becomes `MUNIC_RES.capital`.

**Evidence.** EVALUATION 2026-10-03 "Municipality and procedure
dimensions". On SIM-DO SE 2022 (14,791 deaths):
- `CODMUNRES.health_region`, `CODMUNOCOR.ibge_immediate_region` and
  `CODMUNRES.ibge_mesoregion` resolve every row except one;
- the exception is `280000` ("Município ignorado – SE"), left null.

**Consequences.**
- **A roll-up exists for every declared municipality column** of nine
  systems.
- **Adding a classification to the pack adds a dimension everywhere,**
  without a relation.
- **`is_capital` is renamed** (`capital`).
