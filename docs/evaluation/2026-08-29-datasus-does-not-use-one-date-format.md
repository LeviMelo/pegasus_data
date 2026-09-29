## 2026-08-29 — DATASUS does not use one date format

*Split from docs/history/FINDINGS.md §3s on 2026-09-28; text unchanged.*

## 3s. DATASUS does not use one date format (2026-08-29)

Found by building the SECOND artifact. SIH had worked for weeks, and it worked
because its time axis happens to be a competence held in two columns.

### What came out

`build_aggregate("sim_do_municipality_month", years=[2022])` produced **62,040
cells from 75,707 rows** — nearly one cell per row, which is the opposite of
what an aggregate is for. Its periods were named `0101`, `0102` … `3112`.

Those are day-and-month, not months.

### Why

`_competencia_column` took the **first six characters** of a single packed time
field. That is correct for a competence — `AP_CMP` is `202201` — and wrong for a
record date, because DATASUS writes dates **day-first**:

| dataset | column | value | layout |
|---|---|---|---|
| SIH-RD | `DT_INTER` | `20211227` | `AAAAMMDD` |
| SIM-DO | `DTOBITO` | `07052022` | `DDMMAAAA` |
| SINASC-DN | `DTNASC` | `16041976` | `DDMMAAAA` |

**The format is not uniform across systems.** SIH is year-first; SIM and SINASC
are day-first. `07052022` sliced to six characters gives `070520`, whose first
four characters are `0705` — hence 366 "months".

### Why nothing caught it

Nineteen `(system, field)` pairs declare a `date` encoding and **none of them
had ever been built**. Both existing specs use a competence, so every test,
every measured figure and the whole SIH verification exercised the one path
where the assumption happens to hold. The defect was not hiding — it had never
been asked a question.

### The fix, and why it is a measurement

A table of nineteen declared formats is nineteen things to maintain and to get
wrong, and it grows with every new binding. The layout is **decidable from the
column**:

* year-first requires `text[0:4]` to be a plausible year and `text[4:6]` ≤ 12;
* day-first requires `text[4:8]` to be a plausible year and `text[2:4]` ≤ 12.

These are **disjoint for every real date after 1900**: if `text[4:8]` is a year
then `text[4:6]` is `19` or `20`, which is not a month, so year-first cannot
also hold. There is no ambiguous eight-digit date. A sample of a few thousand
values settles it exactly, and the confidence threshold is a guard against junk
rather than a tie-break.

`_date_layout()` scores both hypotheses and **returns None when neither
dominates**, which the build reports as a skipped year naming the fields — a
column it cannot read is refused rather than bucketed under a period that means
nothing.

### The rule this generalises to

**A format assumption that holds for the dataset in front of you is not a
format fact.** The tell was structural rather than statistical: 62,040 cells
from 75,707 rows is a compression ratio of 1.2, and an artifact whose whole
purpose is compression should have been challenged by that number alone.

Worth applying the same suspicion to: fixed-width numeric fields (SIH bills in
centavos in some eras and reais in others), and any column whose meaning is
inferred from position rather than declared.
