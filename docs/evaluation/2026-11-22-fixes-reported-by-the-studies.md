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

**IGP-M deflator (t10 paper's sensitivity analysis).** `price_index` had no IGP-M. It now serves `index="IGP-M"` and
`"IGP-DI"` from the Banco Central's SGS (series 189 and 190, `sources/bcb_sgs.py`, stored with URL, SHA-256 and fetch time like
the SIDRA facts); the monthly percentage changes are chained into an index (first month = 100, stated in the metadata). The
API's bare URL answered `304` with an empty body, so the request always carries explicit dates. Check on the fresh home
(2026-11-23): the index reproduces IGP-M's accumulated December-to-December change, 2020 23.14% and 2021 17.79% (FGV's
published 23.14% and 17.78%; the last digit is the SGS's two-decimal monthly rounding); IGP-DI 23.07% and 17.74%. Annual factor
2012 to 2024: IGP-M 2.327 against IPCA 1.986.

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

**SINASC 2013 read twice (race papers).** `query('SINASC.DN', period=2013)` and `role_table` returned 5,808,054 rows for
2,904,027 births. DNBR2013.dbc was listed in two families: `SINASC_DN_f250f23917` (built 2026-11-21, a family that now
groups only the `NOV/` state files) and `SINASC_DN_49b98e3fbe` (built 2026-11-22 04:21, the family that now claims the
file), with the same digest and rows, and the one-reading rule (`national_or_states`) keeps every national partition of a
year. The only such case in the catalog. Writing a partition now removes from the catalog every other family's
partition of the same dataset, place and year built only from its files (`persist.lake._delist_superseded`); the 2013
row was removed by the same function (its row saved under `work/logs/`), and the unlisted file goes with the next prune. `query()` then read 2,904,027;
`role_table` still served 5,808,054 from its cache, whose key globbed the year's folders, unlisted file included. The key
now reads the catalog's listed files (`roles.partition_files`), as `query()` plans: SINASC 2013's key changed and the
table holds 2,904,027; the keys of other years (SINASC 2014, SIM-DO and SIH-RD 2022) are unchanged, so no other cached
table or stored link run went stale.

**Radiotherapy to death (science-2's request).** `sia_radiotherapy_to_sim` declared (SIA-AR first course per patient token
to SIM-DO within a year; keys sex, residence, day of death; match "principal" filters the certificate's underlying
cause by the same codes). Paraná 2019, C71: 217 patients, 47 pairs against 39 in the control: not viable. Measured by
hand on the same records, the age decides: 169 patients have a C71 death of their sex and residence within the year, 95
agree on age (0 to +1), 57 with one candidate, against 11 in a window moved back 180 days. The engine has no key of an
age against an age at death a year later. Link sides now expand a number role by offsets (`explode_values`, the age
at the course and one more), and the age became a key: Paraná 2017-2019, 750 patients, the pass found 154 pairs and a
control moved back 400 days (when every patient was alive) 67. Still not viable: no stronger key exists in the public
files (no birth date in the APAC, no postcode in SIM). Glioma survival goes through the operated patients
(`sih_admissions_to_radiotherapy` then `sih_admissions_to_sim`, both on birth date).

**A cohort link's partner as records (science-2, t05).** `linked_outcomes(..., link_name=, partner_roles=)` reads any
cohort link as `linked_deaths` reads the death links: columns named for the event (`event_date`, `days_to_event`,
`partner_record`) and the partner's own roles (`partner.<role>`); `linked_deaths` is its death-link form with the old
names. A bare `linked_deaths("SIH-RD", ...)` had been refused since SIH-RD gained a second and third cohort link; it now
picks the link whose event is a death. Paraná 2019, glioma surgery (C71) to radiotherapy: 891 persons, the pass 58 pairs
and the control 6 (10.3% chance, above the drop threshold): not viable for one state and year.

**A long `rows=` list (science-2).** `query("ANS.TISS_HOSP_CONS", rows={"ID_EVENTO_ATENCAO_SAUDE": <200,000 ids>})` killed the
process with a Windows stack overflow: `prefix_match` chained one `starts_with` per prefix, an OR nested 200,000 deep. It
now tests, per prefix length L, whether the first L characters are among the prefixes of that length (one `is_in` per
length): the same rows (20,050 random values against 300 prefixes: equal but for a null value, now false rather than null,
which every filter drops alike). The same query of 2024-01..06 returns 200,000 of 200,000 ids in 1.0 s.

