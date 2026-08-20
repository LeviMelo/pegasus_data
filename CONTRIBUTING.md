# Working on this

Read this before writing anything into `curation/`. Most of the open work is
documentation, and documentation here has rules that are not stylistic.

## The one rule everything else follows

**A guess with no provenance is worse than a gap.**

A gap is visible. Someone hits it, sees the column is undocumented, and goes
looking. A plausible guess is invisible: it reads like knowledge, gets used, and
ends up in a number somebody publishes. Every mechanism in this project — the
source ranking, the confidence scores, `open_questions`, the refusal to pad a
code to make a join succeed — exists to keep those two outcomes distinguishable.

So when you cannot find out what something means, **leave it out and say so**.
That is a contribution. Describing 40 of 100 columns honestly is worth more than
100 with 60 invented, and the second is worse than doing nothing.

## Getting set up

```bash
pip install -e ".[dev]"
pytest -q                      # 545 tests, all offline
ruff check src/ tests/ scripts/
```

Nothing in the test suite touches the network. Tests that would are marked
`network` and skipped unless `PEGASUS_TEST_NETWORK=1`.

You need a catalog to do documentation work. Either build one:

```bash
pegasus-data all               # hours: crawls 207,251 files
```

or get one from whoever has it — it is a single SQLite file. `explore()` works
without one, because the map of the tree ships with the package.

## The main open work: describing variables

**4,528 columns are catalogued; about half have a description.** The rest is the
job. `docs/RESUME.md` carries the current numbers and where the good sources are.

### It runs off a queue

```bash
python scripts/doc_queue.py $CATALOG --summary      # what is left
python scripts/doc_queue.py $CATALOG --size 25      # the units, as JSON
```

A unit is ~25 columns. Take one, describe it, write
`curation/variables/<slug>.yml`, validate, move on. Units are built from what is
**still undescribed right now** and named by a hash of the columns they contain,
so the queue is idempotent: re-running it after you stop produces fewer units and
never repeats one. There is no state to maintain and no coordination needed
between people working in parallel — two of you can take different units and
neither will duplicate the other.

This shape was learned expensively. Earlier waves handed one worker 130 columns
that were written to disk only at the very end; when the run was interrupted,
twenty minutes of finished research vanished. Small units that write immediately
lose only what is in flight.

### Finding what a column means

Order that has actually worked:

```bash
python scripts/doc_files.py $CATALOG SINAN     # what the FTP tree carries
python scripts/evidence.py $CATALOG --system SINAN --limit 400
```

`evidence.py` gives you, per column: declared type and width from the file
header, what the detectors concluded, bound codelists, the values actually
observed with their labels, and which series and years it appears in. **Read the
observed values.** They tell you more than the name — a column whose values are
1/2/9 labelled Masculino/Feminino/Ignorado is a sex field whatever it is called.

Then, roughly in order of yield:

- **DATASUS layout documents** on the tree. There are only 56 in total, so this
  is usually not the answer.
- **SINAN field dictionaries are not on the FTP tree.** They live at
  `portalsinan.saude.gov.br/images/documentos/Agravos/<AGRAVO>/DIC_DADOS_<AGRAVO>_v5.pdf`,
  with the shared notification block in `DIC_DADOS_NET_Not_Individual_rev.pdf`.
- **`Dados_Abertos/SINAN/` names the agravos in Portuguese** where the legacy
  tree has only four-letter codes — `ACBI` is `Acidente_tbr_mat_biologico`. Use
  the disease name as your search term.
- **SISCAN**: INCA's requisition and result forms, and the notas técnicas at
  `tabnet.datasus.gov.br/cgi/SISCAN/doc/`.
- The web generally, and what you know about the domain.

A layout document being silent is a reason to keep looking, **not** a finding to
write down. See "the failure mode" below.

### What a description looks like

```yaml
system: SINAN
asserted_by: your-name
variables:
  DT_SIN_PRI:
    official_name: Data dos primeiros sintomas
    translated_name: Date of first symptoms
    description: >
      Date the patient first showed symptoms of the notified disease. Earlier
      than DT_NOTIFIC, sometimes by weeks, so incidence counted by onset differs
      from incidence counted by reporting.
    code_system: none
    source: layout_doc
    source_ref: DIC_DADOS_NET_Not_Individual_rev.pdf, campo 8
    notes: >
      Optional. Anything that will mislead someone using this naively.
```

Say what **one value of this column IS in the world**. "Município de residência"
rendered as "the municipality of residence" adds nothing. This does:

> IBGE 6-digit code of the municipality where the patient lived, as recorded at
> admission — not where they were treated, which is `MUNIC_MOV`.

`source:` must be one of:

| | means |
|---|---|
| `layout_doc` | you read it in a DATASUS document. Put the document in `source_ref`. |
| `web` | an identifiable published source. Put the URL in `source_ref`. |
| `def` | from the TabNet `.DEF`/`.CNV` files themselves. |
| `inferred` | you worked it out. **Requires `reasoning:`** and `asserted_by:`. |
| `manual` | you are asserting it from domain knowledge. Requires `asserted_by:`. |

