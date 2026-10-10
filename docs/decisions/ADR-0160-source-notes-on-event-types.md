# ADR-0160: a source's own definitions and caveats are declared on its event types

**Date:** 2026-10-10. **Status:** accepted.

**Context.** A source states how it defines an event, from when its data are valid, when a year is final and what it
knows to be wrong. The Ministry's Nota Técnica 133/2022 does so for SINAN's gestational and congenital toxoplasmosis
(valid from 2019; a year frozen three years after notification; ICD-10 codes entered wrongly; a generic form). None
of it was readable by a consumer, so a study could not state its limits with their source (PegaSUS ARCHITECTURE §2.4).

**Decision.**
- **The block.** An event type may declare `source_notes:` with a required `source` (the document) and any of
  `definition`, `form` (texts), `valid_from`, `valid_to` (years), `final_after_years` (a notification year's national
  database is frozen that many years later), `known_errors`, `limitations` (lists of the source's statements).
- **Validation.** Unknown keys raise, a block with no citation or nothing beside it raises, years are integers and
  ordered, texts are non-empty.
- **Reading.** `event_types(dataset)` returns it as `source_notes` (`None` where undeclared); it changes no count.
- **Declared for.** SINAN-TOXG and SINAN-TOXC (Nota Técnica 133/2022) and SINAN-ROTA (Nota Técnica 30/2024: sentinel
  surveillance, not compulsory notification; sentinel CNES codes vary; frozen after three years).

**Consequences.**
- The statement is the source's, cited; what a consumer does with a window (clipping a period, marking a preliminary
  year) is its own decision.
- The notes `sources/sinan_docs/` also holds (Creutzfeldt-Jakob 48/2025, Surtos de DTA 45/2024) are declared when a
  study reads those datasets.
