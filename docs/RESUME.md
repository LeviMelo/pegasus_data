# Where this stands, and what to do next

Written so that continuing does not depend on anyone remembering the last
session. Everything below is checked against the catalog, not recalled.

## State

**Counts live in `pegasus_data_ARCHITECTURE.md` §21 and only there.** This file
used to carry its own State table; it disagreed with §21 by a factor of three
and nobody could tell which was current, so it no longer holds numbers. Read §21
for what exists, and `scripts/evidence.py $CATALOG --plan` for the live position.

What this file is for: where to pick up, and what bites you when you do.

Working catalog (not in the repo — it is data):

```
$SC/home_e2e/_catalog/catalog.sqlite
# where $SC = C:/Users/Galaxy/AppData/Local/Temp/claude/
#             C--Program-Files--x86--Steam-steamapps-common-Europa-Universalis-V-game-in-game-common/
#             d044c7fd-ea26-4b3a-9785-a94d0c7e296c/scratchpad
```

Interpreter is the project conda env, **not** the base one, whose pytest is
broken by a stale `pyreadline`:

```
C:/Users/Galaxy/miniconda3/envs/pegasus/python.exe
```

## If a documentation wave was interrupted

Agents write one YAML per batch to `curation/variables/<slug>.yml` **at the end
of their turn**, relative to the repo root. A batch cut off mid-turn writes
nothing; a batch that finished has its file on disk whether or not the workflow
as a whole completed.

So after any interruption:

```bash
ls curation/variables/                     # anything here is unsaved work
python scripts/validate_curation.py $CATALOG curation/variables/*.yml
mv curation/variables/*.yml src/pegasus_data/curation/variables/
pegasus-data curate                        # load into the catalog
git add -A && git commit
```

The canonical location is `src/pegasus_data/curation/` — inside the package,
because it ships. The repo-root `curation/` only exists because agents are told
a path relative to the repo; consolidating is a step, not an accident.

## The work that remains

Every catalogued column now has a description, so the description backlog is
closed. What is left is not more of the same work:

1. **The columns that do not decode.** Counts in ARCHITECTURE §21; WHY they are
   hard, and what would settle each, in `pegasus_data_ARCHITECTURE.md` §22.1b. Short version:
   RESP has no laboratory-result table anywhere on the tree, SINAN needs
   `TAB_SINANNET.zip` parsed per agravo rather than per system, and SISCAN needs
   INCA's requisition forms. None of these is unblocked by effort alone.

2. **Prose quality in the older curation.** `scripts/validate_curation.py` flags
   descriptions over 70 words, ones that discuss the source document rather than
   the column, and runs of three that open identically. The newer files are
   clean; SINAN, SISCAN and SIASUS carry the backlog. Run the validator over
   `src/pegasus_data/curation/variables/*/*.yml` for the live list.

3. **The inferred entries have never had an independent review.** This is the
   top-ranked doubt in `pegasus_data_ARCHITECTURE.md` §22.1 and it needs a domain reader with
   the paper forms, not another pass from the same author.

To see the current position at any time:

```bash
python scripts/evidence.py $CATALOG --plan
```

### What actually works for finding meaning

Learned the expensive way; a wave briefed without this produces a third as much.

- **SINAN's field dictionaries are not on the FTP tree.** They are at
  `portalsinan.saude.gov.br/images/documentos/Agravos/<AGRAVO>/DIC_DADOS_<AGRAVO>_v5.pdf`,
  with the shared notification block in `DIC_DADOS_NET_Not_Individual_rev.pdf`.
  One batch read 25 of these.
- **`Dados_Abertos/SINAN/` names the agravos in Portuguese** where the legacy
  tree has only four-letter codes — `ACBI` is `Acidente_tbr_mat_biologico`. Use
  the disease name as the search term. The mapping is already loaded as
  `dataset_docs`; `scripts/sinan_agravos.py` regenerates it.
- **SISCAN**: INCA requisition and result forms, plus the TabNet notas técnicas
  at `tabnet.datasus.gov.br/cgi/SISCAN/doc/`.
- `scripts/doc_files.py $CATALOG <SYSTEM>` lists what the tree itself carries —
  56 documents in total, so it is usually not the answer.

### The failure mode to brief against

A batch once answered by auditing DATASUS's paperwork: ninety words on what a
PDF fails to say about `QTINST30`, repeated for `QTINST01` through `37`. The
rewrite found the CNES *tipo de instalação física* table and each column now
names its own room type.

`scripts/validate_curation.py` now enforces this — it refuses a description over
70 words, one that discusses the document rather than the column, and three that
open identically. Run it; it is not advisory.

### The other failure mode: believing the test suite

A municipality-decoding defect survived days of "fixed" claims because every
layer's tests passed while the output said "Baixo Acre e Purus" where it should
have said "Rio Branco". Two more defects — a doubled code
(`120001 – 120001 Acrelândia, AC`) and a data dictionary with every description
blank — were then found in minutes by opening a generated CSV. None of the three
had a failing test, because nothing asserted on the rendered STRING a person
opens; the suite measured column lists, coverage percentages and report objects,
all of which are measurements of the *process* rather than the *answer*.

**Before claiming any labelling or rendering work is done:** run a real `fetch`,
write the file, open it, and read the values. `docs/FINDINGS.md` §3k is the full
account.

**Use Sonnet for describing.** Measured on identical work: Opus produced 0
descriptions for 1.77M tokens (all agents died on a session limit); Sonnet
produced 270 for 1.08M, and later 1,009 more. Opus earns its cost on adversarial
review and synthesis, not on reading evidence and writing YAML.

## Known open items

- **~~`fetch()` rebuilt every reference table on first use.~~ Closed.** It now
  materialises only the requested system and merges that scope transactionally.
- **`scriptPath` on the Workflow tool** fails permission validation in this
  environment ("script contains control characters"). Send the script inline.
- **~~Ranking could still pick from an arbitrary first 12 tables.~~ Closed by
  refusal.** Curated variable → decoder links still bypass ranking. For an
  uncurated field with more than `_MAX_CANDIDATES` bindings, rendering now leaves
  the raw codes unlabelled (or raises in strict mode) and asks for curation; the
  cost cap no longer becomes an epistemic decision.
- **35.2% of measurable bindings decode nothing.** Recorded in
  `field_codelists.decodes_observed` and ranked last at render time, not deleted:
  `.DEF` really did declare them, and the measurement only covers values the
  profiler has seen.
- **`SIM.TABOCUP` holds 2,780 stale rows** whose code and label are swapped. The
  parser was fixed; the catalog kept what the old one wrote. `pegasus-data
  semantics` re-derives them. `verify` check 16 fails until it is run.
