# Race at death: one evidence base, several papers

Manuscripts generated from code. No journal is chosen yet; the texts follow journal-independent conventions (original
article, RECORD, English). The papers, their questions and their state are in `PAPERS.md`.

## What is here

| path | what |
|---|---|
| `analysis/counts.py` | the candidate counts and the one-to-one infant linkage, with the columns of both records (`linkage_context`), written to `data/` (hours; reads the lake) |
| `analysis/context.py` | the municipality as a unit: SIDRA GDP, census 2010 literacy, income, urbanisation and race, CNES physicians, capitals, metropolitan and IBGE regions, how its certificates are filled (`data/municipal_context.parquet`, two minutes) |
| `analysis/common.py` | what the analyses share: births and composition, the candidate tables, the estimator's matrices and rates, the linkage |
| `analysis/results.py` | every non-spatial number into `results/results.json` (two minutes) |
| `analysis/spatial.py` + `analysis/models.R` | space, time and context into `results/spatial.json`, `results/*.parquet` and `results/supplementary_data_*.csv` (stages `prep`, `individual`, `post`; R stages `areal` 28 min, `ratio` 2 min, `individual` 8 min, detached) |
| `analysis/pair.py`, `analysis/estimator.py`, `analysis/simulate.py` | paper 6: the second validation pair (admissions that ended in death to their certificates), both validations with four standard errors (`results/estimator.json`), the simulation study (`results/simulation.json`, ~50 min) |
| `figures.py` (+ `figures_space.py`; `figures_estimator.py` for paper 6) | every figure, by name, into `figures/` (PNG, PDF, SVG) |
| `build.py <paper>` | one paper's `out/manuscript.docx`, `out/supplement.docx`, `out/build_report.json` from its folder's `text.py`, `text_results.py`, `text_discussion.py`, `text_supplement.py`; a missing number, an unverified reference or a verbal claim the results contradict stops the build |
| `place/`, `indicators/`, `estimator/` | papers 1, 2 and 6 (`place/audits/` holds the four audits of the combined manuscript and the responses) |
| `references/` | `verify.py` and the Crossref records (`crossref*.json`), official documents (`manual.json`), `reading_report.md` |

Rebuild, in order: `analysis/context.py`; `analysis/spatial.py prep`; `Rscript analysis/models.R data/spatial areal`
and `ratio`; `analysis/spatial.py individual`; `Rscript analysis/models.R data/spatial individual`; `analysis/results.py`;
`analysis/spatial.py post`; `analysis/panel.py`; `Rscript analysis/panel.R data`; `figures.py`; `figures_space.py`; `build.py place`; `build.py indicators`. PDFs: `soffice --headless --convert-to
pdf` in each `out/`. R is `C:\Program Files\R\R-4.4.1` (INLA 24.12.11 without PARDISO: Gaussian approximation, empirical
Bayes; lme4 with nAGQ = 0). `results.py` also needs `data/probes/census2010/mother_child.parquet`,
`data/probes/race_own_birth` and `data/probes/race_chain`.

The numbers are in `results/results.json` and `results/spatial.json` and nowhere else; the study record is
`docs/evaluation/2026-11-21-race-own-birth.md`, with ADR-0226, ADR-0229 and `docs/plans/race.md`.

## Not done: each of these blocks submission

1. **Authors, affiliations, ORCID, contributions, funding, conflicts.** The authors' decision.
2. **Data and code deposit (persistent identifier), statement on the use of generative AI** (the analysis code and the
   drafts were produced with an AI system under the author's direction). Wording depends on the journal.
3. **Target journals**, then their dossiers, limits and checkers.
4. **References not read in full**: see `references/reading_report.md`.
5. **Language pass** by a human reader.
6. **Paper 2 has not had an independent audit** of its own text (its numbers are those audited in paper 1's build).
