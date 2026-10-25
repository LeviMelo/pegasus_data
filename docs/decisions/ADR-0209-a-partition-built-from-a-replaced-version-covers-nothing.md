# ADR-0209: A partition built from a version the server has replaced covers nothing, and a build records its files' layout

2026-10-25. Status: active. Amends the coverage test of the query planner (`coverage._source_identities`, ADR-0185) and
the build (ADR-0172).

## Context

nees-gt-ms read 17 fewer diabetes admissions of 2025 on 25/10 than TabNet and than its own read of 23/10. DATASUS
republished SIH-RD September to December 2025 on 2026-10-16, at the same paths (RDES2511: 2,007,865 bytes dated
2026-09-06, then 2,025,818). The lake partitions had been built on 2026-10-15 from the old files. The planner matches a
partition to its publications by path, so a partition built from a replaced version still counted as covering the
year, and the query read the old records. The 23/10 read, made in a stray home, had fetched the new files; ADR-0200
adopted them.

Rebuilding showed a second defect. `pegasus-data families`, run on 25/10 for CNES, re-placed every file. A file is
placed by its own header signature (`file_schemas`), else by its stratum's. The table held no SIH or SIA rows, so
SIH-RD January and February 2025 (113 fields) moved into the family of the 2025 stratum (September's layout), and
1,249 lake sources of SIA AR, ATD, PS, SAD and SIH RD fell in other families than their partitions. Those years then
read as uncovered, and a build refused their files.

## Decision

1. **A source the server now lists as another version than the one its partition was built from does not cover its
   publication** (`coverage._republished_since_build`). The version a build read is the latest fetch of the path made
   by the time the partition was written. They differ when the listed size does, or the time does other than through
   the server's two clocks (`listing.same_instant`). Such a year is read from the current files, and the next build
   rewrites the partition (its fingerprint holds the source digests). A source no fetch dates cannot be judged and is
   taken as built from the current version.
2. **A build records the layout of every file a verified partition holds**: its family's signature goes in
   `file_schemas` where no header census has one. A decode is a reading of the header, so `families` no longer falls
   back on the stratum for a file the lake has decoded.
3. The signatures missing on 25/10 were restored from the lake the same way (28,978 sources, none with two
   signatures), and families were rebuilt: no lake source now lies outside its partition's family.

## Evidence

Evaluation 2026-10-25-sih-2025-republished: 104 sources of 2,936 partitions republished since their build (SIH-RD
2025-09 to 2025-12, 26 states; RDAC rebuilt on 24/10 from the new files), sizes up 1,163 to 17,953 bytes; the check
costs 0.4 s over the whole lake; ES 2025 is read from the lake again after the rebuild, equal to the current files.

## Consequences

* DATASUS's current version is the one served: a republished month is read from the server until rebuilt.
* A rebuild after a republication fetches the files again, ADR-0208 having released them (1.1 GB for SIH-RD 2025).
* The snapshot versions (ADR-0122) remain how an older version is read on purpose (`as_of`).
