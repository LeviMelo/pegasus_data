## ADR-0002: The listing method is chosen per directory and recorded; a listing that cannot be read is an error, not an empty directory

**Date:** 2026-08-18. **Status:** active.

**Context.** The prior scan of DATASUS reported 124,810 files and success. A
correct crawl finds 207,251 (`docs/history/FINDINGS.md` §0, §3c). Two
mechanisms, both measured on 2026-08-18:

- The server is Microsoft FTP Service on Windows_NT. `MLSD` returns `500
  Command not understood`; `LIST` returns the IIS MS-DOS dialect, which carries
  size and mtime for every entry. The prior parser matched only Unix `ls -l`
  rows, raised on every MS-DOS row, and fell through to `NLST`, which carries no
  metadata: `size` and `modified` were NULL for 124,810 of 124,810 rows
  (FINDINGS §2; defect D4 in `docs/history/pegasus_data_ARCHITECTURE.md` §2).
- `NLST` returns bare names with no type, so an extensionless directory is
  indistinguishable from a file. The old scan recorded `SIASUS/200801_/Dados`
  (54,199 files, SIA outpatient production from 2008) as a file, never listed
  it, and emitted no warning (FINDINGS §0).

Implemented in `7b9488a` and `1aad10a` (2026-08-18).

**Decision.**
- The listing method is chosen per directory (MLSD, then LIST parsed per
  dialect including IIS MS-DOS, then NLST as a last resort) and **recorded per
  row**, because it decides whether size and mtime exist at all (ARCH §5.1).
- A non-empty listing the parser cannot read is a **hard error**, never an
  empty directory.
- An entry that cannot be typed gets a per-file `SIZE` probe; only a
  successful probe makes it a file.
- A directory that cannot be listed becomes a `coverage_gaps` row, retried on
  `--resume` and asserted on by `verify` (defect D6). It is never only a log
  line.

**Alternatives.** The brief's escalation `MLSD → LIST → NLST`, with content
addressing as the fallback where typed listing is unavailable. It is kept as
the escalation order, but its diagnosis ("the protocol gave us nothing") was
wrong: the metadata was always there and could not be read (FINDINGS §2).

**What would reverse it.** A server that returns typed listings everywhere
(MLSD) would make the SIZE probe unnecessary. It would not change the rule that
an unreadable listing is an error.
