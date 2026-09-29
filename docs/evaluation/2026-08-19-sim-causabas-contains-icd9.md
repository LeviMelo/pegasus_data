## 2026-08-19 — SIM's CAUSABAS contains ICD-9, not malformed data

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### SIM's `CAUSABAS` contains ICD-9, not malformed data

386 of 5,000 sampled values failed ICD-10 shape validation. 338 of those are valid **ICD-9** codes
(`7999`, `7680`, `8199`): SIM ran on CID-9 until 1996 and those years are still on the tree. Filing
them as "malformed" hides a revision boundary and invites someone to clean real records away. The
quality report separates "valid under another revision" from "structurally broken", because one
wants a second reference table and the other wants investigation.
