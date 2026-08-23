# What we are least sure of

`FINDINGS.md` records things we measured that contradicted an assumption.
This file records the opposite: **claims this project makes that are not
well-evidenced**, ranked by how much damage a wrong one would do.

It exists because the project's whole pitch is that it says what it knows and
what it does not. That promise is empty unless the doubts are written down
somewhere a reader can find them, rather than living in whoever last touched
the code.

Every entry states what would settle it. Delete an entry when it is settled;
do not soften one because it is uncomfortable.

---

## 1. Variable descriptions rest largely on inference, self-audited

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

## 1b. 143 code-bearing columns still have no working table

**Claim made:** the module decodes DATASUS's codes.

**What is actually behind it:** 2,014 of 2,157 columns that curation declares as
holding a code (93.4%) reach a codelist that ships. 128 have no binding and 15
are bound to a table the pack does not carry.

**Why the remainder is hard rather than merely undone:**

| system | left | why |
|---|---:|---|
| SINAN | 53 | agravo-specific codes whose dictionary either has no value table or contradicts another agravo's reading of the same column name |
| SISCAN | 29 | cytology-pattern columns where several plausible tables ship and the name does not say which |
| SIA | 17 | APAC sub-forms |
| RESP | 12 | **no laboratory-result table ships for RESP at all** |
| SIH · PCE · CNES · ESUSNOTIFICA | 12 | per-state or non-DATASUS code spaces (health districts, Febraban bank codes) |

21 columns were refused outright during the SINAN harvest because two
dictionaries read the same code differently — TIPO_ACID is `1 típico` in the
work-accident forms and `01 administração de medicação endovenosa` in the
biological-exposure one. Those are recorded rather than merged; a merged table
would label a typical accident as an intravenous administration.

**What would settle it:** the agravo-specific SINAN tables need
`TAB_SINANNET.zip`'s .CNV set parsed per agravo rather than per system, so a
column can carry a different table in each form. SISCAN needs INCA's own
requisition forms to disambiguate the cytology patterns. RESP needs a source
that does not currently exist in the tree.

## 2. SINAN wave-1 descriptions were never checked for correctness

**Claim made:** 366 SINAN variable descriptions are documented.

**What is actually behind it:** they were produced in a first pass, then
subjected to a *vagueness* pass — is this sentence specific? — and never to a
*correctness* pass against the SINAN notification forms.

**What would settle it:** compare a sample against the agravo's own
`ficha de notificação`, which DATASUS publishes as PDF.

## 3. Binding decode rates are computed on a partial sample

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

## 4. Declared join grain is partly unmeasured

**Claim made:** three join keys declared — `AIH`, `CNES`, `APAC`.

**What is actually behind it:** all ten `APAC` members carry
`rows_per_key: unmeasured`. The key was declared without checking whether each
dataset holds one row per APAC or many — which is precisely the fan-out error
the declaration exists to prevent. `AIH` and `CNES` grains come from curation
statements, not from counting.

**What would settle it:** count distinct keys against row counts on a real
sample of each dataset.

## 5. Exhaustiveness is true of one crawl

**Claim made:** 207,030 data files, 100% bound to a declared dataset.

**What is actually behind it:** one crawl, at one moment. DATASUS has
reorganised its tree before and will again. The claim is *"nothing on the tree
as we last saw it is unaccounted for"*, which is weaker and is the honest form.

**What would settle it:** nothing permanently — it needs re-checking each crawl,
which verify step 17 does.

## 6. The lake has barely been exercised

**Claim made:** the pipeline decodes DATASUS into a queryable lake.

**What is actually behind it:** verify step 14 skips with "no build has been
run against this catalog". Value profiles exist for 4 of 20 systems. Most of
the decode path has been exercised by tests and by single ad-hoc runs, not at
scale.

---

## Known-bad, already diagnosed

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
now carries a 19.8 MB label pack and the bindings, and a clean-machine
`fetch("SIM-DO", uf="AC", years=2022)` returns 56 labelled columns. See
ARCHITECTURE §14.9. Along the way this turned up a crash on the same path:
`_discover` unpacked `list_directory`'s `(entries, method)` tuple as a bare
list, so *every* fresh install died before reaching the labelling question at
all — which is what comes of never running the user's own first command.

**A label can be broader than the column it decodes.** `.DEF` binds SINASC's
`CODMUNRES` to `CIRAC`, a health-region table containing every municipality code
mapped to the region that contains it. It decodes 100% of the column and reports
Rio Branco as "Baixo Acre e Purus". Granularity now breaks the tie against such
rollups, and where one is the only table bound it is used and named — but the
underlying binding is still wrong and nobody has fixed it.

**The catalog is ~200× larger than its information content.** `SIASUS.MUNICBR`
holds 5,728 distinct labels — about Brazil's municipality count — as 280,004
enumerated codes across 4 stored vintages. One `.CNV` rule for "Brasília"
becomes 10,000 rows. This is why a semantics rebuild takes over an hour and
holds a write lock that blocks `curate` and `fetch`.
