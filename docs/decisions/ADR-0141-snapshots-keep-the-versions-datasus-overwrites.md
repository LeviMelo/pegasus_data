## ADR-0141: Snapshots keep the versions DATASUS overwrites

**Date:** 2026-10-05. **Status:** active. **Request:** PegaSUS ADR-0004 (surveillance needs revision histories); evidence in PegaSUS `docs/evaluation/2026-10-05-surveillance-lags.md`.

**Context.**
- DATASUS rewrites preliminary and current-year files under the same name: SIA rises 26% at its first rewrite, SIM preliminary 2025 fell 4%, a DENG final was re-issued with 47% of its rows removed.
- The catalog keeps only the latest size and mtime of a path, and `fetches` records a version only when a query happens to download it. A history cannot be recovered afterwards.
- The blob store is already content-addressed and immutable, and `fetches` already keeps one row per download (path, sha256, listed size and mtime). Only the *deliberate, protected* history was missing.
- Since 2026-10-03 the FTP data channel (every LIST and every transfer) does not answer from this machine (ADR-0122); the control channel (MDTM, SIZE) does.

**Decision.**
1. **`pegasus-data snapshot`** (`snapshot.snapshot()`) keeps every changed file of the series declared in `curation/snapshots.yml` (SINAN, SIM and SINASC preliminary; SIH-RD, SIA-PA and CNES-ST of the last 14 competences; the state lists of SIH and SIA are a disk budget). It deletes nothing.
2. **Replace, not beside.** The bytes go through the existing `Crawler` (one connection), `Fetcher` (one connection) and `BlobStore`. The one new object is `snapshot_versions (path, sha256, modified, size, first_observed_at, last_observed_at, observations, serving_method)`, local to the data home and not in the seed. It differs from `fetches` in three ways: it is written only by a snapshot, from a listing taken in the same run (a query's `fetches` row carries the last crawl's listing, which can be stale); it records the runs that found a version still current; and `BlobStore.prune_verified` never deletes a blob it names.
3. **A file is fetched only if its listed size or mtime differs from its latest version**, or it has none. A copy an earlier query fetched from DATASUS at exactly that size and mtime is adopted without a download.
4. **Observation.** By directory listing when one answers within 20 s; otherwise by `MDTM`/`SIZE` of each declared file over the control channel, the names coming from the catalog and the mirror's key list. DATASUS stays the authority on what the file is.
5. **Transport.** When DATASUS cannot transfer, the mirror's copy is taken as the version only when its size and its stored original mtime (`x-amz-meta-mtime`) equal DATASUS's answer; otherwise the file waits. The version records `mirror:<url>` as its serving method.
6. **Reading.** `pegasus-data snapshot --versions TEXT` lists the versions of matching paths; `query(..., as_of="2026-09-30")` (`--as-of` on the CLI) reads each source file as the version whose server mtime is the latest on or before the date, with no network and no lake. A file with no version by then is an acquisition failure, never answered with a later state.
7. **Budget.** A run refuses to start under 4 GiB of free RAM, if it would leave under 10 GiB of disk, or above `--max-gb` (5) of new bytes, and reports bytes downloaded, versions kept and store size.

**Limits (to state, not hide).**
- A version overwritten twice between two runs is lost; the history is as dense as the schedule (daily, RUNBOOK §8).
- FTP mtimes have minute resolution; two rewrites in one minute with equal size are one version.
- Observation by `stat` cannot discover a file name neither the catalog nor the mirror knows.

**Evidence.** EVALUATION 2026-10-05 "Snapshot".

**What would overturn it.** A DATASUS publication of its own revision history, or measuring that no series changes between daily runs (then weekly is enough).
