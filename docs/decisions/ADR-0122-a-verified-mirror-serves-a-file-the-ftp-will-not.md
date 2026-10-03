## ADR-0122: When the FTP transfer fails, a public byte-identical mirror serves the file, size-checked and recorded as the mirror

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0003 (the FTP is
the source). The user directed the mirror's use (2026-10-03).

**Context.**
- **The data channel stopped answering.** From 2026-10-03 on, at the
  latest, `ftp.datasus.gov.br` accepted control connections (login, `CWD`,
  `SIZE`) but dropped every passive data connection. The SYN to the assigned
  port (5539–5800) went unanswered, so listings and downloads both failed.
- **The last good transfer** was 2026-10-01 21:48 UTC.
- **SINASC 2021 could not be fetched.** The padded links of ADR-0121 need
  it, and the build had no other source.
- **A public mirror exists.** Raphael Saldanha keeps an S3 copy of
  `/dissemin/publicos` at
  `https://datasus-ftp-mirror.nyc3.digitaloceanspaces.com/`, with the same
  relative paths. Its file index was last modified 2026-10-02.

**Decision.**
1. **Fallback only.** `Fetcher._fetch_one` tries the mirror only after an
   FTP transfer has failed through all of its retries.
   - The mirror copy is accepted only when its byte count equals the size in
     the catalog's listing of the DATASUS server, and only when that size is
     known.
   - It is streamed and hashed exactly like an FTP transfer.
   - It is recorded with `serving_method = "mirror:<url>"`, never as
     `ftp:RETR`, so every blob still says where its bytes came from.
2. **A file absent from both is a recorded gap.** For example CIHA, which the
   mirror does not carry. The gap names both methods.
3. **Once a fetcher has fallen back, it tries the mirror first** for its
   remaining paths (`mirror_first`). Otherwise each file would spend about
   95 s on FTP retries against a data channel that is down.
4. **The FTP stays the source of record.** A path is fetched only when the
   catalog's crawl of the FTP names it, with its size. The mirror never adds
   files.

**Evidence.** EVALUATION 2026-10-03 "The FTP data channel stopped answering;
the mirror is byte-identical".
- **Byte identity.** 8 of 8 files that had been fetched from the FTP, chosen
  at random, have the same SHA-256 on the mirror. 4 CIHA files are not on
  the mirror.
- **DNBR2021.dbc.** The mirror's copy is 131,594,988 bytes, the size the FTP
  reports. It decodes to 2,677,101 records, the official count of 2021 live
  births.
- **Live fallback.** `DORR2021`, `DOAP2021`, `DOAC2021` and `DOTO2021` were
  each served by the mirror at exactly the listed size. The first took 94 s
  (FTP retries first); the rest took about 1 s each.

**Consequences.**
- **A fresh install can still read data** while the DATASUS data channel is
  down, for every system the mirror carries.
- **Equal size is not identity.** A file the mirror holds from an older
  DATASUS publication with an unchanged size would be accepted. The mirror
  is refreshed regularly, and the byte comparison found no such case.
  Provenance shows which blobs came from it, so they can be re-fetched from
  the FTP when it answers.
