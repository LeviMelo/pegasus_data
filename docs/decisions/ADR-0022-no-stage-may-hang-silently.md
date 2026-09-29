## ADR-0022: No stage may hang silently

**Date:** 2026-08-19. **Status:** active.

**Context.** The profile stage hung, and two fetch deadlocks were found: an
unbounded `queue.join()`, and a worker that returned without draining after
failing to connect (`docs/history/pegasus_data_ARCHITECTURE.md` §12). The exit
criterion was set not as "fix the profile hang" but as "the pipeline can never
hang silently". Fixed in `40fd9e7` ("Give FTP transfers a read timeout, and
stop a failed connect from deadlocking") and `21861fe` ("no stage may hang
silently"), 2026-08-19.

**Decision.**
- **Per-item deadline.** Every stage runs its items through
  `run_with_timeout`. An item that exceeds it records a `coverage_gaps` row
  with `kind='timeout'`, and the stage continues. A slow file is a finding,
  not a stop.
- **Heartbeat.** A daemon thread names the item in flight on stderr, flushed.
- **Stall timeout** bounds the stage as a whole, above the per-item deadline.
- FTP transfers have a read timeout. The header census reads through
  `transfercmd` plus `ABOR`, never `retrbinary`, which applies no read timeout
  (ARCH §6.5).
- Both deadlocks are regression-tested.

**Alternatives.** None recorded.

**What would reverse it.** Nothing. The per-item deadline stopped waiting but
did not stop the work, because a thread cannot be killed; ADR-0039 made the
timeout end the work.
