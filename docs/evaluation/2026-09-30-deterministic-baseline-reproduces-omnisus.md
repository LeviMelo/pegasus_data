# The deterministic baseline reproduces omnisus's RR 2022 linkage to the pair

**Date:** 2026-09-30. **Regime:** branch `linkage` (after ADR-0110), fresh home
`~/pegasus_fresh`, live FTP. Plan phase A3.

**What was run.** `pegasus_data.linkage.engine.link(name, period="2022",
geography="RR")` for the three specs in `curation/links.yml` that mirror
omnisus's study (`evidence/2026-09-23-colunas-e-linkage.md`,
`…-linkage-ampliado.md`): the same passes, the same control (birth date + 7
days over the same remaining records), the same drop rule and verdicts.
Artifact: `data/probes/linkage/a3_rr2022.json`.

**Why this is the thing to count.** Two projects with independent decoders,
label layers and linkage code, run on the same public files, must produce the
same pairs if both read the files correctly. Every difference would point at a
decoding or label defect on one side.

**Counted.**

| link | omnisus (RR 2022) | pegasus_data (RR 2022) |
|---|---|---|
| SIH deaths → SIM: records | 1,340 | 1,340 |
| passes (pairs / control) | 1,085 / 1 · 68 / 0 · 29 / 0 | 1,085 / 1 · 68 / 0 · 29 / 0 |
| linked | 1,182 (88.2%) | 1,182 (88.2%) |
| residence agrees | 85.9% (passes 1–2) | 86.3% (all passes, incl. pass 3 where it is a key) |
| died in hospital | 1,181 of 1,182 | 99.92% |
| SIM infant deaths → SINASC: records | 196 | 196 |
| pass 1 (weight) | 117 / 0 | 117 / 0 |
| pass 2 (mother's age) | 23 / 5, dropped | 23 / 5 (21.7%), dropped |
| linked | 117 (59.7%) | 117 (59.7%) |
| delivery type · plurality agree | 96.4% · 99.3% | 95.7% · 99.1% (canonical categories, ADR-0109) |
| SINASC deliveries → SIH: pairs | 8,846 | 8,846 |
| control pairs · chance | 168 · 1.9% | 168 · 1.9% |
| obstetric diagnosis · residence | 96.8% · 94.1% | 96.77% · 94.09% |
| denominator | 10,638 (deliveries in hospitals present in SIH) | 12,956 (all deliveries) |

**Findings.**
- Every pair count and every control count agrees exactly. The differences
  are definitional:
  - validation over different pass sets;
  - a denominator restricted differently;
  - agreement compared on canonical categories rather than label text.
  
  No decoding or label defect on either side for these fields.
- The engine's drop rule reproduces omnisus's judgement on the
  mother's-age pass. The verdicts are viable, viable and viable (omnisus: use
  with caution for SIH → SIM, where its validation was residence at 85.9%;
  ours counts "died in hospital", 99.9%, as the strongest held-out check).

**Consequence.** The deterministic baseline is established: the probabilistic
engine (plan A4) is judged against these numbers, at equal or lower measured
chance.
