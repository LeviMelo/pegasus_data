# Reading notes: references of paper 6 (the estimator)

Checked 2026-11-21; Belin and Rubin 1995 and Chipperfield and Chambers 2015 added 2026-11-22 after the audit (finding 16). Crossref records by `references/verify.py estimator` (`crossref_estimator.json`; Chipperfield et al. 2011
matched another work and was dropped). Abstracts read from OpenAlex (browser User-Agent); full texts not read. Binder 1983
and Goodman 1953 have no open abstract (JSTOR) and are not cited; the linearisation is described, not attributed. References shared with papers 1-2 are read in
`references/reading_report.md`, except where noted here.

| key | claim it supports here | what the abstract says |
|---|---|---|
| fellegi1969 | probabilistic linkage gives the pairs | model for deciding link / non-link / possible link from agreement vectors, with the two error rates (read now; the shared report had it NOT READ) |
| doidge2019 | linkage error biases what is estimated from linked pairs | missed and false links act as missing data, misclassification, unrepresentative sampling; information and selection bias |
| harron2017 | as above; comparing linked and unlinked records | guide to evaluating linkage quality: gold-standard subset, linked against unlinked characteristics, sensitivity to the procedure |
| lahiri2005 | regression on linked data corrected for known link probabilities | unbiased regression estimator given the probabilities that pairs are links; mixture models to estimate them; simulation |
| hof2012 | partially identifying variables; wrong pairs must be removed | extends Lahiri-Larsen and a weighted least squares; all wrong pairs must be removed for unbiased coefficients, which needs strong assumptions |
| goldstein2012 | every candidate record carried into the analysis | multiple imputation using all potential matches instead of the maximum-weight one; full probabilistic linkage may be unnecessary |
| tancredi2011 | linkage and analysis modelled jointly (no claim that this estimator propagates matching uncertainty) | hierarchical Bayesian matching model propagating uncertainty both ways, for linkage and population size |
| pita2018 | a 114 million cohort linked to health databases with 93-97% true matches | AtyImo; 114 million cohort linked to health and administrative data; 93-97% true matches |
| lipsitch2010 | the idea of a negative control, borrowed (the paper detects bias; it does not subtract it) | negative exposure and outcome controls detect confounding and other errors |
| morris2019 | ADEMP structure of the simulation | aims, data-generating mechanisms, estimands, methods, performance measures; Monte Carlo error |
| lash2014 | the simulation of unequal shares found as a bias analysis (the t_a/t_b scaling is algebra, not from the paper) | good practices of quantitative bias analysis: bias models, parameter values, interpretation |
| benchimol2015 | RECORD reporting | extension of STROBE for routinely collected data, 13 items |
| belin1995 | the false-match rate must be estimated; linkage estimates it from a model of the weights | mixture of weights of true and false matches fitted by EM, false-match rate for each cutoff; slightly conservative in simulation |
| chipperfield2015 | cross-tabulations of linked files corrected for linkage error | parametric bootstrap for inference on cross-tabulated variables from probabilistically linked files (1-1 linkage); simulation and a real application |
