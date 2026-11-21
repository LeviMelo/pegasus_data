## ADR-0224: a kept artefact is written whole, and replaces its older versions only once it exists

**Date:** 2026-11-21. **Status:** active. **Request:** the architecture review of 2026-11-21.

**Context.** Derived files (cubes, role tables, concept caches, link runs, intake sidecars, reference stamps, SIDRA
parts, the source adapters' tables) were each written by their module's own temp-and-rename, about twenty copies.
A survey found them unequal: the cube cache used one temp name for every process and deleted the older versions
before writing the new one; `_stamps.json`, four intake sidecars, extract parts and several JSON files were written in
place, and a torn one raised when read; the reference stamp hashed row counts and label lengths, so a label edited to
the same length was not seen; the records cube's version left out the geography pack it places municipalities by.

**Decision.**
1. `persist/kept.py` is the one mechanism, over `staging.staged_file`: `write_atomic` (a temp unique to the process
   and the call, then a replace) with parquet, JSON and text forms; `kept(target, build, read=, write=, siblings=)`
   (read if present, else build, write, and only then remove the older siblings); `cap_by_recency`.
2. The caller names its file. No stored artefact was renamed: the role tables (20 GB) and link runs stay valid.
3. A stamp or sidecar that cannot be parsed reads as absent (stale, landed again), never as an error.
4. Two versions gained an input, so their artefacts are rebuilt once: the reference stamp hashes the dictionary
   rows' content; the records cube's stamp includes the checksum of the geography and municipality packs.
5. A cube's version is the source it can compute through: every module but those of the layers above it
   (`cubes.ABOVE_CUBES`: the commands, the routes, the compendium, the study builders), which `scripts/layers.py`
   proves nothing below imports (ADR-0225). An edit there rebuilds no cube; before, any edit rebuilt all of them.

**Evidence** (evaluation 2026-11-21-architecture-review). A records cube (SIH-RD hospitalisations, Acre 2023) equal
before and after, the second call a hit (0.09 s), one file left and no temp; a build or a write that fails leaves the
previous version and nothing else.

**Not changed.** Each store still decides what its version is made of (the catalog column of a lake partition, the
sidecar of a link run, a modelled product's version directory): those are different facts, not copies. No
cross-process lock was added; last writer wins, on whole files.
