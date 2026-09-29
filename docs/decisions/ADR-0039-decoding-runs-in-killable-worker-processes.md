## ADR-0039: Decoding runs in a pool of persistent, killable worker processes

**Date:** 2026-08-22. **Status:** active.

**Context.** ADR-0022's per-item deadline was never cancellation.
`run_with_timeout` joins a daemon thread with a deadline, and on expiry stops
waiting, which is all Python can do: a thread cannot be killed, and DBC
inflation ran inside a native extension that never yields. A file recorded as
"abandoned after 1200s" kept a core, an inflated DBF and temporary disk while
the API moved on, and several accumulated
(`docs/history/pegasus_data_ARCHITECTURE.md` §12.1). Built in `31c5930`
(2026-08-22, "Decode in a killable process, so a timeout ends the work").

**Decision.**
- Decoding runs in a small pool of **persistent** worker processes
  (`decode/isolation.py`, `decode/_worker.py`). On expiry the parent kills the
  worker and starts a fresh one, so "abandoned" means the work stopped.
- The unit of work is one **physical source**, not one logical member, so an
  archive with seven selected members is inflated once.
- Batches are framed individually across the pipe, so neither side holds a
  whole decoded table. Framed batches spool to disk, and any failed or
  incomplete reply retires the worker (second review closure,
  `docs/history/DEFECTS.md`).
- Workers run as `python -m pegasus_data.decode._worker`, not through
  `multiprocessing`, because a library imported from a notebook, a REPL or a
  frozen application cannot rely on a guarded `__main__`.

Measured cost of the boundary on a real 208-column payload: Arrow IPC
serialise plus deserialise is 1% of decode.

**Alternatives.** Threads with deadlines (the prior state), rejected because
they cannot stop work. Per-file processes, rejected because interpreter
start-up per file would swamp the decode.

**What would reverse it.** Nothing foreseen. The IPC pipe is also why a
decompressor that prints to stdout is unacceptable (ADR-0059).
