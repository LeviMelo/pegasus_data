# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-10-03.

## Where the project is

`redesign` (2026-09-28 to 09-30: meaning on the read path, every variable
described and code translatable, ADR-0061 to ADR-0106) was live-verified and
fast-forwarded into `master` on 2026-09-30, locally (not pushed). Work
continues on branch **`linkage`**: record linkage across systems, planned in
`docs/plans/linkage.md` (ADR-0107).

## Record linkage (branch `linkage`, ADR-0107 to ADR-0124)

**The theory** (`docs/plans/linkage-theory.md`; accepted 2026-10-03; what
executing it taught is in §11) is executed through T1–T5:

- **T1, records and the lake.**
  - Linkage reads the lake through role tables. They are cached per scope;
    a national table is built state by state when the lake holds only state
    partitions.
  - A record's identity is the hash of its own fields, numbered for exact
    duplicates within a file (ADR-0124). It is the same in the national and
    the state publication.
  - CIHA publishes 735,049 duplicate rows.
- **T2, scope invariance.**
  - A slice is linked against the national partner side, with national u,
    error channels per state shrunk toward the nation's (ADR-0123), and the
    national threshold and calibration.
  - Measured: SE, RR and SP give exactly the national run's pairs (SP
    133,476 of 133,476).
- **Impossibility as learned evidence** (ADR-0121): event order and
  category pairs as comparisons whose weight the data set.
  - It gains maternal deaths (+188).
  - For SIH deaths it drops 3,279 pairs that look true, which is unresolved
    (EVALUATION 2026-10-03).
- **Padded partner periods** (ADR-0121): infant deaths and newborn
  admissions read SINASC one year back. Infant deaths: 23,845 → 25,982
  pairs.
- **T3, entities.**
  - `build_entities()` merges links into persons, with uniqueness
    constraints.
  - The newborn link inherits the mother's delivery AIH, which doubled
    Sergipe's pairs.
- **T4, settings as annotators.** SIH's excess "asian" is two hospital
  practices: a default fill (04 for everyone), and SIM's code for brown
  written into SIH (one hospital, fixed in September 2022). Nothing is
  relabelled (OQ-66).
- **T5.** `p_match` on every pair (a calibrated local false-match rate);
  `link_draws()`.
- **Discovery** (ADR-0119): a placebo-checked search over typed fields finds
  the hand-written keys. SIH and CIHA share 0.4% of persons.

**National, 2022** (the latest runs: record keys, per-state channels,
ADR-0121 specs):

| link | pairs | FDR upper 95% | minutes |
|---|---|---|---|
| SIH deaths → SIM | 548,033 (90.5%) | 1.03% | 3.3 |
| deliveries → SIH | 1,533,023 (60.8%) | 0.74% | 13.3 (before the speed-up) |
| infant deaths → SINASC (2021 padded) | 25,982 (81.0%) | 0.79% | 4.8 |
| newborn admissions → SINASC (2021 padded, inherited AIH) | 79,272 (20.4%) | 1.07% | 2.4 |
| maternal deaths → SIH | 1,058 (64.5%) | 1.61% | 2.2 |
| CIHA deaths → SIM | 60,720 (61.8%) | 1.03% | 7.9 (CIHA role table uncached; fixed) |
| births → CIHA deliveries | 195,761 (7.8%) | 0.99% | 11.3 (same) |

**Speed** (EVALUATION 2026-10-03 "Performance pass"), each change checked
identical to the code it replaced:
- the SP slice of SIH deaths takes 274.5 → 41.9 s;
- a cold CIHA role build 26.2 → 14.2 s;
- the lake build of CIHA 2022, 182 → 96 s;
- linkage DuckDB is capped at 40% of RAM.

**Data sources.**
- The DATASUS FTP data channel has dropped every passive connection since
  2026-10-03 (control still answers).
- The fetcher falls back to a byte-identical public mirror, checked against
  the listed size and recorded as `mirror:<url>` (ADR-0122).
  `data/probes/ftp/data_channel.jsonl` records when the channel returns.

**Meaning fixes found on the way** (unchanged): SINASC `LOCNASC` 5, SIH
`IDENT`, SIH-SP `SERV_CLA` 000000, SIM `IDADE` minutes, `TABPAIS`,
`CLASSI_FIN`, SINAN `ORIGEM`, inferred descriptions marked (ADR-0116,
OQ-64), 1990s SIH V-codes.

**Open in linkage:**
- why the impossibility evidence drops 3,279 plausible SIH-death pairs
  (`scripts/link_pair_fate.py`);
- a coverage prior (coverage varies by stratum; not yet shown to add to
  the evidence);
- flagging unreliable race settings (OQ-66).

## Done (live-verified)

- **Presentation** (ADR-0084).
  - Headers read "Variable name (CODE)" and values "Label (code)"; an
    undecoded value reads `code (?)`.
  - Presets `readable` (the default), `analysis`, `labels` and `codes`, plus
    templates and pt/en.
  - Every coded column leaves rendering with a label companion (ADR-0093).
- **Canonical classifications,** one table for every system (ADR-0087):
  - ICD-10, falling back to the category when a subcategory is not listed
    (ADR-0089);
  - SIGTAP, with group, subgroup and form as dimensions (ADR-0092);
  - CBO 2002, banks, naturality/countries, states and health regions.
