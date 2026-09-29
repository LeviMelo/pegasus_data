## 2026-08-23 — What we are least sure of (ARCH §22)

*Split from docs/history/pegasus_data_ARCHITECTURE.md §22 on 2026-09-28; text unchanged.*

## 22. What we are least sure of

`docs/FINDINGS.md` records things we measured that contradicted an assumption.
This section records the opposite: **claims this project makes that are not
well-evidenced**, ranked by how much damage a wrong one would do.

It sits in this document rather than beside it because it is not a different
subject. A reader who opens the architecture to learn what the system does
should meet, in the same place, the parts of that description the evidence does
not fully carry. Kept separate, it drifted: decode coverage ended up filed here
as a doubt, disagreeing with the counts in §21, which is exactly the failure §21
now guards against.

Every entry states what would settle it. Delete an entry when it is settled; do
not soften one because it is uncomfortable.

### 22.1 Variable descriptions rest largely on inference, self-audited

**Claim made:** 4,528 columns described, "100% coverage".

**What is actually behind it:** of 4,298 curation entries, **1,799 carry
`source: inferred`** — reasoning from column name, observed values and
neighbouring fields, not a document. The remainder cite a layout document, a
`.DEF`, or the web.

**Why it is the top entry:** a wrong description is worse than a missing one.
A missing description makes an analyst go and look; a confident wrong one does
not. And the audit that cleared these was written by the same author as the
descriptions — an internal vagueness pass flagged 489 entries and then
reclassified 433 of them as acceptable. Nobody independent has reviewed any of
it.

**What would settle it:** a domain reviewer sampling ~100 `inferred` entries
against the paper forms and layout documents, and reporting an error rate.

### 22.1b The columns that still do not decode

**Claim made:** the module decodes DATASUS's codes.

**What is actually behind it:** most of them; the count is in §21. What belongs
here is why the remainder is hard — and, twice now, why it was not.

Two blockers recorded here turned out not to be blockers, and both failed the
same way: the obstacle was asserted rather than tried.

- SINAN was recorded as needing `TAB_SINANNET.zip` parsed per agravo, treated as
  unavailable. It is 44 MB on the same FTP tree this package crawls, carrying 626
  `.CNV` tables and 60 `.DEF` files — and a `.DEF` is exactly the per-agravo
  field-to-table statement said to be missing.
- SISCAN was recorded as needing INCA's forms because `TAB_SISCAN.rar` is RAR5
  and no extractor was available. 7-Zip was already installed on the machine. The
  kit holds 103 `.CNV` tables whose TITLES name the columns outright — "Atipia em
  celulas escamosas", "Celulas atipicas de significado indeterminado-escamosas",
  "Periodo do Preventivo" — so the mapping is DATASUS's own title against
  DATASUS's own column label, not a guess.

A third obstacle was real and internal: the `.DEF` parser matched only
upper-case usage markers while TabWin writes them in either case, discarding 881
of 22,675 variable lines as "unrecognised marker" and with them every binding
they declared.

**What is genuinely left:**

- **RESP** — no laboratory-result table exists anywhere on the tree for it.
- **SINAN** — agravo-specific spaces where one column name means different things
  on different forms. `TIPO_ACID` is `1 típico / 2 trajeto` on the work-accident
  dictionary and `01 administração de medicação endovenosa …` on the
  biological-exposure one; 21 columns were refused outright during the harvest
  for exactly that, because a merged table would label a typical accident as an
  IV administration.
- **SIA** — APAC sub-form columns, and CNES references that are registries.
- **PCE · ESUSNOTIFICA · SINASC** — per-state or non-DATASUS spaces: health
  districts are defined by each state, DRS is a São Paulo structure, Febraban
  bank codes are not DATASUS's to publish.

**What would settle it:** per-agravo (family-scoped) bindings for the SINAN
columns whose meaning genuinely varies — `field_codelists` can already express
that through `family_id` and nothing yet populates it; and for RESP, a source
that does not currently exist.

