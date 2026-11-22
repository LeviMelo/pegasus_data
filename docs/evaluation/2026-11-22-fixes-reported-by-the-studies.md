# Defects the ABNc studies reported, fixed at the source (2026-11-22)

**Regime.** Real home, master 58ffa85a to 302d95c3. Each defect was reported by a science session working on the ABNc
2027 studies (`../abnc2027_neuro`) and reproduced before it was fixed.

| Report | Cause | Fix and check |
|---|---|---|
| Code search empty for 0304010294, 0304010367, 0304010537 | `_code_hits` matched label text only, and current labels only | matches the code itself, keeps ended codes with their window, searches SIGTAP's own history (`code_windows`): 0304010294 [200801-201906], 0304010367 [201905-current] (58ffa85a) |
| `municipality_point('530140')`: no point | the Federal District's administrative-region codes are in `MUNIC_MOV` as in `MUNIC_RES`: 111,115-125,592 rows a year 2010-2017, none from 2018 (DF files) | `MUNIC_MOV_municipio` maps them to 530010 for 2008-01..2017-12: SIH-RD DF 2015-03, 530180 and 530040 now 530010; the warning names the column (29f4f1c0) |
| No orthopaedist supply field | not declared | `cnes_orthopaedists_*` (CBO 225270; 223146 before 2011): 36,872 persons in 2022, against 6,676 neurosurgeons, both municipality-distinct (4ef8073f) |
| `care_flow_communities` input undocumented | an extra undotted column in a hand-built table becomes a group silently | the function states its input and output (4ef8073f) |
| APAC token `AP_CNSPCN`: a blank shared as fifteen braces | declared nowhere; linkage roles ignored their columns' `missing:` lists | declared not recorded in 20 roles files; linkage roles null declared not-recorded values: SIA-AR SP 2025-06 role table 139 placeholders → 0 (nulls 293 → 432); ROLE_TABLE_VERSION 3 (604d25b0) |
| `sidra inspect` in the manual; cube refuses an unheld level silently | the command is `sidra show`; the refusal named no remedy | manual header and the refusal name `sidra show`/`sidra fetch` (302d95c3) |
| TISS `info` "none held" | read before the background map rebuild caught up | no defect; the page shows 462.6 M rows once the map is current |

The 2025 counts of the token placeholder (lake, SIASUS 2025 partitions): AQ 218,633 of 4,966,559 authorisations
(681,918 true nulls), AR 7,944 of 176,753 (32,292 nulls).

**TISS hospital events as an event source** (the thrombectomy study counts private-plan admissions). `ANS.TISS_HOSP_CONS`
now declares a `hospitalisation` event (one row per admission, key `ID_EVENTO_ATENCAO_SAUDE`, classifier CID_1) and roles
(`roles/ANS-TISS_HOSP_CONS.yml`): residence and provider places, `admission.month`, sex, age band, stay, ICU days, values.
On 2024-03 (all states): 702,048 rows, 702,048 distinct event ids, `count_events` 702,048 (CID_1 empty on 258,734, 37%);
`cube('records:ANS-TISS_HOSP_CONS/hospitalisation', at='provider')` places I63 in 76 municipalities. Making it found a
defect in `semantics_for`: a series with underscores was matched on its last word (`CONS`), so 15 datasets (ANS TISS, 10
SISCAN, SIH.BASE_AIH1, two DADOS_ABERTOS) fell through to role-derived axes and ignored their curated ones. The series
is now matched as the whole end of the key; the default place and time columns of all 15 are unchanged, and no other
dataset of the 180 resolves differently (SIA.PA still to core.yml's SIASUS_PA).

**Second round (science-1, after the crash).** Ages above 80: no defect in the data. `projpop` holds single years to 90+
by state, sex and year 2000-2070, and `CENSO` single years to 100+ by municipality for 2022, but no page of the manual
said which series carries which ages, so the study looked only at POPSVS (80+). The manual now has `populations.md`, read
from the files: series, place, years, axes, age range. `read_modelled` returns `(table, manifest)`; the products' calls now
show it. INPC: `price_index(index="INPC")` (SIDRA 1736, variable 2289, December 1993 = 100) beside IPCA; 2012 to 2024 annual
factor 1.982 against IPCA's 1.986.

**The newborn link's 11-17% (science-1).** No defect in the keys: in AL 2022, 85% of 6,913 newborn admissions have a
birth agreeing on birth date, sex, hospital and residence, 40% exactly one, and the 7-day control finds 826 unique pairs
against the first pass's 2,600 (deterministic: not viable). The linked share is what the data identify; the link's
description now says so. `info <link>` marked no stored run as stale while `link()` would recompute it: every run of the
newborn, death and infant-death links was stale after the day's spec and role-table changes. Each run now shows
`[stale: link() recomputes it]` and the header counts them.

**Sex across population series (science-1).** POPSVS, POP and CENSO filed sex as "1"/"2", projpop and the census
covariates as "M"/"F", so two series stacked never met. `load_population` now returns "1"/"2" for every series, read from
the whole spelling (`canonical_sex`), with the filed value as `sex_filed` where it was rewritten. projpop 2024 by sex now
equals POPSVS's (103,662,286 and 108,921,464). The one internal reader of projpop's M/F (the population account's IBGE
calibration, `population_tensor`) reads the new coding.
