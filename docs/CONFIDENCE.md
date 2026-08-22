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

**Labels are refused on columns the dictionary can decode.** A real fetch of
SIH-RD 2023 returned **36 of 142 columns unlabelled**, including `DIAG_PRINC`
and every `DIAGSEC*`. DATASUS's own CID-10 table is present and correct — 2,039
three-character codes and 12,214 four-character ones, `K808 → "K80.8 Outr
colelitiases"` — and the data holds `K808`. The renderer still refused, because
§6.2 matches code widths exactly and the codelist mixes widths 3 and 4. A rule
written to prevent mislabelling is preventing labelling, on the most important
column in the dataset.

**`fetch(labels=True)` cannot work on a fresh install.** The package ships
`tree.parquet` and two schema files (~1.4 MB) and no dictionary. Labels require
unpacking a bundle (~10 MB per system, ~153 MB for all), which nothing fetches
automatically and the quickstart does not mention.

**The catalog is ~200× larger than its information content.** `SIASUS.MUNICBR`
holds 5,728 distinct labels — about Brazil's municipality count — as 280,004
enumerated codes across 4 stored vintages. One `.CNV` rule for "Brasília"
becomes 10,000 rows. This is why a semantics rebuild takes over an hour and
holds a write lock that blocks `curate` and `fetch`.