- **Establishments and legal entities.**
  - Registry names come from the CNES kit (692,004 establishments,
    ADR-0086).
  - CNPJ → legal name; a CPF is never resolved (ADR-0093).
  - A maintainer is named through the row's establishment (ADR-0094); the
    documented all-zeros is "Sem mantenedora" (ADR-0097).
- **Relations between columns.**
  - A composite key (`CLASS_SR`, `PA_CLASS_S`, `SUBFIN`), whose parts can carry
    the record's width: age unit + age via `IDADEDET` reads "3 dias"
    (ADR-0088, ADR-0098).
  - A sibling that names the code (ADR-0090).
  - Path tables whose unlisted codes are named by their deepest listed level
    (`VINCULO`, `S_CLASSEN`, ADR-0096).
- **Municipalities** show the 7-digit IBGE code.
- **The kits are read correctly** (ADR-0095). 43,916 `.CNV` lines had codes
  glued to their labels (`PACIENT15`); a re-read now supersedes the old
  reading.
- **Speed** (ADR-0097). One year of SIASUS-ACF, files cached: 104 s → 16.7 s
  (35 s in a fresh process).
- **Descriptions.**
  - DADOS_ABERTOS inherits SIASUS's curation (ADR-0095).
  - Curated: BASE_AIH1 (60 fields), SIA PQ (7), SIA UO (4) and the SI-PNI
    exports (22).
- **Sweep tools.** `scripts/sweep_undecoded.py` lists undecoded values over 16
  datasets. `scripts/def_evidence.py` lists what each `.DEF` offers for them.

## Linking datasets (ADR-0100 to ADR-0103)

- **One establishment registry.** Typed identifiers: only a valid CNPJ is
  stored, a CPF is never stored or resolved, and no identifier appears in any
  name or label (ADR-0102). The registry also holds maintainers,
  inclusion/exclusion dates, 107,438 health teams (INE) and the federal
  university hospitals.
- **CNES ↔ CNPJ** reads the registry first, then older kits' claims.
  - SIH AC 2023-01: 4,160 of 4,165 resolved, and every one confirmed by the
    admission's own `CGC_HOSP`.
  - The reverse direction works; it resolved nothing before.
- **The 2008 procedure break is bridged** by the official Tabela Unificada
  map, one-to-one only. 96.3% of SIH AC 2005 admissions reach a SIGTAP
  procedure, and the SIGTAP group/subgroup dimensions are continuous.
- **Pre-2006 occupations** decode from SIM/SINASC's own `OCUPA` table.
- **SIA's 2001–2007 establishment codes** are keyed by the file's state
  (`SIA_UPS_BR`).
- **Every legacy APAC archive's members are measured** by ranged header reads
  (1,721 of 1,723), so components reach the years they exist in (EX and PC,
  2003–2006) and absent ones are not gaps (ADR-0103).

## Coverage now

- **Kits and pack.** The maintainer catalog was re-read with the fixed parser.
  The label pack and the seed are rebuilt from it; the pack no longer loses a
  window the catalog lacks (ADR-0095).
- **Per family-field** (`pegasus-data meaning`, 22,714 rows):
  - missing descriptions: 441 → 130;
  - undecoded: 240 → 34;
  - opaque: 120.
- **Per cell, fresh home, 16 datasets:** undecoded 1.23 M → 0.56 M, with no
  regressions. What remains is mostly values that no source documents
  (EVALUATION, 2026-09-29).

## Open fronts

- **Undecoded because no source names them** (OQ-61; fresh-home sweep, 21
  columns and 48,763 cells, from 52 and 560,585 the same morning): largest SIH-SP
  `SERV_CLA` `000000`; SIA-AQ/AR histology grade and `AQ_TRANTE`; SIA-PS
  nationality and ethnicity; CNES bank codes and placeholders; SINASC
  `TPDOCRESP` `0`; SINAN-HANS `9`s; SINAN meningitis quadros (OQ-59). Each
  reads `code (?)`. Settled by measurement against other columns of the same
  record: SIH `TPDISEC*`, `SP_DES_*`, `SP_U_AIH`, `GESTOR_TP`/`GESTOR_COD`;
  SIA `TIPPRE`, `UFDIF`/`MNDIF` `9`, `PA_CODOCO`; CNES `TP_PREST` `99`,
  all-zero `CNPJ_MAN`/`CNPJ_CC`; SINASC `CODPAISRES` (ADR-0105, ADR-0106).
- **Undescribed:**
  - SIA UO's 74 modality fields and PQ's 14 name-only fields (no layout
    found);
  - BASE_AIH1's 11 fields without an RD/SP twin;
  - its age pairing, unverified until a sample of the 12 GB file is read.
- **Renamed columns** across layouts (OQ-57).
- **Speed.** A cold process still spends most of its time in per-group
  binding decisions and catalog reads.
- **Carried:**
  - distinct-count measures and age-standardised rates;
  - health macroregions;
  - moving `tools/` into the package;
  - mypy;
  - splitting `cli`, `retrieve` and `view`.

## Waiting on the user

- **Publishing.** `master` (fast-forwarded to `redesign`) and `linkage` are
  not pushed (CLAUDE.md §4). Platform wheels for the compiled DBC engine
  (ADR-0074).

## Tests and checks

- `scripts/live.py --all --fresh` and `scripts/sweep_undecoded.py` on a fresh
  home.
- `ruff check src scripts tests` and `scripts/check_docs.py`.
- `pytest -q -m "not network"` is a regression net that does not grow
  (CLAUDE.md §5).
