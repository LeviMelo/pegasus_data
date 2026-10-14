# ADR-0169: a source that exists and cannot be read is a recorded gap, never an absence and never a mismatch

**Date:** 2026-10-14. **Status:** accepted. **Origin:** the ingest review of 2026-10-14 (findings 1, 2, 3, 27).

**Context.** Three consumers read "this source produced no table" three ways. `fetch()` called an archive member it could
not read an *absent member* ("not published", not a gap), so twelve months with one corrupt returned eleven and
`is_complete` was true. `build` counted the file decoded *and* a schema mismatch, recorded no gap, exited 0 and, because
the partition fingerprint hashes the file's digest, never retried it. Only `profile` recorded a gap, with the text
"undecodable". Beneath them, a `.dbc` whose compressed stream failed was handed to the DBF reader, which took the
compressed bytes for records: garbage rows under a correct header (`CAUSABAS='\x1b'`). In the pool the readers' error
text was dropped (the worker sent `detail`, the parent read `error`).

**Decision.**
- **One verdict.** `decode.service.member_verdict(outcome, member)` answers *present*, *absent* or *failed*. *Absent* only
  when the archive was listed and does not hold the member. A member the archive lists that yielded no table, or a source
  nothing could open, is *failed*.
- **One record.** `decode.service.record_decode_failure` writes a `coverage_gaps` row of kind `decode` carrying the
  readers' own error text. `fetch` adds the source to `report.undecoded` (so `is_complete` is false); `build` adds a
  `stats.errors` entry (exit status 1), does not count the file as decoded, and marks the written partition
  `<undecodable>:<fingerprint>` so the next build tries it again; `profile` records the same gap.
- **A damaged container ends the ladder.** A `.dbc` whose header is a DBF's and whose stream fails to inflate raises
  `DamagedPayload`; no other reader is tried. A stream whose first bytes are not a DCL preamble may be a loose DBF named
  `.dbc`: the DBF reader then runs *strict* and refuses a body shorter than its header declares. A DBC declaring zero
  records has no stream and is an empty table, as published.
- **A decoder that dies is the source's gap.** `ItemTimeout`, `IsolatedDecodeError`, `DecodeError` and `OSError` from one
  source no longer leave the pool and abort every partition; the partition that could not be written is an error entry.
- The pool carries `failed_members` and the readers' error text across the process boundary.

**Evidence.** Of 6,551 real blobs up to 8 MB that start with a DBF version byte (blob store, 2026-10-14), 6,543 inflate
as DBC and 8 are loose DBFs read by the DBF reader; none fails and none declares more records than it holds (a first
sample of 2,283 had refused three under the old reader: two loose DBFs and one zero-record file, now read as empty). A
`.dbc` of a valid header and random stream used to return 331 rows; it now returns none and names the failure. An archive
of one good, one truncated and one random-stream member: verdicts present, failed, failed; a name not in it, absent.

**What would overturn it.** A DATASUS family whose DBCs declare more records than they hold: strictness is then the
reader's to relax per family, and the measurement above to repeat on that family.