**Deaths of stays admitted the year before (science-2, t08).** `sih_admissions_to_sim` read SIM from the cohort's year
on, but SIH files a stay by its processing month, so a year's publication holds stays admitted, and ended by death, in
the year before. Spine surgery (040803), SP 2019: 50 of the cohort's 58 in-hospital deaths linked, and all 8 misses were
dated 2018. The partner side now reads a year before as well (`pad_years: [1, 1]`, also for
`sih_admissions_to_radiotherapy`): 56 of 58 (97%). Every stored run of the two links recomputes. The 40% that science-2
measured came from its own join of all stays of the person, not from the cohort record.

## Defect sweep (A1-A8)

From `.claude/defect_sweep_2026-11-22.md`, each reproduced before and re-run after on the real home (AL 2019 unless noted).

| item | before | after |
|---|---|---|
| A1 `geography=["AL","BR"]` (SIM.DO 2019) | 1,370,088 rows (BR 1,349,801 + AL 20,287) | 1,349,801; BR in a list reduces it to BR with a warning (`_query_engine.model._geography`, so query, plan, count_events, cube inherit it) |
| A2 `linked_deaths(geography="XX")` | empty Followup | ValueError as `query` |
| A2 `load_population(uf="2700102")` | 0 rows | ValueError (not a state) |
| A2 `load_field("cnes_beds_total", years=2024)`, `years=1900` | 0 rows | ValueError listing the years held (2008-2023); `years="2019"` TypeError; `inep_enrolments` 2019 lists 2021-2024 instead of the cube message |
| A2 `rows=` value of a width the column never holds | 0 rows | unchanged (width-exact by design); no warning added: the planner does not read the column's values before filtering, so a warning would cost a scan |
| A3 `projpop`/`census_covariates` with `uf="AL"` | ValueError | 12,922 rows (projpop all years); uf via `_AXIS_COLUMNS` (`ufcod`; census `muncod` prefix) |
| A4 `years="2010"`; `uf="BR"` | characters iterated; KeyError | TypeError; BR = no state filter (902,340 rows, POPSVS 2010) |
| A5 `query("SIM.XX")` | geography error | `DatasetUnknown` |
| A6 `role_table("SIM.DO")` | KeyError | `dataset_roles` accepts the dotted name |
| A7 manual "years held" | CNES 2008-2025 (served 2008-2023); climate and SIES/SISAGUA `[]` | CNES held within the declared years; every other kind reports what `load_field` serves (`fields._held_years`): air_temperature 1961-2024 (64), sies_requested 2023-2026, thrombectomy 2023. The manual is regenerated by the next `pegasus-data manual` |
| A8 `lake_coverage("SIM.DO")` 2015 / SINASC.DN 2012 | 2.5M / 5,811,578 rows, 28 partitions | 1,264,175 / 2,905,789 rows (one reading); `also_on_disk` names the other copy |

**The manual build at 68 GB (science-1, 2026-11-22).** The A7 fix computed each field's years held by reading the field whole,
and the manual asks it of all 156 fields: the climate and intake cubes took the build to 68 GB of committed memory and the
machine into paging. `fields._held_years` now reads metadata only (a records cube's lake partitions in the catalog, a
climate or CNES field's declared years, a stored field's year folders; only SIDRA and series fact stores are read, being
small): all 156 fields in 118 s at 0.89 GB peak, with the same years (cnes_beds_total 2008-2023, air_temperature 1961-2024).

