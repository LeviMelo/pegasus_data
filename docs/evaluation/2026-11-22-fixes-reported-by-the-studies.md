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
