# ADR-0153: SINAN's notification block is declared once, for every agravo

**Date:** 2026-10-07. **Status:** accepted.

## Context

`curation/datasets/sinan_agravos.yml` already says that every agravo carries SINAN's notification block, and that
restating it per agravo is the duplication that lets one file drift. Its event types and column roles were declared
per agravo anyway, and for only some of them:
- the `notification` event type for 16 of 58;
- roles files for 15 of the 47 agravos the lake aggregates.

PegaSUS (pegasus_core O9, breadth) fitting every agravo failed on the others with "no event types declared" or "no
column roles declared". Nothing about their rows was unknown: a SINAN row is a notification, and its residence,
dates, sex, race and age are the shared form's.

## Decision

- **Event types.** A datasets file may declare `shared.event_types`. They hold for every dataset in the file that
  does not declare one of the same name (`semantics/event_types.load_event_types`). `sinan_agravos.yml` declares
  `notification` there. An agravo's `case` or `probable_case` stays its own, from its own form's classification codes.
- **Column roles.** `curation/roles/SINAN-_notification.yml` (key `SINAN-*`) holds the 19 columns of the block,
  copied from SINAN-LEPT's curated entries without their years. `column_roles.roles()` reads it for a SINAN agravo
  that has no roles file of its own; an agravo's own file always wins. An agravo's investigation fields are never
  inferred from another agravo's.

## Consequences

- All 58 agravos count as notifications, by residence, notification date, sex and age.
- No code's meaning is guessed: the block is one form, and nothing outside the block is declared for an
  agravo that lacks its own curation.
