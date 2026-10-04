# Open questions pass: curation, join grain, linkage evidence, rebuild speed

**Date:** 2026-10-04.
**Regime:** branch `linkage` after df6366b. Maintainer catalog, plus a fresh home at `~/pegasus_live/home`. The FTP data channel is down, so files came from the mirror.

**Curation against documents (OQ-3, OQ-8, OQ-64).** Agents searched `sources/` (PDFs converted to text, TabWin kits) and the web. Every edit cites its source.

| measure | before | after |
|---|---|---|
| coded columns with no table | 175 | 86 |
| columns without an official name | 185 | 159 |

- **What was added:**
  - SISCAN: 60 code lists, from kit `.def`/`.CNV` files and Notas Técnicas;
  - SIA APAC: 12 code lists and 22 names (the PQ/PR/AC legacy fields matched to the APAC_JUL07 layout);
  - SINAN: 9 code lists; SINASC: 2; Dados Abertos: 4;
  - RESP `ETIOLOGIA`, which `DIC_DADOS_RESP.pdf` documents (an earlier note said no dictionary did).
- **Withheld:** codes borrowed from another form's field of the same name (`HEPATO`, `CLI_OUTRO`, `AMP_ACEVAS`). HEPATO and CLI_OUTRO now come from the congenital-syphilis dictionary as SIFC supplements (`curation/codes/supplements.yml`, merged by `scripts/harvest_codes.py`).
- **Widths:** the SISCAN national CSV and the kit's own 2013 DBFs both write "01"/"02" where the CNV lists 1/2. The CNV is the narrower representation.
- **Inferred descriptions (OQ-64):** 501 audited by exact field name. 10 confirmed. 1 contradicted: SIM `NUMERODO` is "sequencial por UF informante e por ano", not a pre-printed serial. The rest have no document.

**Other codes.**
- **AIDA `CRITERIO`.** 601 and 902 are defined in an SES-RJ TabNet technical note ("600, 601 - ÓBITO", "901, 902 - HIV+"), and 120–500 in the same note and `CRITAIDS.CNV`. AIDA 2023 now leaves only 101 undecoded (16,433 rows).
- **VIOL `CS_ESCOL_N`.** The `'43'` was a text-extraction artefact for `0 – Analfabeto`.

**Join grain (OQ-20).** `scripts/linkage_study.py joins`; artifacts `data/probes/linkage/joins_joins-SP_2010-01.json` and `…1996-01.json`.

| member | period | rows | keys | repeated | rows per key |
|---|---|---|---|---|---|
| SIA-AN | SP 2010-01 | 18,908 | 18,849 | 55 | many |
| SIA-AB | SP 2010-01 | 968 | 653 | 315 | many |
| SIA-AR | SP 2010-01 | 4,267 | 4,121 | 121 | many (was declared one) |
| SIH-MT | national 1996-01 | 4,317,149 | 1,040,594 | 801,542 (max 82) | many (was declared one) |

**Delivery type as linkage evidence (OQ-63).** SINASC `PARTO` against the delivery AIH's SIGTAP procedure, deliveries link, SE 2022:

| | pairs | threshold | upper FDR |
|---|---|---|---|
| baseline | 20,658 | 15.74 bits | 0.02% |
| with delivery type | 20,705 | 14.37 bits | 1.1% |

Agreement is +0.94 bits and a conflict −5.9 bits. It cannot lift a typo pair, which needs about +9 bits, and it worsens the bound, so it is not adopted.

**Rebuild speed (OQ-24).** `semantics --system SINASC` under cProfile (`data/probes/sem_sinasc*.prof`): 282 s, of which `persist_entries` took 172 s and a LIKE count over the 12.7M-row `code_tables` took 27 s.
- The count is now a key range: 0.05 s.
- An unchanged kit (same blob, same parser fingerprint) is no longer re-read: a repeat run takes 2 s instead of 179 s, with the same 1,128,320 SINASC rows.

**APAC identifiers (OQ-19).** The 2002 pattern holds on 16 `.exe` files sampled at random from 2001–2006 and 12 states, with no reversal attempted:
- patient CPFs pass the check digit on 0 of 528,517 values;
- professional and director CPFs on 332,995 of 333,358;
- `EXA_NUM` ⊂ `PAC_NUM` in all 15 files carrying both tables.

**APAC DuckDB exports (OQ-54).** `pegasus-data schemas --system DADOS_ABERTOS --whole-up-to-gb 8` fetched the eight exports whole from the mirror into the blob store and recorded their tables. All eight are now in families.
- **Mis-parse fixed.** `apac_am.duck.zip` had been parsed as series APAC, state AM. A national medication export was therefore a would-be Amazonas file, and a phantom "APAC layouts" dataset declared in the ontology. A descriptive tail is now read as a state only when no sibling's tail is a type.
- **A scoped inventory damaged the catalog, now fixed.** `inventory --system DADOS_ABERTOS` rewrote SINAN's strata from the Dados_Abertos exports alone, and the family count fell from 98 to 58 SINAN families. It was restored from the seed copy and is guarded: a scoped run now writes only strata of its own systems.

**Every declared dataset, fresh home (OQ-23).** `scripts/live.py sweep`, artifact `data/probes/live/20261004-003436/sweep.json`:
- 134 datasets: 116 returned rows.
- 1 failure: SINAN-CHAG 2025, a file neither the FTP nor the mirror serves.
- 17 skipped: 10 reference sets with no dated file, 7 over the 25 MB cap.
- Its "labelled" count reads 0 because the default presentation now merges codes and labels into one column; this is a metric artefact, not a defect.

**Newborn admissions: congenital anomalies as evidence (OQ-62).** `sih_neonatal_admissions_to_sinasc`, SE 2022, probabilistic. Delivery links re-stored for SE 2021 and 2022: 21,217 and 20,656 pairs.

| | pairs | threshold | upper FDR |
|---|---|---|---|
| baseline | 717 | 9.46 bits | 2.01% |
| with CODANOMAL against the admission's diagnoses, by ICD-10 category | 711 | 9.47 bits | 2.03% |

A shared category is worth +3.1 bits; an anomaly on the admission but none at birth −2.75. The shared category occurs in only 0.29% of true pairs, so the evidence is rarely available. Not adopted.

**Catalog storage (OQ-24).** `data/probes/compact.log`, measured with `dbstat` before:
- `code_tables` was 6.9 GiB, mostly an `extra_json` nothing reads;
- `dictionary_conflicts` held 4.0M rows for 662k distinct claims, re-recorded on every rebuild.

Both were fixed at the source and cleaned once (3,342,637 rows deleted), then the catalog was vacuumed: 18.9 → 12.0 GiB in 469 s.

**Maternal age as delivery evidence (OQ-63).** SINASC `IDADEMAE` equals the age from `DTNASCMAE` on 28,520 of 28,521 SE 2022 births, so it carries no independent evidence.

**Where delivery recall is lost (OQ-63).** SE 2022, exact key = mother's birth date + hospital + birth day inside the stay:

| | births |
|---|---|
| all births | 28,524 |
| linked on the exact key | 20,559 |
| unlinked, no unlinked obstetric admission at that hospital that day | 5,377 |
| unlinked, a single remaining candidate, mother's birth date one digit off | 24 (23 agree on residence) |

The typo ceiling is about 0.1% of births; the gap is births with no SUS admission.
