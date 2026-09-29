## ADR-0004: Fetched files are stored content-addressed by SHA-256

**Date:** 2026-08-18. **Status:** active.

**Context.** The tree is about 207,000 files, and one representative file per
stratum already totals 183 GiB (`docs/history/FINDINGS.md` §3g). Bytes on the
wire are the scarce resource (CLAUDE.md §3). DATASUS moves files, so the same
bytes reappear under new paths (FINDINGS §3c: `BackUp_Ducks_SIASUS_PA` was
replaced by `PA_SIASUS` and `APAC_SIA`). During transitions it publishes the
same content in two trees at once (FINDINGS §3w). Implemented in `7b9488a`.

**Decision.** Every fetched file is stored under `blobs/`, keyed by the SHA-256
of its content (`acquire/cache.py`, ARCH §6.1). Nothing is downloaded twice,
and a re-crawl that finds the same bytes under a new path costs nothing. The
digest is part of an artifact's identity downstream: an aggregate's fingerprint
covers its source blob digests (ARCH §14.15). `verify` asserts deduplication
(`check_blob_dedup`, ARCH §17).

**Alternatives.** Caching by path. Rejected, because a path is not an identity
on this server (ADR-0017): a move would cost a re-download, and a mirror would
cost a second copy.

**What would reverse it.** Nothing foreseen. FINDINGS §3u records the next
lever for rebuild time: a decoded-blob cache keyed by the same digest.
