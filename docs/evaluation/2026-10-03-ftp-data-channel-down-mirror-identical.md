# The FTP data channel stopped answering; the mirror is byte-identical

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- this machine's public IP 201.149.104.98.
- Probes (curl, Python `ftplib` and sockets) were run in the session. Their
  ongoing record is `data/probes/ftp/data_channel.jsonl`, written every 15
  minutes by `data/logs/ftp_probe.py`.

**Why.** SINASC 2021 (`DNBR2021.dbc`) would not download, and the session
first called this an "outage" without evidence. The user challenged that.
What follows is what was established and what was not.

**What the server does (2026-10-03, about 04:30–05:15 UTC).**
- **The control channel works** (port 21): login, `CWD` down to `DNRES`,
  `SYST` (`Windows_NT`), `FEAT`, and `SIZE` (131,594,988 for DNBR2021).
- **Every passive data port is dropped.** Of 14 `PASV`/`EPSV` replies
  (ports 5539–5800), none accepted a connection. The SYN went unanswered
  until the 21 s Windows limit, which is a filter, not a refusal.
- **Listings fail too**, since they also need a data connection.
- **Active mode** was refused (`501`). This is expected from behind NAT, and
  proves nothing.

**What this machine does.**
- Windows firewall: all profiles allow outbound traffic.
- portquiz.net answered on port 5764, the very port DATASUS had assigned.
- Passive FTP to `ftp.ibge.gov.br` listed a directory in 0.6 s. Passive FTP
  works here.
- The last successful DATASUS transfer was 2026-10-01 21:48 UTC.

**Not established: whether every client is affected.**
- check-host.net nodes in Cyprus and Iran also timed out on a passive port.
  That is inconclusive, because a stateful FTP firewall opens a passive port
  only for the client of the session.
- A full transfer from another network was not run: ftptest.net requires an
  anti-bot proof, which was not attempted.
- The user judges an IP block on this address astronomically improbable.

**The mirror.**
- **Byte comparison.** 12 files fetched from the FTP on 2026-09-30 were
  chosen at random.
  - 8 are on the mirror, and all 8 have the same SHA-256 (SIH RD, SIA PS).
  - 4 (CIHA) are not on the mirror.
- **DNBR2021.dbc from the mirror.**
  - Size: 131,594,988 bytes, equal to the FTP's `SIZE`; downloaded in 28 s.
  - Adopted as `mirror:<url>`, then built with `build --family
    SINASC_DN_19b47552e2 --years 2021 --uf BR --no-labels`: 2,677,101 rows.
  - That is the official count of 2021 live births in SINASC (Fiocruz
    PCDaS's release note for the 2021 data; Ministry of Health), so the
    file is the DATASUS publication.
- **The fallback in the fetcher (ADR-0122), live.**
  - DORR2021, never fetched before in this home: FTP failed after 94 s;
    the mirror served 355,267 bytes, the listed size.
  - DOAP2021, DOAC2021 and DOTO2021 in one run: the first took 94 s, the
    others 0.9 s and 1.0 s (mirror first). All three match their listed
    sizes.