**Cohort links without the day explosion.** A cohort pass keyed its follow-up day on one row per person and day (366 a
person), and those joins were about half a link's time (SIH-RD I21, SE 2018, 11.8 of 22 s). The windowed passes now join on
the other keys and test the partner's date against the window's two ends (`engine._join_window`); the control turns the
partner's date back through the rotation's inverse (`placebo.rotation_inverse`), and the day-level ambiguity rule counts the
persons whose window holds that day. Eight state slices (sih_admissions_to_sim by diagnosis and by procedure,
sih_admissions_to_radiotherapy, sih_readmissions with its `differ` rule, sia_radiotherapy_to_sim with its age expansion)
give identical pairs, pass and control counts, horizons, control reach and verdicts. Back to back under the same load:
I21 SP 2019 46.5-49.9 s to 16.8-25.0 s (4,653 pairs), neurosurgery readmissions AL 2019 4.5-4.9 s to 2.6-4.0 s. Stored
runs stay valid (no change of pairs, no LINKAGE_VERSION bump).
The first version windowed only cohort follow-up and left the day explosion for windows a record carries (a delivery
admission's stay holding a birth's date): two mechanisms for one job. Every window is now its two ends, on either side
(`_join_window_right` for a partner's stay), and the engine no longer explodes days anywhere (the `<side>_days` view feeds
only the control's range and reach diagnostics). Ten slices, identical outputs: the eight above plus
sinasc_births_to_delivery_admission AL 2019 (30,620 pairs, 68.7 s to 39.0 s) and sinasc_births_to_ciha_delivery SE 2019
(633 pairs, 112.3 s to 19.2 s).

**field_fill counted sentinels as filled** (science-1). SIH-RD's CID_ASSO, CID_MORTE, DIAG_SECUN (every record '0000'
from 2015) and CBOR (every record '000000') declared no missing code, so `field_fill` gave share 1.0. Measured on SE
2010, 2015, 2024: those codes now declared per field (curation/roles/SIH-RD.yml), and the four read 0.0 from 2015 (2010:
3.9%, 3.2%, 16.1% real codes; CBOR 0.0). Recorded zeros stay values (VAL_ORTP, VAL_SADT 0.00 in every record; MARCA_UTI
'00' no ICU in 93-96%): `field_fill` now adds `modal` and `modal_share`, so a column one value fills shows as filled and
uninformative without a global zero rule. A column no year of the dataset carries now raises instead of reading 0.

