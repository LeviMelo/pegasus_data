# ADR-0201: A care-flow edge carries the state of a role-named quantity, and the recipes say how it adds

2026-10-24. Status: active. Extends ADR-0144 (care flows) with the sum of a quantity beside the count.

## Context

`care_flows` counted events only. An analyst of hospital admissions needs, per edge, the days the residents of A spent
in the hospitals of B, to derive a mean stay later. The pieces existed apart: the roles layer says what a number IS
(`admission.length_of_stay`: a quantity, in days, with the codes that mean "not recorded"), `conditions.py` reads such
a column with its missing codes and domain, and `measures.py` holds the algebra (state, merge, the refusal of a stock
summed over time). Nothing connected them: the roles declare no aggregation, and the algebra was fed only by
`curation/aggregates/*.yml`, which name columns, not roles.

## Decision

1. **A quantity is named by its role** (`care_flows(..., measure="admission.length_of_stay")`, one or a list;
   `graph --measure`, repeatable). The column is whichever the roles declare for the year (`conditions.role_column`),
   never a name in code; a column name is refused with the role it stands for.
2. **The edge carries the state, never the mean**: `<role>_n` (events whose value was recorded) and `<role>_sum`
   (null when none was), the mean's `(n, sum)` (`measures.MEAN`); `Measure.formula` gives the mean. A role has a dot and
   a classifier column never does, so `careflow._group_columns` tells a measure's state from a `by` group by that alone.
3. **"Not recorded" has one reading**: `conditions.measurement` (the text is a number, not one of the role's `missing`
   codes, inside its `domain`) is now the function the condition tests and the sum both call. Events without a value
   are in neither column; their number, `outside_domain` and the top raw values, and the sum and count of the events no
   edge holds (`unplaced`, `unresolved`), are in the table's metadata (`measures`) and per year in `accounting`.
4. **The roles say what, the recipes say how it adds.** `measures.measure_of_role` builds the measure from the role and
   keeps the axes every recipe that declares the column allows (`_aggregate.declared_measures`: `additive_over`,
   `time_reducer`); with no recipe the number is a quantity of one event, in one cell of any grouping, additive on every
   axis. `care_flows` checks time, geography and dimensions with `check_rollup` before reading anything. A role that is
   no quantity or declares no `missing` is refused (as a condition is).
5. **A row that stands for several events is refused** (`weight` or `grid`): nothing declares whether a quantity on it
   is each event's or the row's total, so a sum would silently be one or the other.

## Consequence

Nothing the roles say changes. A stock a recipe declares (CNES beds and rooms, `time_reducer: mean`) is refused over
time with the recipe's own reason; CNES-ST has no flow, and its roles declare no `missing`, so the refusal shows there
only when a role is given one. 248 of the 364 quantities of the 87 flow datasets declare no `missing` and are refused
until a reviewer closes them (SIH-RD declares all of its own). A currency is summed nominal, as the aggregates
do (the unit's meaning travels in the metadata).

## What would reverse it

A role-level declaration of aggregation (then `declared_measures` is read second, as a check); a weighted event type
that declares whether its quantities are per event.
