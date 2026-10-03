# Which population series the Ministry's tables divide by: POPSVS, measured against TabNet

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; maintainer home `pegasus_data_home` (population series
  built in `lake/population/`).
- TabNet over HTTP: `tabcgi.exe?ibge/cnv/popsvs2024br.def`, "População
  Residente - Estudo de Estimativas Populacionais por Município, Idade e
  Sexo 2000-2025", rows by state, file `pop22.dbf`.
- Client: `sources/tabnet.tabulate`. The FTP data channel was down; TabNet's
  web side answered.

**Why.** OQ-12 asked which population series backs the Ministry's published
rates. Per-capita rates that are to reconcile with federal figures need the
same denominator.

**What TabNet serves.**
- The form's definition (`ibge/cnv/popsvs2024br.def`) reads
  `IBGE\bases\PopSVS2024\POP??.dbf`. Its source note credits RIPSA and
  CGIAE/SVSA, and points to `ftp://…/IBGE/POPSVS/`.
- Brazil 2022: **210,862,983**.

**Each local series, 2022, by state:**

| series | 2022 total | states equal to TabNet |
|---|---|---|
| POPSVS | **210,862,983** | **27 of 27** |
| POPTCU | 406,161,512 (a defect, below) | 0 of 27 |
| POP | no 2022 (2007–2012 only) | — |
| censo | 1991, 2000 and 2010 only in this build | — |
| projpop | state projections; not compared | — |

**Settled.** POPSVS, the RIPSA/CGIAE estimates study, is what the Ministry's
TabNet population tables hold. Its 2022 equals TabNet's in every state.
`load_population` already defaults to it. OQ-12 is resolved.

**A defect found on the way: POPTCU 2022 and 2023 were counted twice.**
- `POPTBR22.zip` and `POPTBR23.zip` (77 KB, against about 35 KB for the
  other years) hold the national table `POPTBR22.dbf` **and** its 27
  per-state parts.
- The population build read every member, so each municipality appeared
  twice, with identical values. The 2022 total read 406,161,512; Sergipe
  read 4,420,008.
- **Fixed in `build.Builder.population`.** When an archive holds a member
  named as the archive itself, that member is the national table and the
  per-state members, which partition it, are not read. The build notes say
  so.
- Rebuild check: see the later section of this entry.

**Mirror coverage, also measured.** The public mirror (ADR-0122) carries CNES,
SIASUS, SIHSUS, SINASC, SIM, SINAN, Dados_Abertos and ESUSNOTIFICA. It
carries no `IBGE/` and no `CIHA/`, so population series and CIHA files cannot
be fetched while the FTP data channel is down.
