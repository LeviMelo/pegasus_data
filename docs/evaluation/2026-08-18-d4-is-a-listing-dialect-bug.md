## 2026-08-18 — D4's root cause is a listing-dialect bug, not a protocol limitation

*Split from docs/history/FINDINGS.md §2 on 2026-09-28; text unchanged.*

### D4's root cause is a listing-dialect bug, not a protocol limitation

The brief's design rule proposes escalating `MLSD → LIST → NLST` per directory and falling back to
content addressing where typed listing is unavailable. Both are good rules and both are
implemented. But the diagnosis was incomplete.

Measured: the server is **Microsoft FTP Service on Windows_NT**. `MLSD` returns
`500 Command not understood`. `LIST` works and returns the **IIS MS-DOS dialect**:

```
05-29-15  04:10PM                18550 acac0201.exe
02-24-18  07:38AM       <DIR>          199201_200712
08-17-26  10:07PM              6005360 TAB_SIH.zip
```

which carries **both size and mtime for every entry**.

The prior implementation's `_LIST_UNIX` regex matches only `ls -l` output. Every MS-DOS row failed
it; `_parse_list` then raised `"LIST returned rows but parser did not understand them"`; the
fallback chain ran to `NLST`, which carries no metadata at all. That is why
`inventory_files.size` and `.modified` are NULL for 124,810 of 124,810 rows.

So D4 is not "the protocol gave us nothing". It is "we asked correctly and could not read the
answer". `discovery/listing.py` parses both dialects and — importantly — treats a non-empty
listing it cannot parse as a **hard error**, never as an empty directory. Conflating those two is
how a whole subtree disappears silently.

Measured on a 9,667-file slice: **9,667 of 9,667 files carry both size and mtime.**
