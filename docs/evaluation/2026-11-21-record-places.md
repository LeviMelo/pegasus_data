# How precisely a record's CEP places a person, and `record_places` (2026-11-21)

**Regime.** `master` after 6979092; home `pegasus_core_data`; CNEFE 2022 per-CEP table (`cep_points`); SIH-RD
admissions 2023-2024 with a neurosurgical procedure (0403...) or a TBI diagnosis (S06), the ABNc study's
`probes/p07_cep_precision.py`.

**Why it matters.** SIH (and SIA's APACs, SINASC) record the residence CEP. A CEP can name one street or a whole town,
so whether a CEP places a person at a point or only in a municipality decides what area context and distance a study
can attach to each record, and for whom.

**Measured.**
| admissions | CEP not in CNEFE | generic CEP (xxxxx-000) | CEP in one tract | in 2-5 | in more than 5 | addresses' p90 radius (p25, p50, p75, p90) |
|---|---|---|---|---|---|---|
| neurosurgical, 217,846 | 6.6% | 39.3% | 16.6% | 30.7% | 46.1% | 171 m, 571 m, 9.1 km, 18.0 km |
| TBI, 208,118 | 7.0% | 47.2% | 13.9% | 26.0% | 53.1% | 216 m, 1.9 km, 14.1 km, 28.0 km |

About half the records carry a CEP precise to a few hundred metres; the rest carry a town's CEP, and they are not a
random half: small and rural municipalities write the generic CEP. A tract-level exposure built from the CEP is
therefore missing not at random.

**What changed.** `record_places(ceps, municipalities)` gives every record its finest supported place: the CEP's
point when the CEP is specific (found in the CNEFE within the record's own municipality, not xxxxx-000, p90 radius
within 2 km), else the municipality's population centre, saying which (`source`). Alagoas 2024 neurosurgical
admissions: 224 by CEP (median radius 242 m), 822 by municipality. Studies take the municipality as the place every
record has, and the CEP's point or tracts as a refinement with a sensitivity analysis.
