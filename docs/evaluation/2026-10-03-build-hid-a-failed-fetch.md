# `build` reported a failed download as an empty success

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- `pegasus-data build --family SINASC_DN_19b47552e2 --years 2021 --uf BR --no-labels --json`;
- log `data/logs/build_sinasc_2021.log`.

**Why it was run.** SINASC 2021 is the padded partner year for the 2022
infant-death and newborn links (ADR-0121). `plan()` priced it at one file,
131,594,988 bytes.

**What happened.**
- The FTP control channel answered: the size and the modification date
  (2025-01-24) came back. The data transfer timed out (WinError 10060) on
  all four attempts.
- `build` printed `"files_attempted": 0`, `"rows": 0`,
  `"errors": []`, the path under `"skipped"`, and exited **0**.
- The cause was recorded nowhere. `fetches` had no row for the file, and
  `build_outcomes` held only "1 of 1 selected files could not be fetched
  or decoded".
- A script that chains on the exit code would have gone on to link 2022
  deaths against a partner year with no rows. That violates "a file that
  would not open is a recorded gap, not an absence" (CLAUDE.md §6).

A first attempt without `--uf BR` also selected the 27 per-state copies of
the same births (28 files). This is not a defect: a family spans every
publication. It is the reason a padded partner year is built with
`--uf BR`.

**The fix.**
- `Builder.build` now copies the fetcher's errors (`last_stats.errors`) into
  the build's `errors`, prefixed `fetch:`.
- The `build` command exits 1 when `errors` is not empty.

**After the fix, the same command** reports
`"fetch: RuntimeError: RETR …/DNBR2021.dbc failed after 4 attempts: [WinError 10060] …"`
and exits 1. The build is retried by a loop (six tries, five minutes apart),
and the padded links wait for a successful try.
