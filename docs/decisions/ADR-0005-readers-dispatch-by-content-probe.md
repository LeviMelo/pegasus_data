## ADR-0005: Readers dispatch by content probe, not by suffix

**Date:** 2026-08-18. **Status:** active.

**Context.** The prior scanner excluded files by extension (defect D1,
`docs/history/pegasus_data_ARCHITECTURE.md` §2). The `.exe` files under
`SIASUS/APAC/` are not programs to skip. Measured on `acac0202.exe` on
2026-08-18 (`docs/history/FINDINGS.md` §1 V2): the stub is `LHA's SFX 2.13S`,
and the payload is an LHA `-lh5-` archive holding seven DBF members.
`PK\x03\x04` and `Rar!` appear nowhere, so the brief's ladder (`zipfile`,
`rarfile`, `7z`, signature scan) failed at every rung except `7z`. Excluding
them by suffix had dropped 1,723 files and the whole APAC system. Composite
suffixes (`.csv.zip`, `.duck.zip`) had broken the prior suffix-stripper into
82 `UNPARSED` families (FINDINGS §1 V10). Implemented in `7b9488a`.

**Decision.** Readers are tried in probe order against the file's actual bytes
(`decode/registry.py`, ARCH §6.2). LHA is decoded in pure Python
(`decode/lha.py`: `-lh0-`/`-lhd-`/`-lz4-` stored, `-lh4-` to `-lh7-`
compressed). It was verified byte-exact against 7-Zip on all seven members.
`7z` remains a fallback for rarer methods, and its absence degrades to a
recorded decode gap. **Never exclude a file by extension** is a prohibition
(ARCH §18).

**Alternatives.** An extension allow-list, rejected as the cause of D1. An
external `7z` as the primary LHA reader, rejected so that the package needs no
external binary.

**What would reverse it.** Nothing foreseen.
