# Where this stands, and what to do next

Written so that continuing does not depend on anyone remembering the last
session. Everything below is checked against the catalog, not recalled.

## State

| | |
|---|---:|
| columns catalogued | 4,528 |
| columns described | 1,572 (**34.7%**) |
| families | 1,633 across 16 systems |
| datasets documented | 40 |
| bindings measured to decode nothing | 658 of 1,871 (35.2%) |
| tests | 541 passing |

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

## The work that remains, largest first

| system | columns left |
|---|---:|
| SINAN | 1,978 |
| SISCAN | 487 |
| SIASUS | 290 |
| CNES | 105 |

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

**Use Sonnet for describing.** Measured on identical work: Opus produced 0
descriptions for 1.77M tokens (all agents died on a session limit); Sonnet
produced 270 for 1.08M, and later 1,009 more. Opus earns its cost on adversarial
review and synthesis, not on reading evidence and writing YAML.

## Known open items

- **`fetch()` rebuilds every reference table on first use** when the lake has
  none — `rmtree` plus a full scan. Correct but expensive; should be per-system.
- **`scriptPath` on the Workflow tool** fails permission validation in this
  environment ("script contains control characters"). Send the script inline.
- **35.2% of measurable bindings decode nothing.** Recorded in
  `field_codelists.decodes_observed` and ranked last at render time, not deleted:
  `.DEF` really did declare them, and the measurement only covers values the
  profiler has seen.
- **`SIM.TABOCUP` holds 2,780 stale rows** whose code and label are swapped. The
  parser was fixed; the catalog kept what the old one wrote. `pegasus-data
  semantics` re-derives them. `verify` check 16 fails until it is run.
