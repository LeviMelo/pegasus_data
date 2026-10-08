# `translate` throughput: 22 s a call to 0.1 s

**Date and regime.** 2026-10-08; pegasus-core-fixes; the repo's own data home, whose `lake/reference` is materialised. Measured on SINAN columns of three codes each, with cProfile, while a proposal run was writing role files beside it.

**What was counted, and why.** The wall time of one `pegasus_data.translate()` call. `scripts/propose_missing.py` makes one call per column, so a SINAN form of 50 columns over three years cost 5–20 minutes; every labelled read pays the same checks.

**Where the time went** (7 calls, 155 s):
1. **The staleness fingerprint covered the whole curation**, roles and links included.
   - Editing any role made SINAN's reference tables "stale", and the next call rewrote them (about 70 s).
   - Two processes with different curation states (a run and an edit) rewrote each other's stamps on every call.
   - Now `dictionary_fingerprint` hashes only the curation codelists are built from (`curation.CODELIST_CURATION`: `codes/`, `variables/`, `codelists.yml`).
2. **"Is anything materialised?" walked every codelist, system and window directory**: `available_tables`, 283,000 `stat` calls, about 9 s a call. It is now `has_reference_tables`, one directory listing.
3. **"Is the dictionary empty?" counted its rows**: `COUNT(*)`, 2.7 s a call, in `translate` and in every labelled `fetch`. It is now `CatalogStore.has_rows` (`EXISTS`), also in `verify` and `explore`.

**Result.**
- A warm call takes 0.08–0.12 s (from about 22 s), with the same labels.
- A cold first call takes 2.4 s: 1.1 s for the fingerprint query, about 1 s of imports.
- A change to codelist curation still rewrites the stale system's tables, once.