`inferred` is legitimate and expected — the naming grammar is regular (`DT_` data,
`ID_` identificação, `CS_` característica, `NU_` número, `SG_` sigla, `NM_` nome,
`TP_` tipo, `QT_` quantidade, `VAL_` valor, `CO_`/`CD_` código). Inferring
`DT_SIN_PRI` from the prefix plus a date-typed column is sound reasoning; write
it down in `reasoning:`. What is not acceptable is dressing an inference as
`layout_doc`.

`code_system:` is `internal` (a DATASUS-invented code nobody can read — the label
replaces it), `external` (a real identifier in its own right: CID-10, CBO, IBGE,
CNES — the code is kept beside its label), or `none` (dates, money, counts, free
text, identifiers). Set it from **what the column is**, not from what the catalog
binds to it: `.DEF` binds tabulation axes to raw columns, so a date arrives bound
to a year table.

### Validate before you commit

```bash
python scripts/validate_curation.py $CATALOG curation/variables/<slug>.yml
```

It asks two different questions. First, does the file load — a bad `source`, a
`multi_valued` without a `token_rule`, an `inferred` description with no
reasoning. Second, and this is the one nothing else asks: **does the description
contradict the data?** A field described as a date whose observed values are
single characters; a field described as free text that is bound to a codelist.
Those read plausibly and survive review.

Warnings prefixed `SPURIOUS-BINDING?` are findings about the *catalog*, not
errors in your file. Collect them and leave your curation alone.

### The failure mode to avoid

One batch answered the brief by auditing DATASUS's paperwork instead of
describing columns:

> Count of rooms/offices at fixed grid position 30 of the Estabelecimentos (ST)
> record's physical-installations block. The source layout table gives this exact
> generic label for every one of QTINST01 through QTINST37 with no field-specific
> wording; it does not identify, in this document, which installation type each
> numbered position counts…

Ninety words on what a PDF fails to say, repeated near-identically thirty-seven
times. Nobody reading the data wants a review of DATASUS's documentation; they
want to know what `QTINST30` counts. The rewrite found the CNES *tipo de
instalação física* table, and each column now names its own room type in about
twenty words.

The validator now refuses descriptions over 70 words, descriptions that discuss
the document rather than the column, and three or more that open identically.

## Repo layout

```
src/pegasus_data/
  catalog/       the SQLite catalog: schema and access
  discovery/     FTP crawl, listing dialects, reconciliation
  inventory/     filename grammar, strata, families, the header census
  acquire/       content-addressed fetch cache
  decode/        readers dispatched by content probe, not by suffix
  profile/       distributional evidence and semantic detectors
  semantics/     .CNV/.DEF parsing, the dictionary, curation loading
  normalize/     typing, sentinels, geography, time
  persist/       Parquet lake and the reference tables
  curation/      HAND-WRITTEN. The manual-authority rung. Ships with the package.
  resources/     the 1 MB map of DATASUS, so explore() works offline
  view.py        read-time labelling and render profiles
  retrieve.py    fetch(): one call, DATASUS to a table
  explore.py     what is on the server, answered from the shipped map
  translate.py   label data someone already has
scripts/         operator tools: the doc queue, evidence, validation
tests/           545 tests, offline
```

## Things that will trip you up

- **Codes are matched at exact width, never padded or truncated.** A 3-character
  CBO-1994 code and the first three characters of a CBO-2002 code are different
  things, and 452 tables on the tree mix classifications in one file.
- **Meaning is versioned.** A 1995 admission decodes against the 1992–1997
  vintage, not today's. Labels are joined at read time for exactly this reason.
- **A codelist is scoped by system.** Thirteen systems ship a file called
  `SEXO.CNV` and they disagree — SIHSUS codes sex 1/3, SINASC 1/2, SINAN M/F.
  Merging them once made `1` mean both Masculino and Feminino.
- **Personal identifiers pass through unmodified.** If you find a column holding
  CPF, CNS or a name, document it plainly — that is a finding worth surfacing.
  Do not propose masking, hashing or dropping. That decision is not ours.
- **The catalog refuses to migrate.** If a table's columns disagree with the
  shipped schema it raises `CatalogSchemaError` naming `catalog-rebuild` as the
  remedy, rather than silently adding a column and carrying on.
- **Derived output is replaced, not accumulated.** Every stage that re-derives
  clears its own output first. A stale partition beside a fresh one is
  indistinguishable from data.

## Before you open a PR

```bash
pytest -q
ruff check src/ tests/ scripts/
pegasus-data verify            # 16 regression assertions against a real catalog
```

`verify` reporting `skip` is a first-class outcome — an assertion about the lake
cannot pass before the lake is built, and reporting that as a pass would be a
lie.

## Where to read next

- **`README.md`** — what the module does and how to call it.
- **`pegasus_data_ARCHITECTURE.md`** — how it is built and *why*, including §19,
  which records every place the implementation departs from the original brief
  and the reasoning for each.
- **`docs/FINDINGS.md`** — what we learned about DATASUS itself. Start with §0:
  a correct crawl finds 207,251 files where the previous scan found 124,810, and
  the mechanism behind that gap is the headline of the project.
- **`docs/RESUME.md`** — the operational state: what is left, what works, and how
  to pick up an interrupted run.
