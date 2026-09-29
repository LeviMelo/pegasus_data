## 2026-08-30 — The CNES stock that measured the wrong columns

*Split from docs/history/FINDINGS.md §3y on 2026-09-28; text unchanged.*

## 3y. The stock that was never a stock of the right thing (2026-08-30)

The CNES artifact existed to prove the aggregate layer handles stocks, and it
did -- while measuring the wrong stocks. `consulting_rooms` read QTINST07 and
`beds_total` QTINST08, but the dictionary rows for the installations grid say
those positions are the male and unsegregated REST ROOMS of the emergency
block. Sao Paulo painted 1.934 "beds" against its real ~80 thousand. The
frontend surfaced it: once the client learnt to reduce stocks honestly (mean
per period instead of bed-months), the headline number was finally readable
enough to be visibly absurd.

Two changes. `field:` on a `sum` measure now accepts a list, summed row-wise
at lift in both the row and columnar paths (a row where no column parses
stays null); only `sum` composes this way, anything else is refused. And the
spec now reads what the dictionary says: Leitos = QTLEITP1+P2+P3 (the legacy
existing-beds rollup, surgical + clinical + complementary; SP mean 78.594 in
2022, jan 81.775 -> dez 76.972) and Consultorios = QTINST14-18 (the five
physician/non-physician consulting-room positions; SP mean ~155 mil).

The lesson is the label ladder's, replayed on measures: a measure whose field
was picked by number rather than by its dictionary row is not curated, it is
guessed -- and a guess inside a correctly-functioning algebra is worse than a
refusal, because everything around it keeps working.
