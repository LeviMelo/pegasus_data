## 2026-08-18 — V1: there is no HTTPS mirror, and none is needed

*Split from docs/history/FINDINGS.md §1 V1 on 2026-09-28; text unchanged.*

### V1 — HTTPS mirror · **resolved: no mirror, and none needed**

`ftp.datasus.gov.br` accepts nothing on :80 or :443; both connections time out. There is no HTTPS
mirror of the tree.

The mirror was wanted because it would restore `Content-Length` and `Last-Modified`, eliminating
defect D4. That turns out to be unnecessary — see §2 below — because the metadata was always
available over FTP and the prior scan simply could not read it.

`FEAT` on the live server reports: `LANG EN*`, `UTF8`, `AUTH TLS;TLS-C;SSL;TLS-P;`, `PBSZ`,
`PROT C;P;`, `HOST`, `SIZE`, `MDTM`, `REST STREAM`. `SIZE` and `MDTM` give per-file metadata on
demand, and `REST STREAM` means interrupted transfers are resumable.
