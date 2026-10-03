## ADR-0120: The linkage theory, executed: lake-backed roles, national partner and calibration, a placebo that breaks every key, entities, inherited evidence, settings as annotators

**Date:** 2026-10-03. **Status:** active. **Part of:** ADR-0107; executes
docs/plans/linkage-theory.md (steps T1–T5). Extends ADR-0111, ADR-0119.

**Context.** The user accepted the proposed theory (2026-10-03) and asked for it
to be executed, with hour-long runs treated as unacceptable. Each step was
measured as it was built (EVALUATION 2026-10-03, entries named below).

**Decisions.**

1. **T1. Linkage reads the lake, through cached role tables.**
   - The four linkage datasets are built into the lake once per year
     (`build --family … --years …`). National 2022: 16 minutes, 923 MB,
     against 3.1 GB of DBC blobs that every query used to decode again.
   - **`role_table` keeps each dataset-scope's roles under `<lake>/roles/`.**
     The key covers the scope, `roles.yml`, the code that reads, renders and
     normalises rows, and every lake partition file. A stale table is never
     served.
   - **Two lake-path defects found and fixed on the way:**
     - provenance (`_blob_sha256`, `_row`) was dropped by a projection;
     - derived columns (`IDADE_anos`) lost their inputs, which silently
       emptied the newborn link's left side.
2. **T2. Scope invariance.**
   - **A slice is linked against the national partner side**
     (`right_geography="BR"`).
   - **It uses the national run's chance agreement (u).** A slice's random
     pairs are not a sample of Brazil: Sergipe's residence u was 8× lower.
   - **It pools its error channels (m) toward the national ones** with
     200 pseudo-anchors.
   - **It decides with the national threshold and calibration curve**,
     stored with the national run (`<lake>/links/_params/`).
   - **Measured.** A slice's pairs equal the national run's pairs for that
     slice: SP 132,896 of 132,933 (99.97%), SE 4,700 of 4,704, RR 1,200 of
     1,201.
3. **The placebo shifts every left date, not only the birth date.**
   - With only the birth date shifted, a true pair stayed reachable through
     another block (death day + hospital). It came back into the placebo
     short only of the birth date's bits and sat at the threshold: 23.22
     against 23.35 nationally, above it in a slice, where 2,304 of 2,307
     placebo pairs above the threshold were true pairs.
   - **A null must break every identifying key.**
4. **Every pair carries `p_match`**: one minus the local false-match rate at
   its score, from the placebo, monotone by pool-adjacent-violators.
   `link_draws()` and Rubin's rules carry linkage error into analyses (T5).
5. **T3. Entities.**
   - Every spec declares the person its records are about (`person:`); the
     declaration is excluded from the spec digest, so no stored run is
     orphaned.
   - `build_entities()` merges stored links into persons, strongest first,
     refusing merges that give a person two births or two deaths.
     National: 2.39 million links, 78 refusals.
   - **Inherited evidence.** A record can take a role from its partner in
     another stored link (`inherit:`). The newborn admission's baby inherits
     its mother's delivery AIH (`number_distance`).
6. **Chance agreement is estimated where the scores are compared.** This is
   the one lesson behind three defects:
   - **Value-specific u**, from marginal frequencies, double-counted what
     blocking already conditioned on. Tried, measured worse, removed; the
     code is kept in the evaluation entry.
   - **An evidence-only comparison** takes its u from the real candidates, the
     non-matches the blocks put beside a record. Not from random pairs (an
     AIH within 100 earned +15 bits), and not from the placebo (born 400 days
     away, so it never has nearby AIHs). Measured: within 10 is +4.2 bits,
     within 100 +2.9.
   - **A slice uses the nation's u.**
7. **T4. Settings as annotators.**
   - `linkage/annotators.py` (Dawid–Skene, optionally hierarchical)
     estimates how each setting classifies the persons it shares with
     others.
   - **Race is held out of identity evidence.**
   - **Identifiability is limited:** with two settings per person, *which*
     system errs is not identified; contrasts between settings against a
     common reference are.

**Evidence** (2026-10-03):
- Sergipe newborn admissions, with the inherited AIH: 828 pairs against 410,
  estimated FDR 0.36% (upper 1.06%), perinatal diagnosis 91.1%, born in the
  admitting hospital 100%.
- Speed:
  - national SIH-deaths link 58 → about 11 minutes (the first pass and the
    lake);
  - a Roraima slice against national SIM 40 → 13 s with cached roles.

**Open (OPEN_QUESTIONS).**
- **Record identity depends on the publication read.** SINASC publishes a
  national file and per-state files. A birth read from one has a different
  `_blob_sha256:_row` than from the other, so links and entities computed on
  one do not join the other. A content-based record key is needed (OQ-65).
  **Resolved 2026-10-03 by ADR-0124:** `_record_key`, numbered for exact
  duplicates within a file.
- **Hospital-level settings and the asian coding.** Seven hospitals record
  most brown persons as asian, two of them about 89%. Code mixing is the
  hypothesis; confirming it at its source (hospital software) is outside the
  data.

**Consequences.** All seven national links are recomputed under this engine
(EVALUATION 2026-10-03, "Linkage theory executed"), and the entities and race
studies are rerun on them.
