# ADR-0175: an explicit root carries its places

**Date:** 2026-10-14. **Status:** accepted.

**Context.** A review of the intake and CLI layer on 2026-10-14 (finding 17) found that `load_settings(root=X)` named the data home and
nothing else: `blobs`, `lake`, `work` and `catalog` still came from `PEGASUS_BLOBS_DIR`, `PEGASUS_LAKE_DIR`, `PEGASUS_WORK_DIR`,
`PEGASUS_CATALOG_DIR` or a `pegasus-data.toml` found by walking up from the working directory. With `PEGASUS_LAKE_DIR=C:/other/lake` and
`root='C:/caller/home'` the settings were `root=C:\caller\home`, `catalog=C:\caller\home\_catalog`, `lake=C:\other\lake`. The catalog of a
root lists its lake partitions relative to that root's lake and its fetches against that root's blobs, so every reader (`query(root=)`,
`serve --root`, `capabilities(root=)`, every CLI `--root`) opened the catalog of X over a lake that was not X's. `origins` recorded the
mismatch; no caller printed it.

**Decision.** Under an explicit root (`root=`, `--root`) the places that live under the home (`blobs`, `lake`, `work`, `catalog`:
`locate.UNDER_ROOT`) are the root's own unless the same call names them. The environment and the config files keep deciding them only
when the root itself came from the environment, a file or the default. The curated YAML (`curation`) is code, not data, and keeps its
layers. The layers an explicit root overrode are named in `origins` (`pegasus-data where`): `derived (from the explicit root; not used:
PEGASUS_LAKE_DIR=C:/other/lake)`. Decoders' temporary files still follow `PEGASUS_WORK_DIR` where it is set (`locate.use_scratch` yields to
the environment), as before.

**Consequences.** `Settings(root=X)` means everything under X; a caller that wants the lake elsewhere says so in the same call. A person
who set `PEGASUS_LAKE_DIR` for their usual home and passes `--root` for another one now gets the other home's lake, which is what the
flag said. No home is moved.
