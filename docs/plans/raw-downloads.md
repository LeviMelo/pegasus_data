# Plan: the lake as the only stored form of a publication (2026-11-22)

ADR-0208 retired a download once a build's verified partition holds it. It kept on purpose the downloads no partition
holds, "since a query reads it": 22.3 GB on 2026-11-22. Of that:

| Kind | Size |
|---|---|
| SIA | 10.2 GB |
| CNES, read from blobs by design | 3.9 GB |
| SIM, national files read from states | 2.1 GB |
| SINASC | 1.7 GB |
| SIH | 1.4 GB |
| SINAN | 1.4 GB |
| open data | 0.9 GB |
| snapshot versions, kept by ADR-0141 | 1.74 GB, 823 versions |

DATASUS rewrites preliminary and current-year files under the same name (ADR-0141): SIA rose 26% at a first rewrite,
and a dengue "final" was re-issued with 47% of its rows removed. A refetch reproduces the version read only for a file
that has not changed. The snapshot keeps every version of the declared series as protected blobs, and `as_of` reads
them. But it has run once (2026-10-05): its daily task was never registered.

## Units

| Unit | Done when |
|---|---|
| R1 a query that downloads a file the lake does not hold builds it into the lake and releases the blob, unless a snapshot keeps that version | the second read of the year comes from the lake; the blob is gone; ADR-0209 still sends a republished year to the current files |
| R2 CNES registers built into the lake like every other dataset; the fields read the lake | `cnes_*` fields value for value from the lake; 3.9 GB released |
| R3 the existing 22 GB: built where a query or an extract read them, released where a partition or a refetch covers them | `prune --dry-run` lists only snapshot versions and undecodable files |
| R4 the snapshot runs daily (a scheduled task, `scripts/snapshot_task.cmd`) | a version kept on each run day a declared series changes |
| R5 snapshot versions kept as Parquet partitions keyed by their digest; `as_of` reads them; the blobs released | `query(as_of=...)` equal to the blob read for three versions of one file |

R4 needs the author: registering the task is a change to their machine. R5 decides whether any raw download remains.

**2026-11-22 (ADR-0234).** R5 is done as deltas against successors, not partitions keyed by digest. R1 and R2 are done
(a query lands what it downloaded; CNES's fields read through `query`, and one month built covers that month). R3 is
`prune --keep-versions` on the real home, held for the coordinated migration. R4 ran its first scheduled run on
2026-11-22.
