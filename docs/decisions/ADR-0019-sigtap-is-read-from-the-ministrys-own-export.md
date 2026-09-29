## ADR-0019: SIGTAP is read from the Ministry's own export, over HTTP, with layout-driven parsing

**Date:** 2026-08-19. **Status:** active.

**Context.** The TAB kits carry procedure tables (`TPROC`, `TPROC10`, `EMUSO`)
for their own era, enough to decode a code to a description. Procedure
**attributes** (validity windows, CBO and CID restrictions, financing) need
SIGTAP (`docs/history/FINDINGS.md` §1 V5). Measured on 2026-08-19 (FINDINGS
§3d): HTTPS times out on `sigtap.datasus.gov.br` and
`tabela-unificada.datasus.gov.br`; HTTP on port 80 answers 200. The exports are
on `ftp2.datasus.gov.br/public/sistemas/tup/downloads`: 224 monthly vintages,
200801 to 202608. Every table ships its own fixed-width layout file. Ingesting
the newest export gave 44,984 entries, and `tb_ocupacao` carries 2,719
occupation codes at one width. Reached in `3201d60` (2026-08-19).

**Decision.**
- SIGTAP is sourced from the Ministry's own export channel, over plain HTTP.
- Parsing is layout-driven: the published layout drifts between vintages, so
  a hard-coded parser would be silently wrong today
  (`docs/history/pegasus_data_ARCHITECTURE.md` §14c).
- SIGTAP sits at authority 3 on the ladder (ADR-0008).

**Alternatives.** Recorded in ARCH §14c as rejected: migrating to the SIGTAP
SOAP API, and adopting a third-party mirror. For SIGTAP the Ministry is the
maintainer; there is no upstream to escalate to.

**What would reverse it.** The export channel disappearing, or an HTTPS
endpoint that answers.