**Lake views read what query() reads** (science-1's rule note). The study scripts' glob `SIHSUS/*/*/*/*/*.parquet`
reads every SIH series: neurosurgical index rows 2010-2025 were 1,458,819 RD and 232 RJ (rejected AIHs; 96 share an
N_AIH with RD). `open_lake()`'s views globbed each family directory the same way, a second reading beside
`plan_lake_read`. They now register the catalog-listed partitions with one reading per year (`one_reading`): `sihsus_rd`
returns the 1,458,819 RD rows in 8.9 s; registering every view takes 36 s. No SIH file on disk was unlisted.

**One stay chaining (coordinator, 2026-11-23).** The studies chained SIH-RD AIHs into stays with their own SQL
(`abnc2027_neuro/lib/episodes.py`) beside the declared `stay` event (abnc STATUS 82cec68 lists five differences). On the
lake 2010-2025 three of them are void: no AIH has a malformed or zero CEP, an unparseable NASC, a SEXO outside 1/3, or an
IDENT other than 1 and 5. The two real ones are fixed in pegasus_data: ties of one person's order were broken by reading
order (now by the declared `record`, N_AIH), and only a chain's first record was available, while a study needs every AIH
with its stay (length, ICU days, paid). `chain_sql(source, "SIH-RD", "stay")` (`pegasus_data.api`) is the one
computation: every record its event type counts, with `__person`, `__starts` and `__chain` (the first AIH's number);
`events_of` keeps `__starts = 1`. A person column that is blank, a declared not-recorded value of its roles entry, or
an unparseable date (the linkage role's format) makes the record its own person. Pernambuco 2019-2020, 1,075,155 rows:
episodes.py 970,346 stays, the stay event before 970,343 (reading-order ties), after 970,346, and all 1,065,304 IDENT-1
AIHs carry the same stay as episodes.py. The studies' episodes.py is now a wrapper over it (abnc b42ad8f); PE 2024 (669,715 AIHs) and
the whole t03 cohort rebuilt through it (52,360 stays, 51,884 persons, 84,905 AIHs) are identical to the old build.

**A held extract was invisible to query() (science-2, t08/t02 SIH-SP).** `query("SIH.SP", period="2019-06",
geography="SP", rows={"SP_PROCREA": ["040803"]}, max_download=0)` planned 57.1 MiB of downloads and refused, although the
extract `SIHSUS-SP/5b8634771b66` (filters SP_PROCREA 0403, 040803 and SP_ATOPROF 0702040126; 5,184 files, none failed)
holds every record that filter can keep; the study read the extract's directory by hand. A query whose row filter an
extract's filters cover (one covered column under "all", every column under "any") now reads each file the extract
holds from it, as a version is read from the lake (`extract.held_files`, `retrieve._extract_outcome`); the plan counts
those bytes as held (`RetrievalPlan.extract_bytes`, shown in `explain()`), the budget and `max_download=0` see them, and
such files are reported in `FetchReport.from_extract`, never landed. SP 2019-06: 8,389 rows, equal to the extract's
part, 3.6 s, nothing downloaded; all states 2019 with labels: 359,898 rows in 11.3 s, equal to the year's parts. The
`open_lake()` view `sihsus_sp` stays the dataset's partitions: an extract is a filtered table and is read only through
a filter it covers.

**Third round (2026-11-23).** *Stored link runs went stale for a file no read opens* (science-1, t07): the death-link run
of chronic subdural surgery, BR 2020, was on disk but `linked_outcomes(compute=False)` raised RunNotStored. A query of
SIM-DO AC 2020 had landed DOAC2020 beside DOBR2020; the national read opens only DOBR2020 (`query()` 1,556,824 rows
before and after), but `roles.partition_files` keyed role tables on every partition the catalog lists, so every stored
run reading SIM 2020 changed fingerprint. The key now lists the files a national read opens (`plan_lake_read`): SIM-DO
2019 and 2020 one file each (28 and 2 before). The new key changes every stored fingerprint once; `scripts/
restamp_link_runs.py` re-stamps a run only when the old definition, over the partitions written before the run, still
gives its stored fingerprint (roles, labels, files and engine unchanged): 87 re-stamped, 32 already current, 124 left
stale (their inputs did change). *`extract_table` stopped at the first covering extract*: a newer SIH-SP extract still
being written (0403, 2024) shadowed the complete one (0403/040803, 2010-2025); it now tries each and raises only when
none holds the years whole (2024: 2,119,682 rows). *`info SIHSUS-SP.IN_TP_VAL` did not resolve*: a dataset-qualified
field is now split on its last dot whenever the dataset resolves, in any spelling. Not a defect: SIH-RD's CBOR reads
0.0% filled while 225265 is its most common real value; nationally 2024 holds about 1,600 real CBOs among 14.2 M AIHs
('000000'), under 0.1%.

**SUS to private follow-up: `sih_admissions_to_ciha`** (the reviewer's request for t07/t03/t04; 2026-11-23). Declared in
`links.yml`: an SIH-RD admission with the caller's codes (SIGTAP procedure prefixes or ICD-10) to the same person's first
CIHA admission (modality 02) starting within a year of the discharge, to reach private reoperations after an SUS
operation. CIHA has no CEP, so the person is birth date, sex and municipality of residence (already comparable roles); the
control shifts the birth date by 7 days as `sih_readmissions` does. Held out: the CIHA hospital lies in the SUS hospital's
state, and CIHA's `IDADE_anos` (now a comparable role) agrees with the birth date within a year. Measured, 0403
(neurosurgery) 2019, partners to 2020: **Alagoas** cohort 763 persons, 51 pairs, 40 control pairs, chance 78.4%;
**São Paulo** cohort 19,979, 5,967 pairs, 5,926 control pairs, chance 99.3%. Verdict **not viable** in both: the pass is
not kept, so no pair is linked, none can be read, and no held-out check compares 30 pairs. The key is too weak: birth date
and sex within one municipality recur across a year of the other payer's admissions even in a state of 3 million, and the
control finds nearly as many pairs as the real data. No threshold was tuned. The link stays declared for a stronger key
(a patient token in CIHA, or a pass anchored on one named hospital); until then a private reoperation after an SUS
operation cannot be recovered from the lake.
*SIH-SP IN_TP_VAL described backwards* (science-1, t10): the variable text said "1 is SP, 2 is SH" from the Informe
Técnico SIH 2016-03; TabNet's TP_VAL.CNV (the label table pegasus_data already renders with) says 1 SH, 2 SP, 3/4
federal complement SH/SP, 5/6 local complement SH/SP, and the records agree (physician CBOs on even codes, ICU dailies
and OPME on odd). The text now follows the CNV and records the conflicting claim; labels in query output were right.
**Certification quality of the cause of death** (the reviewer of t06, t07 and t09 asked for a context). Three counts by
municipality of residence and year of death, 1996-2023, declared in `fields.yml` as the first `source: records` fields
(`fields.records_cube`: one cube of a landed dataset's events, with `where` as the cube takes it; no new aggregation):
`sim_deaths_residence`, `sim_deaths_ill_defined` (CAUSABAS R00-R99, RIPSA ficha C.5) and `sim_deaths_garbage_codes` (GBD
2019 garbage list, read from `garbage_codes('GBD2019')` by `{garbage_codes: GBD2019}`, not copied). A share is a count over
`sim_deaths_residence` (`over`), never stored. A municipality with deaths and none that meet `where` is a true 0 (the events'
own cube is the support). The cube's prefix filter now tests one membership per prefix length (6,018 GBD codes were a chain
of 6,018 `or`s). 2019, read against a direct DuckDB count of the lake view `sim_do` (DTOBITO in 2019, CODMUNRES): national
1,347,262 deaths, 74,593 ill-defined (5.54%, RIPSA's order), 523,744 garbage-coded (38.9%: the GBD list reaches well beyond
chapter XVIII, heart failure I50 among them); Bahia 12.2% ill-defined, Sao Paulo 4.7%, Federal District 2.1%; Salvador
(292740) 16,853 / 1,143 / 6,379 and Sao Paulo city (355030) 78,581 / 2,574 / 27,295, equal to the direct count. The only
differences from it are the 23 "municipality ignored" codes (xx0000), 2,539 deaths that belong to no municipality and
stay in the state and country cubes (BA 93,058 vs 93,365 direct, the same). Read in 11-15 s a year per field.

**Context fields for the ANS and PNS studies (2026-11-23).** The ANS fields already exist as intake fields; nothing was added
beside them. `ans_beneficiaries_quarterly` (medical-hospital links, sex x age band x contract x segmentation, quarter stock) gives
47,038,196 links in December 2019 (ANS: about 47 million); its age band is CD_FAIXA_E as filed (two codes per five-year band from
15-19 to 55-59, 80+ is 26+27). `ans_beneficiaries` is December 2021-2025 only and keeps dental links as a `coverage` stratum
(2022: 50,458,049 medical-hospital, 30,002,606 dental; the 2022 TabNet figure is 50,530,569). `ans_tiss_hospital_events` (and
`_by_cid`; the DET field is `ans_tiss_hospital_items`) had sex but no age band: `age_band` is added (FAIXA_ETARIA as filed,
spelled '30 a 39' to 2022 and '30 a 39 anos' from 2023). Events placed by residence: 6,134,552 in 2019 and 7,899,364 in 2023
against a direct count of the lake (residence present, not xx0000) of 6,134,556 and 7,899,364.
**PNS not declared.** `load_field` reads a SIDRA field at municipality only (`_field_from_cube` calls `cube` at its default place and
keeps the first six characters of the place as `municipality`); only intake sources with `place.states` come out at state level
(keyed by their own state column), and no field carries an uncertainty column. The cube layer can serve `sidra:<t>/<v>` at
`place="uf"` once N3 facts are fetched (`pegasus-data sidra fetch <t> -v <v> --level N3`). IBGE publishes the count (mil pessoas)
with its 95% interval limits and coefficient of variation (table 4638, variables 4615 count, 4616/4617 limits, 4618 percent, 4934
CV; MG 2019: 3,646.543 [3,347.879; 3,945.207] thousand, 22.0%, CV 4.2%). No registry table was found for AVC; hypertension
(4416-4419), helmet (5267-5278), alcohol (7726-7731), violence (5351-5422, 2013) and seat belt (5133-5138, 8082-8093) exist.

**Every ICD-seeded PegaSUS scope failed in pricing** (science-1 t01/t04/t07, science-2 t05/t06): "ANS-TISS_HOSP_CONS.CID_2:
pegasus_data describes no such field". The scope reaches TISS's secondary diagnoses by role, and `describe` raised
MissingColumnError for every column of the dataset: the intake registered its families without their columns (no
`schemas` row, no `schema_presence`), so neither `describe` nor the read planner's census knew any column of the 35 intake
families on the home (ANS TISS and ICB, SISAGUA, SNGPC, PNI-DOSES, S2iD, INEP, SIES, FA, SRAG, the census 2010 sample,
SIOPS). `intake._register` now records them as a header census does, and the 35 were backfilled from each family's own
parts (35 of 35); `describe('ANS', 'TISS_HOSP_CONS', field='CID_2')` and PegaSUS's `token_rule` answer.
**PNS declared at state level (2026-11-23, working branch, N3 facts fetched into the one home).** A field takes `level: N3`
(`load_field` then reads `cube(place="uf")` and returns `uf`, `uf_abbr` and no municipality, never a state value copied onto its
municipalities) and `interval: {lower, upper, cv}` (the table's own variables, columns `lower`, `upper`, `cv` beside `value`, a
marker staying null). Six fields: `pns_chronic_spine_problem` (4638), `pns_hypertension` (4418), `pns_helmet_motorcycle_driver`
(5267), `pns_seat_belt_front` (8082, 2019), `pns_alcohol_abusive_use` (7726, 2019) and `pns_violence_by_stranger` (5351, 2013); each
27 states and every year it publishes, status `value`. Against the SIDRA API: MG 2019 spine 3,646.543 [3,347.879; 3,945.207], CV 4.2;
SP 2019 hypertension 8,678.935 (API 8,678.935); MG 2013 helmet 3,243.784 [2,859.408; 3,628.159], CV 6.0 (API identical). A municipal
field is unchanged (`gdp` 2021 and `households_sewer_network` 2022: 5,570 rows, same hash on master and the branch). Denominator: IBGE
publishes no count of any universe; count over its own percentage gives 159.0 million adults in 2019 (145.4 to 146.3 million in 2013),
34.8 and 36.7 million motorcycle drivers (2013, 2019) and 154.6 million car users (2019), stated in each field's `what` and `over` left out.
`context_candidates` gains `grain`: the 156 municipal SIDRA groups (4,448 tables) are unchanged (same content apart from the `fields`
that read them), 125 state-only groups (869 tables, N3 and not N6) are added with grain `state`; of the 28 intake entries one (`sies`,
placed by state) is now grain `state`, 27 `municipality` (184 entries before, 309 after). A PNS group with any N6 table (the capitals)
stays a municipal group.

**PNS percentages beside the counts** (science-2, t06 and t08). The studies compare IBGE's published shares (chronic
spine problem among adults; helmet use among motorcycle drivers), which cannot be rebuilt from the count fields: the
survey's weighted universe is published as no count (for the helmet, the drivers). Six `_percent` fields store IBGE's
design-based estimate as published, at state grain, with its own limits and CV (`unit: percent`, never summed; a coarser
share is IBGE's own level): pns_chronic_spine_problem_percent (4638/4618), pns_hypertension_percent (4418/4399),
pns_helmet_motorcycle_driver_percent (5267/5716), pns_seat_belt_front_percent (8082/11692),
pns_alcohol_abusive_use_percent (7726/4301), pns_violence_by_stranger_percent (5351/5828). This is not a mean pegasus_data
computes (CLAUDE.md's rule is about those) but a source's official estimate, which is never recomputed. Minas Gerais
2019: spine 22.0% [20.2; 23.8] CV 4.2 (as SIDRA), helmet 95.1% [92.9; 96.7], seat belt 82.3%, hypertension 27.7%,
alcohol 17.2%; 2013 spine 17.7% [15.4; 20.3]; violence 2013 2.5% [1.8; 3.4] CV 16.9. 27 states in every field-year.

**Oncology supply for t05 (science-2).** Accreditation groups oncology_cacon (HB 1701-1703, 1712, 1713), oncology_unacon
(1706-1711) and radiotherapy (the codes whose label names radiotherapy: 1704, 1707, 1715), and the professional group
radiotherapists (CBO 225330, 223154 before 2011; the study's "225151" is the anaesthetist). Fields
cnes_accreditation_oncology_cacon/_unacon/_radiotherapy (2014-2024) and cnes_radiotherapists_professionals/_hours_sus
(2008-2023). Brazil December 2019: 46 CACON, 263 UNACON, 141 radiotherapy establishments (equal to a direct distinct count
of the lake's HB), 1,207 radiation oncologists (SBRT's own count is of the order of 1,100). Linear accelerators and cobalt
units are not CNES-EQ codes: they are counts on CNES-DC (S_ACELL6, S_ALSEME, S_ALCOME, UN_COBAL; layout IT_CNES_1706),
whose December files the lake holds only for 2026.
The radiotherapy machines are a CNES family over CNES-DC (`radiotherapy_machines`), December 2008-2023, Brazil:
linear accelerators 241 (2008), 354 (2014), 421 (2019), 504 (2023); cobalt units 106, 89, 57, 43 (phased out);
brachytherapy 336, 315, then 242 from 2015 and flat (a break of registration, undocumented; stated in the field's gaps).
**Grain is measured (2026-11-23).** SIDRA's level N6 also means "some municipalities" (PNS and PeNSE publish the 27 capitals), so
`context_candidates` now counts each N6 table's localities (`/localidades/N6`, 4,448 tables fetched through the SIDRA client,
kept in `locality_count` with `n_capitals`) and compares them with the municipalities IBGE's territorial division (DTB) lists for
the table's last year: `geography.yml` `municipalities_by_year`, from `scripts/ibge_dtb_vintages.py` (4,974 in 1994, 5,507 in 2000,
5,564 in 2005-08, 5,565 in 2009-12, 5,570 in 2013-23, 5,571 in 2024-25; a year IBGE does not publish takes the latest before it).
A table is `municipal` when it lists them all, `capitals` when its localities are exactly the 27 of `members('capital')`, else
`partial (n of N)`, naming the missing codes when fewer are missing than listed; a group takes its best table's grain. No
fraction or threshold. Before and after on the real home: the 309 entries and 4,448 tables are identical apart from the grain
(`grain`, `n_localities`, `n_capitals`, `municipalities_in_year`, `missing` are new); the 156 municipal SIDRA groups are 58
`capitals`, 50 `municipal`, 48 `partial`; the 27 municipal intake sources are `municipal`; the 125 state groups are unchanged. By
table: 1,231 municipal, 1,559 capitals, 1,609 partial, 49 ending before 1994 (counted, no DTB total to compare). Every PNS and
PeNSE group with N6 tables reads `capitals` (4 PNS groups are state-only). 168 tables end in 2024-25: 4 municipal, 103 capitals, 61
partial; 34 of them read `partial (5570 of 5571)`, 32 missing 510183 (Boa Esperança do Norte, MT: in the DTB, not in SIDRA's N6
lists) and 2 missing 354880: measured, not relabelled. Checks against the IBGE API: table 9418 lists 5,570 N6 localities, table
5133 (PNS) 27, the capitals from Porto Velho.

**Declared fields as context candidates** (the reviewer, auditing t05). `context_candidates` listed SIDRA groups and intake
sources only, so the declared fields of other sources were never offered to a study: no paper had decided MRI or CT
scanners, neurosurgeons or neurology accreditations. Each source and family of declared fields that no SIDRA group or
intake source lists is now one candidate (`kind: field`, id `field:<source>:<family>`): 18 families, 104 fields (CNES
equipment 13, professionals 31, beds 10, facilities 8, accreditations 7, radiotherapy machines 3, teams 2, specialised
services 1; SIM-DO records 3; climate 8; four ANS TISS intake fields); 309 entries to 327.

**SIA-AR treatment dates described** (t05's final review). The study read AP_DTINIC (the APAC's validity start, as its
roles note says) as the start of radiotherapy; it equals the request date in 76% of courses. The radiotherapy part of
the APAC carries the dates of care: APA_INIAR1-3 and APA_FIMAR1-3, the start and end of irradiation of each treated area
beside its topographic ICD (sources/apac_layout.txt, p. 10). Their roles carried only the layout's bare names; each now
has a note saying what it records. **Corrected the same day** (the reviewer, t05): the first note called them the
start and end of irradiation; the SIA oncology manual (2008, 6.2.3.1) defines them as the *planned* dates informed on
the APAC/RT request, kept to check the billing. The notes now say planned, not delivered.
