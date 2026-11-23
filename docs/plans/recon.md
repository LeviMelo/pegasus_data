# Plan: exhaustive data recon for a study

Opened 2026-11-23. The ten ABNc studies reported no length of stay, ICU use or cost though every cohort held them, and
used almost none of the 156 context fields, 9,336 SIDRA tables or the census. They were written as scripts beside the
system built to scope a study exhaustively: PegaSUS's topic resolution (`../pegasus_project/ARCHITECTURE.md` §4) over
this package's concept index (`concepts.py`), typed roles and declared fields. The failure is that bypass, and the gaps
in what that system can reach; not a missing tool.

## What exists, and does the job
- **Codes in every system:** `concept_index` (SINAN agravos by their records, SIGTAP compatibility, APAC medicines,
  declared treatments and captures, label matches flagged weakest).
- **Datasets holding the codes in any role**, each with its records; **related codes** learned from co-occurrence with
  FDR; **person paths** through links that pass viability; **contexts**: every declared field (PegaSUS `study.resolve`).
- **Every column of an included dataset is a field or a recorded reason** (PegaSUS `fields.declared`: measure,
  composition or interval from its role; or "draft role", "missing codes undeclared", "unfilled in ..."). Length of stay
  enters any SIH scope by construction.
- **Every exclusion carries its reason** (`scope.yml` `not_read`); the scope is deterministic given declaration and data.

So exhaustiveness comes from declarations, never from a model's judgment about what it has not read. A model's role is
to ADD what declarations do not reach, and every such addition or exclusion is recorded.

## Principles
- **A decision about an item is valid only once its meaning was read.** Fill, type or a label never set an item aside;
  CODANOMAL is nearly empty and is the first column of a congenital-anomaly study.
- **The universe is what the home holds.** What is held but undescribed or unserved is invisible to every scope: a
  defect of this package, found by a check, not by a study.
- **No external vocabulary** (MeSH fits biomedical literature, not SIDRA economics or billing fields, and has no
  Portuguese; DeCS needs a PAHO licence): the data's own code systems carry the subject. **No embeddings** (author).

## Gaps, in dependency order (status 2026-11-23)
1. **Robustness of the index.** `condition_codes` and `dispensed` counted the latest lake year nationally without
   downloading; a year held for some states only raised and took the whole index, and every scope, down (2026-11-23,
   a spina bifida scope). **Done** (212ad192): the latest year held whole.
2. **Holdings check:** every store matched to the variables it holds and the ones described and served; fails on held
   and undescribed. **Done** (212ad192, 9ab512f4, 85673778): 957 variables in 29 stores described from their sources'
   documentation; 0 defects. Left: the Census 2010 microdata's 321 variables are described, not served (a fixed-width
   reader).
3. **Contexts beyond declared fields:** SIDRA's tables reach a scope only once declared as fields (156 of 9,336). A
   scope lists the SIDRA tables and registry variables its places and period can join, from their IBGE metadata, each
   with a recorded decision. **Done** (65846705; PegaSUS cc6795a: `contexts_considered`, `study.body` part).
4. **Procedure seeds:** SIGTAP codes as a topic seed. **Done** (PegaSUS cc6795a, `--sigtap`).
5. **Undeclared missing codes and draft roles** that keep columns out of every scope (`fields.declared` reasons),
   swept per column. Fillers **done** (720887f3: 127 columns of 5,801 measured); the `fields.declared` reasons in progress.
6. **Studies go through it:** the skills make a PegaSUS scope the first step of any study; its `scope.yml` is the data
   extent the paper and the reviewer check. Then the ten ABNc papers.
