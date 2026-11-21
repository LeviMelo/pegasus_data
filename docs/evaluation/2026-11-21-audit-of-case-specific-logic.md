# Audit of the case-specific logic written on 2026-11-21 (same day)

**Why.** The author's rule: methods general, systematic and exhaustive; a hand-fixed choice is a debt to learn from the
data. Every change of the day was re-read for logic that names one dataset, recognises a case by its spelling, or
fixes a number by hand.

**Found and replaced.**
| where | what was case-specific | now |
|---|---|---|
| `_compendium._write_fields` | CNES field years by CNES file names and December | any records-cube field held when `plan()` needs no download for its period; the month declared (`fields.yml cnes.register_month`) |
| `_compendium._held_periods` | a fixed 1994-today range | each dataset's own years in the catalog |
| `view` label windows | a SIGTAP procedure recognised as "a 10-digit numeric code" | `codelists.yml code_windows` declares which codelists are dated code by code; any column bound to one is gated |
| `linkage.engine` params | fixed slots (`any`, `procedure`, `partner`), code grammar and partner rule keyed on the word "procedure" | `params.codes.roles` {match: role} and `partner` {match: role}, any names; one prefix grammar |
| `sources.ibge_cnefe.record_places` | a CEP ending in 000 treated as generic by spelling | the addresses' measured spread decides |
| `stay` chain | a 0-1 day window by hand | -1..1 from the measured gaps: after a 2x reason 78,500 at 0-1 days and 577 at 2-10; after a transfer 886 of 16,324 start the day before |

**Kept, with the reason.** The reading rule of a twice-published year (ADR-0228) names no dataset: it reads the file
census's widths for any dataset published nationally and per state (today SIM and SINASC). `drop_redundant_partitions`
decides by record containment or the server's listing, for any dataset. The 2 km radius of `record_places` and the
60-day window of `sih_admissions_to_radiotherapy` are declared parameters still set by hand: the window should be
learned from the distribution of pathology date minus admission among unambiguous pairs (OPEN_QUESTIONS).

**Checked.** Labels by year unchanged (0403070171 only from 2024; 0403070023 only 2009); the links load and bind
under the new parameters; `count_events("SIH-RD", "stay", period=("2019","2020"), geography="PE")` 970,343.
