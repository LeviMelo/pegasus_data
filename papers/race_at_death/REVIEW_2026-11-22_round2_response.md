# Response to the second review of 2026-11-22

Each point below is marked done (with where) or not done (with the reason). Every number cited here is interpolated in the manuscripts from the results files.

New code:
- `analysis/mechanism2.py` adds `declared_again|<class>|same establishment` and `|another establishment` to results/mechanism.json.
- `analysis/violence_place.py` adds `standardised_to_natural_place` and `place_of_death_distribution`.
- `analysis/indicators2.py review4` adds `review4` to results/indicators2.json.
- `build.py` adds two checks: the abstract must be at most 300 words, and the phrases in a paper's `CLAIM` list must appear in both the abstract's conclusion and the text's conclusion.

## Section 4, in order

### 1. Paper 3

**3.2: is the 0.52 the mother or the establishment?** Done. Mothers declaring again at their next birth, with the second birth in the same birth establishment or another (chance pairs subtracted):

| First declaration | Same establishment | Another establishment |
|---|---|---|
| Black | 0.556 | 0.436 |
| White | 0.78 | 0.68 |
| Brown | 0.87 | 0.87 |

Even in the same establishment barely half of Black declarations repeat. Most of the instability is therefore the mother's; the establishment adds about 12 points. The reference of all six papers is unstable mainly through the mothers' own answers. The result is in the abstract, Results ("Four levels of the Black category") and the first Discussion paragraph, and an assert guards the wording.

**3.1: rewrite from the four levels.** Done:
- The abstract states the four levels once, each with its comparator.
- The first Results section is "Four levels of the Black category" and opens from them.
- The Figure 2 note describes the new figure.
- The Discussion opens from the four levels; the separate comparator paragraph is folded into that opening.
- The abstract's and the text's conclusions drop the mother-against-infant comparison.

**3.3: Where.** Done. The section names states in full, gives regional means weighted by Black mothers (North lowest, South highest), and links them to the certificate's order and the birth record's shortfall.

**3.4: abstract.** Done; see B.

### 2. Paper 5

**5.2: the decomposition.** Done. Places of death: health establishment, home, road or elsewhere. Natural deaths were 82% in a health establishment, 12% at home and 6% elsewhere. Standardised to that distribution:

| Cause | Difference from natural deaths | Share of the crude 11.5 points that remains |
|---|---|---|
| Assaults | −6.5 points (−11.0; −2.0) | 57% |
| Other external causes | −9.3 | 88% |
| Transport | −12.9 | the whole crude difference |

Natural deaths away from a health establishment fell by 15.6 points, as much as external deaths there. The paper now says that about half of the assaults' difference goes with where they die, and the rest, with nearly all of the other external causes', goes with the cause.

**5.1: rewrite.** Done:
- Title: "Recorded less White at death: the race of young people who die of external causes against their birth and hospital records...".
- Keywords: External Causes; Death Certificates; Racial Groups; Forensic Medicine; Data Accuracy; Young Adult; Brazil.
- The Introduction is framed on death certificates for external causes and on who certifies, with homicide as one cause among them, and with the circumstances-of-certification reading.
- The objective adds "how and where they died".
- The Discussion's first paragraph, Implications and conclusion are rewritten.
- "Violent deaths" is replaced by "external-cause deaths" throughout.

**5.3: the readings.** Done. The Discussion sets four readings against each other: reclassification in life; classification at death by cause; who can answer for the race (the place of death); and darker coding by hospital clerks. Each is given with its test. It adds that the cause and the informant meet in the law: every external death goes to the medico-legal institute. The paragraph "Who certified did not explain the difference" is rewritten: the certifier field does not say who gave the race, and the place of death does bear on it.

### 3. Paper 2

**2.1.** Done. The only remaining description of the scaling ("Two classifications in each term") now refers to the post-stratification described below it.

**2.2.** Done. Caldas, Santos and Cardoso (2022), Table 5 (read on scielo.br), report Brown to White infant mortality ratios computed the usual way. The paper's computation reproduces them:

| Year | Published | Recomputed here |
|---|---|---|
| 2013 | 0.76 | 0.755 |
| 2014 | 0.72 | |
| 2015 | 0.75 | |
| 2016 | 0.76 | |
| 2017 | 0.78 | 0.784 |

Black to White is 0.36 in 2017 in both. The text gives the series and says that the published series is the usual way, which the paper shows reverses the contrast by the mother's race. An assert holds the reproduction within 0.02.

**2.3.** Done. The text gives one plain sentence: each declaration is treated as a noisy reading of a stable class, with the noise the repeat declarations measure, removed from deaths and births alike. The algebra and the Q and E matrices are in Supplementary Text S3.

**2.4.** Done. The limitations now carry both findings about the reference, with their direction. Black to Brown by the mother's race:

| States | Black to Brown |
|---|---|
| Birth record's Black share within 10% of the census | 1.17 |
| Birth record's Black share short by 40% or more | 1.02 |

The undercount dilutes the Black excess.

### 4. Paper 1

**1.1.** Done. "Analyses" gives each model in one or two sentences: smoothing, Moran, the binomial deviance models with their covariate blocks, borders, the individual and crossed models, and time and the panel. The two new tests have their own Methods paragraph.

**1.2.** Done.
- The abstract says the departure is larger than measured if the mothers still recorded Brown in whiter places are the least ambiguous ones.
- The Discussion states that selection argument in two sentences.
- It names the three rival readings of a slope above 1: fertility along composition (addressed by comparing mothers with mothers), the census respondent answering for the mother, and the years' gap.

**1.3.** Done. The objective says infants.

**1.4.** Table 1 stays in the main text.

### 5. Abstracts and the weak reference

**B. Abstracts.** The build now refuses any abstract over 300 words; all six were cut to pass (see the build reports).

**A. The weak reference.** Done. Every Discussion carries a paragraph, "The reference", citing both findings with their numbers and the direction for that paper. An assert ties it to the results.
- Papers 1 and 3: understated shortfalls.
- Paper 4: the household report is not interchangeable with the birth record.
- Paper 5: the fall from birth to the certificate, and its contrast with natural deaths, are if anything understated.
- Paper 6: the findings concern what the table means, not how well it is estimated.
- Paper 2: carried in its limitations, with the comparison of states.

**C. One rule for rewrites.** Done. Each paper defines `CLAIM`, and the build fails if the abstract's conclusion and the text's conclusion do not both state it.

## Paper 4

- **4.1** Done. The place difference is stated against the certificate's gradient (under a quarter of it), not as "alike".
- **4.2** Done. The conclusions lead with the pull toward White and away from Black.
- **4.3** Done; see B.

## Paper 6

**6.2.** Chipperfield, Bishop and Campbell 2011 stays unread pending the author. The text says the method is described from the 2015 paper by the same first author.

## Independent verification

A separate Sonnet verifier checked every point against the built text and the results files. It found seven defects; six were fixed and one was deliberately left:
- Paper 1: the abstract now carries the "understated" implication.
- Paper 3: a leftover mother-against-infant sentence in Results is reworded.
- Paper 5 abstract: "fell by +4.9" now reads "fell by 4.9", with an assert that every shift is negative.
- Paper 5 abstract: "equal composition of the place of death" now reads "equal racial composition of the municipality where the death occurred".
- Paper 5 Discussion: "a violent death" now reads "a death from an external cause".
- Paper 2: a doubled comma is removed.
- Paper 6: the sentence saying the method is described from the 2015 paper had been missing; it is restored.

Kept on purpose: "homicide among them" in paper 5's first sentence and in its Implications. There homicide is named as one external cause among others, which is the paper's finding.
