## 2026-08-19 — SIGTAP is reachable, over HTTP only

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### SIGTAP is reachable, over HTTP only

HTTPS times out on both `sigtap.datasus.gov.br` and `tabela-unificada.datasus.gov.br`; HTTP/80
answers 200. The exports live on `ftp2.datasus.gov.br/public/sistemas/tup/downloads` — **224 monthly
vintages, 200801 to 202608**. Not "unreachable" and not "not permitted": plain HTTP only, which is a
different finding with a different remedy. Every table ships its own fixed-width layout file, so
nothing hardcodes an offset.

Ingesting the newest export gave 44,984 entries and closed the CBO width problem from a
**first-party** source: `tb_ocupacao` carries 2,719 occupation codes at a single width, where the
FTP tree's CBO file mixes 3,000 three-character CBO-1994 codes with 2,813 six-character CBO-2002
codes in one file.
