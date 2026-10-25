# ADR-0208: A home keeps the Parquet, not the download, and no folder outside the one home holds pegasus data

2026-10-24. Status: active. Amends ADR-0200 (the repository's build catalog; an adoption ends in a removal) and the
default of `build_lake(release=)`.

## Context

On the evening of 2026-10-24 this machine had 6.9 GB free of 931 GB. Measured with each file counted once and no
junction followed (evaluation 2026-10-24-disk-one-home):

* **Downloads kept beside their Parquet.** The one home's blobs held 33.5 GB:
  * 13.6 GB were latest versions whose records a verified partition holds (10.2 GB of them SIH-RD);
  * 17.4 GB were latest versions that no partition holds, read by queries (SIA-PA 6.9 GB, SIA-BI 3.5 GB);
  * 1.7 GB were snapshot versions and 0.7 GB superseded versions.

  A build kept every file it read. Only `build_lake(release=True)` and `extract` released theirs. `prune` existed, but
  nothing ran it.
* **Homes outside the one home.** The homes adopted under ADR-0200 were left on disk, and more had been made since.
  There were 23 folders with a catalog (15.4 GB) and 6 without one, and none held a usable blob or a registry file
  the one home lacks:
  * `pegasus_linkage` held 10.0 GB, 6.75 GB of it a derived lake;
  * live checks, temp homes and agents' scratch homes held the rest.
* **Test homes.** pytest kept three runs of test homes, 3.4 GB each.
* **The repository's home.** `pegasus_data_home/` held the label pack's build catalog (13.2 GB) beside 4.3 GB of
  copies.

## Decision

1. **A build releases its downloads.**
   * After writing, `Builder.build` deletes the selected files' blobs whose every fetched path a verified partition
     holds (`BlobStore.prune_verified(paths=…)`; ``released`` in the counts). Snapshot versions are always kept.
   * `Settings.keep_downloads`, set as `keep_downloads` in a config file, keeps them, and so does
     `build --keep-downloads`.
   * `build_lake` follows the same rule; its own release code is gone.
   * A rebuild fetches a released file again (ADR-0122). A download that no partition holds stays where it is, since a
     query reads it.
2. **The label build catalog lives in the one home**, at `config.label_build_catalog()`
   (`<root>/_label_build/catalog.sqlite`), beside that home's catalog and never as it. The maintainer scripts read it
   there. The repository holds no `pegasus_data_home/`.
3. **An adoption ends in a removal.** `adopt --apply --remove` deletes the other home once adopted:
   * a junction or a link inside it is removed as a link, never followed;
   * a folder that is this home, holds it or lies inside it is refused;
   * a home with a blob failing its digest is kept.
4. **A live check leaves nothing.** `scripts/live.py` makes a new home for each run, then adopts and removes it.
   `--home` keeps one across runs.
5. **Test homes go with a passing run** (`tmp_path_retention_policy = "failed"`, one run kept).

## Evidence

Evaluation 2026-10-24-disk-one-home. In summary:
* 23 stray homes were adopted and removed (15.4 GB), 6 without a catalog deleted, and every remaining blob and
  registry file was checked against the one home first;
* the build catalog was moved, keeping its 22,352,861 dictionary rows (`quick_check` ok);
* SIH-RD AC 2025 was built: 1 partition reused, 1 rewritten (52,796 rows), 11 downloads released (4.0 MB);
* then queried with `max_download=0`: 1,361 records came from the lake in 2.5 s, equal to the nees-gt-ms extract of the
  same filter.

## Consequences

* Downloads built before this stay until `prune` runs: 13.6 GB in the one home on this date.
* A rebuild after a parser change costs a refetch.
* A download only a query reads is released by building it, not by reading it.
