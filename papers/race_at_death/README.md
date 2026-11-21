# Race recorded on death certificates and race declared at birth in Brazil

A manuscript package generated from code. No journal is chosen yet; the text follows journal-independent
conventions (original article, observational study of linked routinely collected records, English).

## What is here

| path | what |
|---|---|
| `analysis/results.py` | computes every number of the paper from the study's artefacts into `results/results.json` |
| `results/results.json` | the one source of the numbers |
| `references/verify.py`, `crossref.json` | each reference looked up at Crossref (authors, title, year, volume, pages, DOI) |
| `references/manual.json` | institutional references with a URL tested on the date written in them |
| `build.py` | builds `out/manuscript.docx`, `out/supplement.docx` and the figures (PNG, PDF, SVG); a missing number or reference stops the build |
| `out/` | the built files, their PDF renderings, page images, `audit_report.md` |

Rebuild: `python papers/race_at_death/analysis/results.py` (about ten minutes; needs the data home and the probe
artefacts under `data/probes/race_own_birth` and `data/probes/race_chain`), then `python papers/race_at_death/build.py`.

## The thesis

The race on a Brazilian death certificate disagrees with the race on the birth record at every age before 25. Among
children, the mortality rate ratio between White and Brown has opposite directions under the two classifications
(0.66 by the mother's race, 1.43 by the certificate at ages 1-4). At 15-24, people recorded as White at birth are
certified White less often when they die from assault (0.38) than from natural causes (0.69). The design does not say
whether the disagreement is an error of the certificate or a difference between two valid classifications, and the
paper says so.

Evidence, in the order of the paper: (1) an estimator that needs no one-to-one match, validated on infant deaths
against a one-to-one linkage, valid below 25,600 births a year; (2) children 1-9: the proportion certified with the
mother's race and mortality rate ratios under both classifications, with a sensitivity analysis without the largest
municipalities; (3) ages 15-24: certified race by cause of death; (4) birth cohorts at birth and at three censuses;
(5) three readings of race for the same woman (supplement).

The study record behind it: `docs/evaluation/2026-11-21-race-own-birth.md`, ADR-0226 and ADR-0229, `docs/plans/race.md`.
An independent audit of the first build and what was done with it: `out/audit_report.md`, `out/audit_response.md`.

## Not done: each of these blocks submission

1. **Authors, affiliations, ORCID, contributions, funding, conflicts.** The authors' decision.
2. **Ethics statement, data and code deposit (persistent identifier), statement on the use of generative AI** (the
   analysis code and the draft were produced with an AI system under the author's direction). Wording depends on the journal.
3. **A target journal**, then its dossier, limits and checkers (word and reference caps, abstract structure, table and
   figure caps, citation style). The current build is 4,400 words including tables and references, 17 references,
   4 tables, 3 figures, 6 supplementary tables.
4. **References read against the sentences they support.** All 17 journal references exist at Crossref with matching
   metadata; none was re-read in full for this draft. Each must be read by an author before submission; a real paper
   cited for a claim it does not make is still a wrong citation.
5. **Keywords** checked against MeSH/DeCS.
6. **IBGE as a cited source** for the census tabulations and the official population estimates: its pages refuse
   scripted requests (HTTP 403); the reference is to be added after a check in a browser.
7. **The audit's open points** (`out/audit_response.md`, "Not done"): a wider literature comparison, official documents for
   facts of the data systems, extraction dates and a flow diagram, intervals for the three readings. A second audit
   of the revised build has not been run.
8. **Language pass** by a human reader; the conventions ask for it once the science is frozen.

## Not in this paper

The population account (`docs/plans/population.md`) is not written up: its results are an alignment with IBGE's
official figures and tested interval laws, with no thesis of its own yet. It serves this paper only as the source of
the census cohorts' racial composition.