### 22.2 SINAN wave-1 descriptions were never checked for correctness

**Claim made:** 366 SINAN variable descriptions are documented.

**What is actually behind it:** they were produced in a first pass, then
subjected to a *vagueness* pass — is this sentence specific? — and never to a
*correctness* pass against the SINAN notification forms.

**What would settle it:** compare a sample against the agravo's own
`ficha de notificação`, which DATASUS publishes as PDF.

### 22.3 Binding decode rates are computed on a partial sample

**Claim made, previously stated too strongly:** "35.2% of bindings decode
nothing at all."

**Why that overstates it:** the decode rate is measured against the value
profile, which covers **4 systems** and only the **200 commonest values** per
column. A codelist may decode values we have never observed. The defensible
statement is *"decodes none of the values observed so far"*, and observation is
thin.

**What the evidence does support**, from a real `fetch("SIH-RD", uf="AC",
years=2023)`: `CNES` has **31 codelists bound to it** — `TCNESBR`, one per
state, plus three federal-hospital tables — all from `.DEF` at confidence 0.9,
with nothing ranking them. The renderer picked `HOSFEDRJ` (federal hospitals in
Rio de Janeiro) for Acre data. So the common failure is **over-binding with no
ranking**, not a wrong claim.

**What would settle it:** run `measure_bindings` after widening the value
profile beyond 4 systems and beyond the top 200 values.

### 22.4 Declared join grain is partly unmeasured

**Claim made:** three join keys declared — `AIH`, `CNES`, `APAC`.

**What is actually behind it:** all ten `APAC` members carry
`rows_per_key: unmeasured`. The key was declared without checking whether each
dataset holds one row per APAC or many — which is precisely the fan-out error
the declaration exists to prevent. `AIH` and `CNES` grains come from curation
statements, not from counting.

**What would settle it:** count distinct keys against row counts on a real
sample of each dataset.

### 22.5 Exhaustiveness is true of one crawl

**Claim made:** 207,030 data files, 100% bound to a declared dataset.

**What is actually behind it:** one crawl, at one moment. DATASUS has
reorganised its tree before and will again. The claim is *"nothing on the tree
as we last saw it is unaccounted for"*, which is weaker and is the honest form.

**What would settle it:** nothing permanently — it needs re-checking each crawl,
which verify step 17 does.

### 22.6 The lake has barely been exercised

**Claim made:** the pipeline decodes DATASUS into a queryable lake.

**What is actually behind it:** verify step 14 skips with "no build has been
run against this catalog". Value profiles exist for 4 of 20 systems. Most of
the decode path has been exercised by tests and by single ad-hoc runs, not at
scale.

---

### 22.7 Known-bad, already diagnosed

These are not uncertainties — they are defects with a cause, listed so they are
not rediscovered.

**~~Labels are refused on columns the dictionary can decode.~~** *Wrong, and
worth recording as wrong.* I read a fetch report as "36 of 142 columns
unlabelled, including `DIAG_PRINC`" and blamed the §6.2 width rule. Neither
half held up: `DIAG_PRINC` **is** labelled — the label arrives in a companion
column, `DIAG_PRINC_label` — and most of the rest are empty. `CID_MORTE` holds
`'0000'` in 59,835 of 59,835 rows and `DIAGSEC3` is null throughout, so
"matched none of the observed codes" was correct behaviour reported badly.
Those columns are now named as `constant` rather than filed beside real gaps.

The real defect on that path was different: `_bindings` picked one codelist per
column and the last tie-break was alphabetical, so `CNES` got `HOSFEDRJ` — six
federal hospitals in Rio — while `TCNESBR` sat in the same lake with 7,189 rows
covering every code in the file. Fixed by measuring candidates against the
column. After both changes: 41 labelled, 23 constant, 9 genuine gaps, and the 9
are dates, identifiers and day-counts that `.DEF` should never have bound.

