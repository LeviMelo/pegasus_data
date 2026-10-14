## ADR-0140: IHME's GBD cause hierarchy is not shipped

**Date:** 2026-10-04. **Status:** active. **Request:** OQ-69 (2), decided by the PegaSUS architecture owner.

**Context.**
- pegasus_data is MIT-licensed open source.
- IHME publishes the GBD cause hierarchy and its ICD mapping, garbage codes included, under a user agreement that permits non-commercial use only.

**Decision.**
1. **Not in the package.** The GBD hierarchy and mapping are not shipped in the package, its resources or its seed. Bundling them would pass a non-commercial restriction to every user of an MIT package, invisibly.
2. **An opt-in fetch is allowed.** A user who asks for `GBD` downloads IHME's published files into their own data home, under IHME's terms. The structure is then served with its licence named (`licence: IHME non-commercial`) in `code_structures()`.
3. **What must stay true:**
   - nothing default and no test depends on it;
   - an absent GBD raises with instructions, never an empty table.
4. **Garbage codes:** an openly licensed list is shipped only after its licence is checked, for example the supplements of open-access papers such as Naghavi et al. 2010, *Population Health Metrics*. Done 2026-10-14 from two CC BY 4.0 supplements (França et al. 2020; Johnson et al. 2021): ADR-0182.

**Evidence.**
- PegaSUS does not need GBD: its blocks are ICD-10 chapters, and GBD would be one more overlapping list.
- The Ministry's own lists (CID-BR-10, avoidable causes, ICSAP) are already shipped.

**Not yet done.** The opt-in fetch itself.
