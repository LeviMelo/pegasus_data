## 2026-08-18 — V5: procedure tables are in the kits; SIGTAP attributes are not

*Split from docs/history/FINDINGS.md §1 V5 on 2026-09-28; text unchanged.*

### V5 — procedure table / SIGTAP · **resolved: in the kits, with a caveat**

A procedure code table **is** present inside the kits — `TPROC`, `TPROC10`, `EMUSO`, `EMUSO10`,
each `IP_COD` → `IP_DSCR` with a group code `IP_GP`. Code→description decoding needs nothing
further.

The caveat that matters: these are TabNet's procedure tables *for the kit's own era*, not the full
SIGTAP release. Anything depending on procedure **attributes** — validity windows, CBO and CID
restrictions, financing type, service/classification links — still requires SIGTAP from
`sigtap.datasus.gov.br`. The distinction is recorded in the resolution text rather than being
glossed as "solved".
