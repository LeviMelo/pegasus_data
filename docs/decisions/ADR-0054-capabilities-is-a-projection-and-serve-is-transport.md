## ADR-0054: `capabilities()` is a derived projection, `serve/` is transport, and microdata is off by default

**Date:** 2026-08-29. **Status:** active.

**Context.** The sibling repository `pegasus_view` generates its whole interface
from one descriptor, on the rule that if the backend does not declare it, the
UI does not draw it. A control that is present and inert is worse than an
absent one, so an omission in the descriptor is a user-visible defect
(`docs/history/pegasus_data_ARCHITECTURE.md` §14.16). Built in `7e7d0b9`
(2026-08-29, "Give pegasus_data a frontend: a derived capability descriptor and
HTTP").

**Decision.**
- `capabilities.py` decides nothing. Every fact it reports is read from the
  module that owns it: grain from curation, bindings from `semantic_axes`,
  additivity from `measures.Kind`, roll-up targets from geography, support and
  partial periods from the built manifest. An authored descriptor would drift.
- A measure travels as **components and a formula** (`components: [los_n,
  los_sum]`, `formula: "los_sum / los_n"`), and `aggregate(finalize=False)`
  serves state, because finalising before the client finishes aggregating is
  how a mean of means happens. `Kind.formula()` is tested against `finalize`
  for every kind.
- The transport renames the geography column `geo` at every grain, widens
  municipality codes to 7 digits (IBGE's check digit, from a 91 KB shipped
  pack; 0 of 5,570 mesh polygons lack an identity row), and sends codes and
  labels separately.
- `/api/v1/records` returns 403 unless the server started with
  `--allow-records`. Identifiers still pass through unmodified (ADR-0032); the
  flag governs exposure on a network, not retention.
- Polygons are a static asset built from IBGE `/api/v3/malhas`. That API
  returns gzip without declaring it, so a client must sniff the magic bytes.

**Alternatives.** A hand-authored descriptor. Rejected: it drifts the moment a
spec changes.

**What would reverse it.** Nothing foreseen. A change to the contract is made
in both repositories or not at all (CLAUDE.md §4).
