## 2026-08-18 — V8: the Ministry's own denominator stays open

*Split from docs/history/FINDINGS.md §1 V8 on 2026-09-28; text unchanged.*

### V8 — the Ministry's own denominator · **open, with the comparison made cheap**

Not resolvable by reading the tree: it requires reproducing a published federal rate under each
candidate series and seeing which matches. The module ingests POPSVS, POPTCU, POP, projpop and
censo behind one interface precisely so that comparison is a one-line change, and
`load_population` refuses a stratification a series cannot support rather than silently returning
a coarser table. The question stays `open` in `open_questions` with that procedure attached.
