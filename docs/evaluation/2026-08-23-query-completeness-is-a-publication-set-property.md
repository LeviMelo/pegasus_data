## 2026-08-23 — Query completeness is a publication-set property

*Split from docs/history/FINDINGS.md §3n (first) on 2026-09-28; text unchanged.*

## 3n. Query completeness is a publication-set property (2026-08-23)

The external follow-up review correctly identified that “some lake partition
exists” cannot choose the source for an entire query. Completeness is now
evaluated for each requested year against the selected logical publications and
the `source_paths` recorded in lake partitions. A partially built year routes as
one unit to fetch; complete and incomplete years can form a non-overlapping
hybrid. Comparing logical publication identity, rather than the current physical
suffix, also means a lake built from DBC remains complete if Parquet later
becomes the preferred representation.

Three related lessons were established while closing that review:

1. **Semantic axes are descriptive knowledge, not retrieval predicates.**
   `MUNIC_RES`, `MUNIC_MOV`, `DTOBITO` and `DT_INTER` remain documented because
   their meanings matter, but source capabilities contain only publication
   resolution and physical partition coordinates.
2. **Semantic vintage belongs to the row.** A multi-year dimension lookup must
   select the packed relation for each row competence/year. Choosing one current
   table for the result silently rewrites historical categories.
3. **A committed adjudication must be visible across connections.** The apply
   path previously issued two uncommitted `execute()` calls, so the writer saw
   its decision while a query opened immediately afterward did not. Applying a
   relation and closing its work item is now one committed transaction; the
   ordinary renderer and dimension resolver share the effective relation view.

Representation conflicts now block analytical execution. In particular, two
same-format objects claiming one logical publication are evidence of a revision,
collision or stale mirror—not a reason to prefer the smaller file. Expert
inspection may explicitly retain all alternatives, but the default cannot emit
duplicate facts.
