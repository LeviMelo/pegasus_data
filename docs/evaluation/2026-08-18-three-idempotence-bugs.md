## 2026-08-18 — Three idempotence bugs this work exposed

*Split from docs/history/FINDINGS.md §3b on 2026-09-28; text unchanged.*

### Three idempotence bugs this work exposed

Derived state was being *accumulated* rather than *replaced*, in three places, with the same
consequence each time: a correction upstream could not propagate.

* `stratum_members` kept a file listed in the stratum it used to belong to, so a 2008 stratum went on
  claiming a 2020 file's 113-column schema after the date fix moved it.
* Orphaned strata survived re-inventory, dragging `families.time_min` back to 1901 long after the
  facts were corrected.
* `family_files` kept stale links, so the 113-column SIH-RD family pointed at 86-column files and
  normalised **zero rows** — a silent, total failure that produced no error at all.

All three now replace their derived rows, and a stratum whose sample is no longer among its members
is invalidated so the next profile re-derives it.
