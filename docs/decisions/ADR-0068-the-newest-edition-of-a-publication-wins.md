## ADR-0068: The newest edition of a publication wins; only undated editions refuse

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0047 (one selector
chooses a representation per publication; a conflict refuses).

**Context.** With the seed catalog, planning `query("SIH-RD")` refused with
`RepresentationConflictError: logical publication 'SIHSUS|RD|AC|1605' has
conflicting representations`.
- SIH-RD 2014–2016 is on the server twice. One copy is
  `/SIHSUS/MHJ_14_16/` (972 files, all dated 2017-10). The other is in
  `/SIHSUS/200801_/Dados/`, with different sizes, dated 2018: `RDAC1605.dbc`
  is 300,032 bytes against 300,573.
- ADR-0047 refused any publication claimed by two objects of one format
  unless their sizes matched (the mirror case). That made SIH unreadable for
  three years, for every user, on a first request.

**Decision.**
- Two editions of one publication in the same format, with different sizes,
  are a **revision**. The one the server dates latest (`files.modified`)
  is kept and the others are reported as deduplicated
  (`FetchReport.representations_deduplicated`).
- Among the surviving formats, selection is unchanged: the cheapest to
  decode.
- Editions the server does not date, or dates identically, still refuse:
  there is no evidence to choose by.
- `representations.choose_representations` looks the dates up itself, so its
  four callers need no change.

**Measured after:** `query("SIH-RD", period="2016-05", geography="AC")` gives
4,081 rows and 35 labelled columns in 9.0 s, read from `200801_/Dados/`, with
`MHJ_14_16/RDAC1605.dbc` reported as superseded.

**What would reverse it.** Evidence that an older-dated edition is the
authoritative one: for example, `MHJ_14_16` turning out to be a distinct
dataset rather than an earlier edition (OQ-55).
