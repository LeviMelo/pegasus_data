# 2026-10-04: national cause-of-death aggregation, and the first population sources (handoff §4, §7.1)

**Regime.** Branch `linkage`; linkage home for SIM; repo home for ANS and INEP; national SIM 2010–2023 from the mirror. Probe: `data/probes/aggregate/sim_2010_2023.py` and its `.json`/`.log` (three runs).

**§4 acceptance.** Recipe `sim_do_municipality_year_cause`: death events by municipality of residence × year × 18 age bands × sex × CAUSABAS, rolled up to ICD-10 category at query time.

| run | build | peak memory | base cells | category cells | roll-up |
|---|---|---|---|---|---|
| cells merged in a Python dict | 1,205 s (fetching included) | 15.1 GB | 16,002,385 | 10,974,296 | 22 s |
| merged in Arrow | 611 s (files cached) | 12.75 GB | same | same | 18 s |
| plus only the recipe's columns fetched | 655 s | 11.4 GB | same | same | 31 s |

- **Totals.** The cells hold 18,878,605 deaths, equal to the records read, and each of the 14 years equals TabNet (`obtuf`, deaths by residence).
- **Unmapped.** 68 deaths carry codes off the ICD-10 tree; they are reported, not folded in.
- **Where the memory goes.** What remains is decoding a whole national year before projecting it. Projecting at decode time is the next lever.
- **SINAN reads national files directly.** The Zika artifact build went from 436 s to 24.5 s. Its 59,215 cells are identical through all three changes.

**§7.1 sources (observed tier; the modelled products are ADR-0139's).**
- **ANS** `ans_beneficiaries` (December of 2021–2025). Medical-hospital plan links: 49,274,613; 50,530,569; 51,254,745; 51,956,946; 52,865,947. December 2022 equals ANS's own TabNet (`tabnet_02`, Assistência Médica) in all 28 state files. A link is not a person.
- **INEP** `inep_enrolments` (2021–2024). Enrolments: 46,668,401; 47,382,074; 47,304,632; 47,088,922. Each margin (sex, race, age band) sums to the total in all 5,570 municipalities. The age × sex × race crossing is not published openly since the 2021 release; a first build counted race "not declared" into sex as well, and the margin check caught it.
- **TSE** (2022 profile, 77 MB fetched). It carries voters by sex, age band and race, but under TSE's own municipality codes (Salvador is 38490). It needs a TSE–IBGE crosswalk before use.
- **CadÚnico and RAIS:** not started.
- **Downloads.** INEP reset a connection mid-transfer. The four file sources now download through one `sources.fetch_url` (browser agent, retries with backoff).
