## 2026-08-18 — V11: the 32 failed directories

*Split from docs/history/FINDINGS.md §1 V11 on 2026-09-28; text unchanged.*

### V11 — the 32 failed directories · **resolved**

Re-crawling with per-directory verb escalation resolves them. `SIHSUS/Doc` returns a genuine
`550 The system cannot find the file specified` — the path does not exist, as distinct from being
unreachable — and anything still failing after backoff persists as a `coverage_gaps` row rather
than a log line.
