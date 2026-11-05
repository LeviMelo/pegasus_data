# ADR-0212: Only a signature read from the file contradicts another representation

2026-11-05. Status: active. Amends ADR-0068 (the newest edition wins) and ADR-0071 (a representation is its full suffix).

## Context

`choose_representations` refuses a publication whose candidates carry different schema signatures. A candidate's
signature came from its family (`family_files`), and most files' families are inferred, never read. SIH-RD 2014 holds
each month twice as a DBC, byte-identical (`/SIHSUS/MHJ_14_16/RDAL1401.dbc` and `/SIHSUS/200801_/Dados/RDAL1401.dbc`,
963,086 bytes), beside DBF and XML exports. The census read only the `Dados` copy (113 fields, `e2f7244ae509a4c0`);
the `MHJ_14_16` copy sits by inference in the family of the 2013-2014 exports (`2dfed3d360ebaa80`). The two signatures
compared as a contradiction, and every SIH-RD 2014 month was refused (`RepresentationConflictError`) although the lake
held one clean representation (324 files, all from `200801_/Dados`).

## Decision

A schema contradiction is counted only between signatures the census measured (`file_schemas`, read without error). An
inferred family signature is not a claim about a file's layout, and two byte-identical mirrors cannot hold two
layouts. Row-count contradictions, exports behind natives and the newest-edition rule are unchanged.

## Evidence

`query("SIH-RD", period=2014)` returns 11,612,715 rows, the lake's count for 2014; the toxoplasmosis codes (B58, P37.1,
O98.6) as principal diagnosis give 1,987 admissions, the count read from the partitions directly before the fix.

## What would reverse it

Two measured signatures that differ for files of equal size (a real mirror with different layouts), which would make
size an insufficient mirror test.
