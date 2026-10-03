# STATUS.md

What is true now. This file is rewritten in place, never appended to. Its
history is in git; measurements are in `EVALUATION.md` and decisions in
`DECISIONS.md`. Last rewritten 2026-09-30.

## Where the project is

`redesign` (2026-09-28 to 09-30: meaning on the read path, every variable
described and code translatable, ADR-0061 to ADR-0106) was live-verified and
fast-forwarded into `master` on 2026-09-30, locally (not pushed). Work
continues on branch **`linkage`**: record linkage across systems, planned in
`docs/plans/linkage.md` (ADR-0107).

## Record linkage (branch `linkage`, ADR-0107 to ADR-0117)

- **Foundations.**
  - Record identity `(_blob_sha256, _row)` on every row.
  - Roles for SINASC, SIM, SIH-RD, CIHA and SIA-PS, normalised through our
    own labels, with categories where systems spell a concept differently
    (ADR-0109).
- **Two engines** (`curation/links.yml`), sharing the negative control,
  held-out validations and verdicts fixed in advance:
  - **deterministic** (ADR-0110);
  - **probabilistic** (ADR-0111): evidence in bits, error channels learned
    from leave-one-field-out anchors, u from 200,000 random pairs, threshold
    by measured false-match rate, vectorised for national candidate sets.
  - **ADR-0113:** a pair must be each side's clear best (log2(19) bits), and
    verdicts use the 95% upper bound, so ties and small samples are refused.
  - **ADR-0114:** every block keeps an identifying key; typo-variant blocks
    exist and are used only where they add links.
  - **ADR-0115:** residence is scored given the place of care. Agreement
    away from the hospital weighs about 4.7 bits; at it, 0.5–1.9 bits.
  - **ADR-0117:**
    - a newborn admission's ICD-10 P07 codes weigh against the birth's
      weight and weeks;
    - a level no anchor showed never counts for a match.
- **Five spine links and two private-sector links, 2022:**
  - viable (RR, AC): SIH deaths → SIM, infant deaths → SINASC, deliveries →
    SIH;
  - viable in SE: newborn admissions → SINASC, 406 pairs (ADR-0117). RR and
    AC certify only with caution; 89% of newborn admissions carry no size
    code (OQ-62);
  - not certifiable per state: maternal deaths (too few), but viable
    nationally;
  - CIHA (non-SUS) deaths → SIM and births → CIHA deliveries: viable in SE.
    The timeline shows non-SUS deliveries.
  
  omnisus's RR study is reproduced to the pair.
- **National, 2022: all seven links viable** under the current engine
  (probabilistic; EVALUATION 2026-09-30 "National linkage, 2022"):

  | link | pairs | FDR upper 95% |
  |---|---|---|
  | SIH deaths → SIM | 545,135 of 605,542 (90.0%) | 0.24% |
  | deliveries → SIH | 1,505,192 of 2,520,744 (59.7%) | 0.49% |
  | infant deaths → SINASC | 23,848 of 28,217 (84.5%) | 0.17% |
  | newborn admissions → SINASC | 67,340 of 389,471 (17.3%) | 1.07% |
  | maternal deaths → SIH | 845 of 1,640 (51.5%) | 1.71% |
  | CIHA deaths → SIM | 55,983 of 98,211 (57.0%) | 0.25% |
  | births → CIHA deliveries | 193,335 (7.7% of births) | 0.95% |

  Deterministic, for comparison: SIH deaths 84.9%, infant deaths 74.1%,
  deliveries 60.1%.
- **Link discovery (ADR-0119).** Given only typed fields, a placebo-checked
  search finds the hand-written keys of deliveries and in-hospital deaths
  (SIH and CIHA), and infant deaths through birth weight, which it picks on
  its own. Staged by default: the same best key from 207 keys in 2 minutes
  instead of 2,016 in 26. Race is held out.
- **The linkage theory is being executed** (`docs/plans/linkage-theory.md`,
  accepted 2026-10-03; ADR-0120; what execution taught is its §11):
  - **T1, the lake.** Linkage reads the lake through cached role tables.
    Records carry a content key (`_record_key`), the same whichever
    publication is read (OQ-65).
  - **T2, scope invariance.** A slice linked against the nation, with
    national u, pooled m and the national calibration, reproduces the
    national run's pairs (SP 99.97%).
  - **The placebo shifts every left date.**
  - **T3, entities.** `build_entities()` merges links into persons;
    inherited evidence (`inherit:`) doubled Sergipe's newborn link (410 →
    828 pairs, FDR 0.36%).
  - **T4, settings as annotators.** Race is modelled per setting
    (`annotators.py`).
  - **T5, linkage error into analyses.** `p_match` on every pair;
    `link_draws()`.
  - **Running:** the national lake rebuild with record keys, the seven
    national links, the scope test, entities, race, and SIH ~ CIHA discovery.
- **Impossible pairs** (a death before the admission, a death at home) are
  mostly recording errors in true pairs. They become learned, flagged
  evidence, not rules.
- **CIHA's residence field** records the hospital's municipality for
  85–100% of mothers and 85–92% of deceased who live elsewhere, tested against
  SINASC and SIM on linked pairs (EVALUATION 2026-09-30, two entries). The
  first version of this claim rested on a match rate alone and was corrected
  after the user challenged it.
- **Surfaces.**
  - `link(method=…)`, `role_table()`, `pegasus-data link`;
  - results persisted in `<lake>/links/` and reused (ADR-0112);
  - `serve/` routes `/links` and `/links/timeline` (timelines behind
    `--allow-records`);
  - live scenarios `linkage` and `timeline`.
  - The frontend is out of scope (user, 2026-09-30).
- **National measurements** (EVALUATION 2026-09-30):
  - bits of identity for SINASC, SIM, SIH, CIHA;
  - SIA error channels (59.9% of one-digit date errors on adjacent keys);
  - travel flows by care type (oncology 46% in its own municipality);
  - SIH ∪ CIHA nearly disjoint (0.18% overlap);
  - join grains (OQ-20).
- **Meaning fixes found on the way:**
  - SINASC `LOCNASC` 5 is *Aldeia indígena* (1,966 births in 2022 read
    "Ignorado");
  - SIH `IDENT` from the layout;
  - SIH-SP `SERV_CLA` 000000 reads "Nenhum serviço/classificação
    registrado" (missing only where the procedure requires a service);
  - SIM `IDADE` 001–099 are minutes (the TabWin table said "Ignorado": 2,598
    deaths in 2022);
  - SIM `TABPAIS` codes named twice keep both names;
  - `CLASSI_FIN` texts corrected for 22 SINAN datasets that lack it in some
    or all files;
  - SINAN `ORIGEM` described from measurement, not inference;
  - `info()` marks each description's source; 504 inferred ones read as
    unverified (ADR-0116, OQ-64);
  - 1990s SIH V-codes decoded;
  - national queries of per-state datasets;
  - provenance under `select=`;
  - uncoded columns and out-of-period tables no longer warn.

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
