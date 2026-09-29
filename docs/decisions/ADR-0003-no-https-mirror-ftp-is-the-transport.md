## ADR-0003: There is no HTTPS mirror; FTP is the transport

**Date:** 2026-08-18. **Status:** active.

**Context.** The brief wanted an HTTPS mirror of the tree to restore
`Content-Length` and `Last-Modified` and so remove defect D4. Measured on
2026-08-18 (`docs/history/FINDINGS.md` §1 V1): `ftp.datasus.gov.br` accepts
nothing on ports 80 or 443; both connections time out. `FEAT` on the live
server reports `SIZE`, `MDTM` and `REST STREAM`, so per-file metadata is
available on demand and interrupted transfers can resume. The metadata D4
lacked was always available over FTP (ADR-0002).

**Decision.** FTP is the only transport to the DATASUS tree. The mirror probe
(`discovery/https_client.py`, ARCH §3.1) settled the question and is not part
of the fetch path. Transfers resume with `REST STREAM`.

**Alternatives.** *An HTTPS mirror*: rejected, because none exists. SIGTAP,
which lives on other hosts, has the opposite answer: plain HTTP answers and
HTTPS does not (ADR-0019).

**What would reverse it.** DATASUS publishing the tree over HTTPS. Transfers
could then use HTTP range requests, and the ranged header read of ADR-0024
would become a plain `Range:` request.
