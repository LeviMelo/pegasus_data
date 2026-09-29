## 2026-08-18 — Dictionary entries need their validity window

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### Dictionary entries need their validity window

With codelists separated, ingesting the modern `TAB_SIH.zip` alongside `TAB_SIH_199201-199712.zip`
still produced **76,115 conflicts** — because the same codelist name genuinely carries different
mappings in different eras. Municipalities were created, merged and renamed across twenty-five
years; both kits are correct for their own window.

Kits name that window in their filename (`TAB_SIH_199201-199712` → 1992-01 to 1997-12; a bare
`TAB_SIH.zip` is current), so `valid_from`/`valid_to` are read from it and made part of the entry
identity. §6.3 already calls for versioned entries; this is what makes the versioning operational.
Six kits now ingest with **5,133 conflicts** — real disagreements within a single window.
