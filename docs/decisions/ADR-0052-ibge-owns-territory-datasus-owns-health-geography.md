## ADR-0052: IBGE owns territorial identity; DATASUS owns the health-service geography; every membership says which

**Date:** 2026-08-27. **Status:** active.

**Context.** Audited against IBGE's Localidades API
(`docs/history/IBGE_LOCALIDADES.md`; `docs/history/FINDINGS.md` §3p, second;
commit `5096c8a`, 2026-08-27):

- Compared as partitions, `MICROBR` is IBGE's microrregião exactly (558
  groups against 558, none split). `MESOBR` differs only by filing three
  municipalities under "Ignorado". Label comparison had suggested 74% and
  14.3% agreement, because `.CNV` labels are truncated.
- IBGE retired meso- and microregions in 2017 and replaced them with Regiões
  Geográficas Imediatas (510) and Intermediárias (133). Neither appeared in any
  of the 2,348 shipped codelists.
- IBGE has no health regions: the Região de Saúde, the colegiado and the
  macroregion are Ministry constructs.
- Only three IBGE municipalities are absent from `BR_MUNICIPALFA`, two of them
  explicable.

**Decision.**
- IBGE is the authority for territorial identity and for the current
  regionalisation. The immediate and intermediate regions ship alongside the
  legacy meso/micro pair, which stays because thirty years of health data is
  tabulated against it.
- DATASUS is the authority for the health geography it invented.
- Every membership carries an `authority` column, and a test refuses a
  classification claimed by both.
- The raw IBGE payload does not ship (2.5 MB of JSON against a 152 KB
  compiled pack, re-fetchable in a second).
- Rows compiled from IBGE's endpoint carry empty validity windows, because the
  endpoint returns today's division and the vintage is unknown.

**Alternatives.** Replacing DATASUS geography with IBGE's. Rejected:
municipality coverage was nearly identical, and IBGE has no health regions.

**What would reverse it.** Nothing foreseen. Wiring in IBGE's historical
divisions is the recorded next step.
