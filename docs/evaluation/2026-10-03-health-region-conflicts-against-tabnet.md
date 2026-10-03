# Contested health regions against TabNet's current table

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`, after commit 4c34bfe;
- membership pack `resources/geography.parquet` as committed (the per-system
  `CIRBRN` tables);
- TabNet's `territorio/br_regsaud.cnv`, cached on 2026-10-03 under
  `pegasus_data_home/registries/tabnet`.

**Script and artifact:** `scripts/health_region_conflicts.py`, artifact
`data/probes/geography/health_region_conflicts.json`.

**Why.** OQ-10 left 46 municipalities with a contested health region and
asked for a Ministry statement to settle them. TabNet's current table is
that statement (ADR-0126). What has to be counted is whether the contests
are real, and which side the current table takes.

**Method.** For each contested municipality:
- read each system's code and label;
- compare the codes in one scheme. SINASC's SC table writes UF + two digits,
  so `4214` is read as `42014` for the comparison only;
- compare with TabNet's region for the municipality.

**Result.**

| verdict | municipalities |
|---|---|
| same region, two code schemes (SINASC SC `42NN` = SIM/TabNet `420NN`; labels agree) | 33 |
| real disagreement; TabNet's current table = SINASC | 11 |
| real disagreement; TabNet's current table = SIM | 2 |

- **All 46 contests are SIM against SINASC:** 44 in SC and 2 in RS.
- **The real disagreements are region changes.**
  - SC: `Nordeste` (SIM) against `Vale do Itapocú` (SINASC, TabNet);
    `Alto Uruguai Catarinense` (SIM) against `Oeste` (SINASC, TabNet);
    `Meio Oeste` (SINASC) against `Alto Vale do Rio do Peixe` (SIM,
    TabNet).
  - RS: 430605 and 432220, where TabNet sides with SINASC.
- **Neither system's table is dated** (empty validity windows), so which
  vintage each holds is inferred from the current table only.

**Consequence.** ADR-0129: a system-neutral current roll-up uses
`health_region_current`, and per-system claims stay as they are. OQ-10 is
resolved.
