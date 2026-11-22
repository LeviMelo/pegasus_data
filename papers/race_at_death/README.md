# The race on the death certificate as a classification of place

A manuscript package generated from code. No journal is chosen yet; the text follows journal-independent
conventions (original article, RECORD, English).

## What is here

| path | what |
|---|---|
| `analysis/counts.py` | the candidate counts and the one-to-one infant linkage, with the columns of both records (`linkage_context`), written to `data/` (hours; reads the lake) |
| `analysis/context.py` | the municipality as a unit: SIDRA GDP, census 2010 literacy, income, urbanisation and race, CNES physicians, capitals, metropolitan and IBGE regions, how its certificates are filled (`data/municipal_context.parquet`, two minutes) |
| `analysis/common.py` | what the analyses share: births and composition, the candidate tables, the estimator's matrices and rates, the linkage |
| `analysis/results.py` | every non-spatial number into `results/results.json` (under two minutes) |
| `analysis/spatial.py` + `analysis/models.R` | space, time and context: the municipal table and contiguity graph (`prep`, `individual`), the R models (BYM2 by R-INLA; lme4 panels and multilevel models; `Rscript models.R data/spatial areal` about 25 minutes, `individual` about 15, both detached), then Moran's I, local clusters, the border test, places, consequences (`post`) into `results/spatial.json`, `results/*.parquet` and `out/supplementary_data_*.csv` |
| `figures.py` (+ `figures_space.py`) | Figures 1-9 and S1-S10 (PNG, PDF, SVG in `out/`) |
| `build.py` + `text.py`, `text_results.py`, `text_discussion.py`, `text_supplement.py` | `out/manuscript.docx`, `out/supplement.docx`; a missing number, an unverified reference or a verbal claim the results contradict stops the build |
| `references/` | `verify.py` and the Crossref records (`crossref*.json`; `verify.py methods` for the spatial and multilevel methods), official documents (`manual.json`), `reading_report.md` |
| `out/` | the built files, their PDF renderings, the audits (`audit_report*.md`) and the responses |

Rebuild, in order: `analysis/context.py`; `analysis/spatial.py prep`; `Rscript analysis/models.R data/spatial areal`;
`analysis/spatial.py individual`; `Rscript analysis/models.R data/spatial individual`; `analysis/results.py`;
`analysis/spatial.py post`; `figures.py`; `build.py`. The R interpreter is `C:\Program Files\R\R-4.4.1` (INLA 24.12.11,
lme4); without PARDISO, INLA runs with the Gaussian approximation and empirical-Bayes hyperparameters (about 45 seconds a
municipal model). `results.py` also needs `data/probes/census2010/mother_child.parquet`, `data/probes/race_own_birth`
and `data/probes/race_chain`.

## The thesis

The race on a Brazilian death certificate is neither the race the mother declared for herself nor the race families
report for children: it is a third classification, and a classification of place. It follows the racial composition
of the municipality continuously across space and across state borders, more than the wealth or the services of the
place, and it changes the measured mortality inequality between White and Brown children differently in each region.

The numbers are in `results/results.json` and `results/spatial.json` and nowhere else; the study record is
`docs/evaluation/2026-11-21-race-own-birth.md`, with ADR-0226, ADR-0229 and `docs/plans/race.md`.

## Not done: each of these blocks submission

1. **Authors, affiliations, ORCID, contributions, funding, conflicts.** The authors' decision.
2. **Data and code deposit (persistent identifier), statement on the use of generative AI** (the analysis code and the
   draft were produced with an AI system under the author's direction). Wording depends on the journal.
3. **A target journal**, then its dossier, limits and checkers. The build is above most journals' word, table and
   figure caps and is to be cut to the journal chosen.
4. **References not yet read in full.** Those read are in `references/reading_report.md`; Rebouças et al. 2022 was read
   in full (PMC9638038) and Telles 2002 in its abstract; the methods references were checked at Crossref.
5. **Language pass** by a human reader.
