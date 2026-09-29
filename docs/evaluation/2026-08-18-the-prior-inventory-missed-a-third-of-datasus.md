## 2026-08-18 — The previous inventory of DATASUS was missing a third of it

*Split from docs/history/FINDINGS.md §0 on 2026-09-28; text unchanged.*

## 0. The headline

**The previous inventory of DATASUS was missing a third of it, and said nothing.**

A full crawl finds **207,251 files**. The prior scan found 124,810 and reported
success. The 82,441-file difference is not attrition or churn; it is one
mechanism, and it is worth stating exactly:

> FTP's `NLST` command returns **bare names with no type information**. An
> extensionless directory name is therefore indistinguishable from a file. The
> old scan recorded `Dados` as a *file* under `SIASUS/200801_`, and `uploads` as
> a *file* under `/dissemin/publicos`. Because it believed they were files, it
> never listed them, and because nothing failed, it **never warned**.

Behind `Dados` sat **54,199 files** — SIA outpatient production, 2008 to the
present, the largest single dataset on the tree. It was absent from the
inventory under a clean bill of health.

That is the failure this project exists to make impossible, and it shapes
everything else here: an entry that cannot be typed gets a per-file `SIZE`
probe and only a successful probe makes it a file; a directory that cannot be
listed becomes a `coverage_gaps` row rather than a silence; an item that stops
responding is abandoned, recorded, and reported rather than waited on forever.
A gap you can query is a different thing from a gap you cannot see.
