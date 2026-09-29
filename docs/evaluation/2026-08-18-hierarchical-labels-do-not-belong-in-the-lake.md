## 2026-08-18 — Labels for hierarchical classifications do not belong in the lake

*Split from docs/history/FINDINGS.md §3b on 2026-09-28; text unchanged.*

## 3b. Corrections after review

Three things were reviewed and changed after the first pass. All three were right.

### Labels for hierarchical classifications do not belong in the lake

The first implementation materialised a `<field>_label` column for every decoded field, following
§7.1 step 3 literally. For `SEXO` that is correct. For `DIAG_PRINC` it is wrong for three reasons
that have nothing to do with size:

* **It fixes a granularity choice invisibly.** `E11` and `E119` are distinct rows in CID-10.
  Whichever codelist won the coverage ranking became *the* label, and the analyst inherited that
  choice without being told one was made.
* **It discards the versioning this module built.** The 1992–1997 CID-10 has 14,197 codes and
  today's has 14,253; `valid_from`/`valid_to` exist precisely to keep both true. A string baked into
  a 2019 row throws that away and cannot be corrected without rewriting the lake.
* **The published wording is lossy and dated.** `DESCR` is 50 characters: `N39.0` reads
  "Infecc do trato urinario de localiz NE".

Code tables now live in `lake/reference/<table>/window=<valid_from>/` and are joined on demand:

```python
cid = load_reference("CID10", year=1995)   # 14,197 codes, the 1992–1997 table
cid = load_reference("CID10", year=2019)   # 14,253 codes, the current one
cbo = load_reference("CBO", code_width=6)  # CBO-2002, not CBO-1994
```

Small closed codelists still get a materialised label. `describe()` reports which policy applies,
names the reference table, lists its validity windows and its roll-up levels, and says how to join.
Meaning stays fully recoverable — P1 and §12 step 10 are unaffected — it simply stops being frozen.

`bind_by_semantic_type` was demoted at the same time. A distributional membership rate is an
inference, and §13 keeps inferences out of the labelling path; it is now promoted only when a record
layout independently names the same classification.
