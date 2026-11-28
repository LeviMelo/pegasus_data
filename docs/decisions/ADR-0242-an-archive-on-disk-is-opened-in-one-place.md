## ADR-0242: An archive on disk is opened in one place

**Date:** 2026-11-28. **Status:** active. **Request:** the author's review of f30096aa (abnc2027_neuro
`papers/TRIAL_t06b.md`, W7): "replace, never build beside" (CLAUDE.md §4).

**Context.** `decode/archives.py` is the package's archive module: containers told by their first bytes (zip, gzip,
RAR, 7z, tar, LHA), member names that leave the folder refused, quotas, a discovered 7-Zip. It takes an archive's
bytes and returns every member, which is what a DATASUS file needs. `intake.py` did not use it. It opened zips with
`zipfile` in four places (a fixed-width member, a spreadsheet member, a CSV member, a stream of CSV members), each
choosing "the one member" by its own rule and message, and f30096aa added a fifth branch for RAR with its own search
for 7-Zip. None checked a member's name, and each told the container by the file's suffix.

**Decision.** `decode.archives.ArchiveFile` opens an archive on disk and reads one member at a time without holding
it in memory: `names()` (files only, unsafe names refuse the archive), `one(match=, endswith=)` (the single member
asked for, or an error naming what the archive holds), `open(name)`, `extract(name, dest)` (streamed). `intake.py`'s
five sites call it; its own 7-Zip finder and `zipfile` import are removed. `Archive` (bytes in, every member out)
stays for DATASUS files.

**Consequences.** Checked on real files in a scratch home: SENATRAN 2015 (twelve RAR archives) lands 66,840 rows with
motorcycles summing to 237,368,050 and scooters to 44,789,015, as the home holds; IBGE's pairing of 2024 (a zip)
lands 14,690, 51,638 and 1,478,428, as IBGE's table states. A zip named `.rar`, or the reverse, is now read as what it
is. Still open, recorded in ARCHITECTURE §5: spreadsheets are read in six places.