**~~`fetch(labels=True)` cannot work on a fresh install.~~** *Closed.* The wheel
now carries a 28.6 MB windowed label pack and the bindings, and a clean-machine
`fetch("SIM-DO", uf="AC", years=2022)` returns 56 labelled columns. See
ARCHITECTURE §14.9. Along the way this turned up a crash on the same path:
`_discover` unpacked `list_directory`'s `(entries, method)` tuple as a bare
list, so *every* fresh install died before reaching the labelling question at
all — which is what comes of never running the user's own first command.

**~~A label can be broader than the column it decodes.~~** *Closed, and the
diagnosis is worth keeping because every layer behaved as designed while
producing a wrong answer.* `.DEF` binds SINASC's `CODMUNRES` to **145 tables**,
all at confidence 0.9, one of which is `CIRAC` — a 24-row health-region table
containing every municipality code mapped to the region that contains it.

Four correct mechanisms composed into a wrong result:

1. `_rank` breaks a confidence tie on name affinity, then **alphabetically**.
   No table is named `CODMUNRES`, so with 145 candidates tied the tie-break that
   actually decided the answer was alphabetical order.
2. `CIRAC` sorts 3rd. `BR_MUNICIPALFA` sorts **118th**.
3. `_choose_binding` historically measured only the first `_MAX_CANDIDATES`
   (12) candidates — a cost bound, since `.DEF` binds `DIAG_PRINC` to 114 tables.
4. So the correct table was bound, never loaded, never measured. `CIRAC`
   decodes 100% of municipality codes and won.

The runtime now refuses any uncurated candidate set larger than that bound;
the cap can no longer silently become the choice. The granularity tie-break
(§22.7, `CNES → HOSFEDRJ`) was the fix for exactly
this shape and could not fire, because it only ranks candidates that were
*measured*. The rollup guard did fire, and named the problem in a warning —
which is not the same as not doing it. A caller who did not read warnings got a
region where they asked for a city.

**The fix is that the link is stated, not inferred.** The variable → decoder
link is a static build object, so a municipality column names its table in
curation and ranking never decides the answer. 167 corrections across 36
curation files: 128 columns onto `BR_MUNICIPALFA` and 12 onto `BR_MUNICGESTOR`.

Two further defects surfaced in the same sweep, both of which silently produced
an *empty* label column rather than a wrong one:

* **56 curated references named a codelist that does not ship** — `ibge_municipio`
  on 30 columns, and the prose placeholder `'..._MUNICIP (per-UF IBGE
  municipality lists)'` on 6. A curated list bypasses measurement by design
  (§14.12), so a misspelled table does not fall back to a bound one; it decodes
  nothing, with no error.
* **Per-UF lists on national columns.** `SIM.MUNIRES` named `AC_MUNICIP` —
  Acre's 32 municipalities — and `SINASC.MUNI_MAE` named `BR_CAPITAL`, a list of
  capitals. Not rollups; simply the wrong 0.6% of the country.

`BR_MUNICIPALFA` is the municipality table: 5,642 exact keys at 0.992
granularity, accented, and UF-suffixed so the ~250 city names shared across
states stay distinct. `BR_MUNICGESTOR` is the same list plus the "UF0000 —
gestão estadual" sentinels, which is why the `*_GESTAO` columns use it.
`MUNICBR` remains bound as a secondary: 41% of its rows are ranges, but it alone
carries the 62 pre-1988 Goiás codes transferred to Tocantins.

Verified on real data, not on a fixture: `fetch("SINASC-DN", uf="AC",
years=2022)` returns `120040 → 'Rio Branco, AC'` across 5,353 rows, with zero
unlabelled municipality cells and zero rollup warnings.
`tests/test_municipality_never_labels_a_region.py` holds it.

**The catalog is ~200× larger than its information content.** `SIASUS.MUNICBR`
holds 5,728 distinct labels — about Brazil's municipality count — as 280,004
enumerated codes across 4 stored vintages. One `.CNV` rule for "Brasília"
becomes 10,000 rows. This is why a semantics rebuild takes over an hour and
holds a write lock that blocks `curate` and `fetch`.
