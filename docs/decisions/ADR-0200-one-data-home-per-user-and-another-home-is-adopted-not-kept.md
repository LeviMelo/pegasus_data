# ADR-0200: One data home per user, and another home is adopted, not kept

2026-10-24. Status: active. Supersedes the walk-up default of `locate.default_data_home` (2026-09).

## Context

A process that named no root resolved its data home from the working directory: the nearest `pegasus_data_home/` at
or above it, else a new one beside it. PegaSUS kept its own variable (`PEGASUS_DATA_ROOT`) and pinned pegasus_data to
it; pegasus_data read `PEGASUS_DATA_HOME`. On 2026-10-24 this machine held eight homes. Another project's pipeline had
fetched 11.6 GB of SIH and SINAN (3,763 files) into the repository's home on 23/10, while the per-user home
(`C:\Users\Galaxy\pegasus_core_data`, 93 GB) already held most of those years. Only 6 files were byte-identical:
DATASUS had republished the rest since the per-user home's crawl.

## Decision

1. **One home per user.** With nothing set, the root is the per-user data directory:
   * `%LOCALAPPDATA%\pegasus-data` on Windows;
   * `~/Library/Application Support/pegasus-data` on macOS;
   * `$XDG_DATA_HOME/pegasus-data` elsewhere.

   It is never derived from the working directory. The per-user config file (`pegasus-data config set --user --root`)
   names the home once for every process of the user. A project that wants a home of its own writes a project
   config. This machine's config names `C:\Users\Galaxy\pegasus_core_data`.
2. **One name.** PegaSUS resolves its data root through pegasus_data (`locate.resolve_placement`), so
   `PEGASUS_DATA_HOME` is the only variable and `PEGASUS_DATA_ROOT` and `PEGASUS_POPULATION_ROOT` are gone.
3. **Another home is adopted, then removed** (`pegasus-data adopt OTHER [--apply]`, `pegasus_data.adopt`).
   * Moved across: what that home acquired. These are the blobs its fetch history names (each digest checked) with
     their fetch rows, and the registry files absent here.
   * Not moved: what it derived (lake partitions, links, fields, aggregates, population series, semantic tables).
     These were computed by the code of their day and are recomputed here from the adopted downloads, so no stale
     product is read as current.
   * Files present on both sides keep this home's copy.
4. **The latest fetch of a path is read by time** (`fetched_at`, then id), so an adopted older fetch never shadows a
   newer one.
5. **The server's two clocks are one instant.** LIST shows the server's wall clock, which is UTC−3 for every date
   (the pre-2019 summer-time months included). MDTM shows UTC. A catalog holds both, because MDTM answers whenever
   LIST cannot or the listing is stale. The freshness check (`Fetcher._should_skip`) and crawl reconciliation
   (`reconcile.classify`) take two times exactly that far apart as one instant (`listing.same_instant`). Without
   this, a crawl after an outage judged 563 unchanged files republished.

The repository's `pegasus_data_home/_catalog/` remains as the label pack's build catalog, which the maintainer scripts
read by path. It holds the dictionary, code tables and kits, 13 GB that exist nowhere else. No command adopts it as a
home. Its downloads are in the one home.

## Evidence

Evaluation 2026-10-24-one-data-home. In summary:
* adoption moved 5,963 blobs (16.9 GB, every digest valid), 11,659 fetch rows and 95 registry files (2.85 GB);
* no stray home kept a blob the one home lacks;
* the fetcher now holds 2,455 of 2,484 SIH-RD files of 2015 and 2020–2026, and 16 of 27 SINAN dengue files;
* 20 of 49,083 latest fetches are judged changed, every one a real republication (its size differs).

## Consequences

* A fresh-install check still needs its own empty home: `scripts/live.py` sets one.
* Every copy it downloads is a second copy, until adopted.
* A stray home found later is cleared with `adopt --apply` followed by deleting the folder.
