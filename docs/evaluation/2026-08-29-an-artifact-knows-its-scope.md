## 2026-08-29 — An artifact knows its scope and was throwing it away

*Split from docs/history/FINDINGS.md §3r on 2026-09-28; text unchanged.*

## 3r. An artifact knows its scope and was throwing it away (2026-08-29)

**Found by a user looking at a map**, which is the part worth recording: every
test passed, every number was correct, and the screen said something false.

### What was seen

The frontend's ranking put **Rio Branco, AC** first for hospital admissions, and
the map coloured Acre while 5,452 municipalities sat pale grey. Acre has ~900,000
people; São Paulo has 46 million. The reaction — "I don't understand how Acre is
leading admissions" — was exactly right.

### What was true

Nothing was wrong with the data. `build_aggregate(..., uf="AC")` had been run, so
the artifact held 49,547 admissions from **Acre's SIH files only**: 2,417 cells
over 118 municipalities, 1,897 of them with UF prefix `12`. The other twenty
prefixes are residents of other states admitted in Acre's hospitals — the
geography binding is *residence*, so a patient from Manaus treated in Rio Branco
lands under `13`.

So the artifact was a correct answer to "admissions in Acre's hospitals in 2022,
by the patient's municipality of residence". The interface presented it as
Brazil.

### Why nothing caught it

`build_aggregate` **took `uf` and did not record it.** The manifest carried
`years`, `support`, `partial_periods`, `warnings` and a fingerprint — every
qualifier about time and about dimensions, and none about space. `aggregate()`
then served a total that was a subset total, with nothing to say so.

This is the SAME distinction the layer already makes twice elsewhere, missing on
the one axis nobody applied it to:

| axis | the distinction | where it was already made |
|---|---|---|
| dimensions | `absent` is "could not have known", not "zero" | the support mask |
| time | a record-date build cannot fill its own edges | `partial_periods` |
| **space** | **a municipality outside the fetch was never in view** | **nowhere** |

A partial classification already produced a warning when a roll-up left mass
unmapped. A partial *fetch* produced none, because from inside the cells it is
invisible: 118 municipalities with data and 5,452 without looks precisely like a
national build of something rare.

### The fix

`AggregateReport.uf` is recorded at build time, written to the manifest, and
carried back on read as a warning. `capabilities()` projects it as
`spatial.coverage` with three fields that mean different things:

- `declared_ufs` — what the build FETCHED. Authoritative when present.
- `observed_ufs` — the prefixes present in the cells. A measurement, and **not a
  substitute**: a national build of a rare condition also touches few states, so
  inferring scope from the cells would be a guess dressed as a fact. Artifacts
  built before this change report `kind: "unknown"` and say so.
- `municipalities` — how many the artifact actually holds.

The interface then restricts the map to what the build could have seen, names the
real scope in the state bar and in every ranking, and carries a banner saying a
municipality with no cell was *not observed*.

### The rule this generalises to

**Every qualifier a build applies to its input is part of what the output means,
and belongs in the manifest.** `uf` was the one that got away because it reads
like a performance knob — "fetch less" — rather than like a claim. It is a claim:
it decides what the totals are totals OF.

Worth re-checking on the same grounds: `years` is recorded (good), but a build
restricted by any future predicate must record that too, or the same failure
recurs in a new shape.
