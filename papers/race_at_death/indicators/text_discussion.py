# The Discussion and references of the indicators paper. Executed by build.py after text_results.py.
# ruff: noqa: F821
assert D2["absolute"]["mother"]["brown"]["excess_deaths"] > 20000, "no longer tens of thousands"
assert D2["by_region"]["South"]["certified_over_child"]["white"] > 1 > 0.7 > D2["by_region"]["Northeast"]["certified_over_child"]["white"], "the regions no longer split on the child's denominator"
d.add_heading("Discussion", level=1)
para(d, "The usual infant mortality rate by race in Brazil divides deaths classified by the child's race, on the certificate, by births classified by the "
        "mother's, on the birth record. Classified consistently, by the mother in both terms or by the child in both, the children of Brown mothers died more "
        "often than those of White mothers; the usual rate reversed this. The reversal came from one flow above all, Brown mothers' infants certified White, "
        "larger than the whole net change and partly offset by White mothers' infants certified Brown. Nationally, households classify Brown mothers' infants "
        "as White in a similar proportion, and with births classified as households classify infants the certified ratio fell below 1 again, though with an "
        "interval that includes 1; by region the point estimates did not: above 1 in the South and well below it in the Northeast, without intervals, which "
        "suggests that the certificate and the household do not classify the same children alike everywhere and that the child's denominator restores the "
        "comparison only on average. The usual ratio stayed above 1 in every year, before and after the first month and for every cause, so the reversal is a property of the rate, not of a period or a "
        f"kind of death. Earlier comparisons of infant mortality by race between sources found differences in opposite directions {cite('cardoso2005', 'caldas2017')}, "
        f"and inconsistent classification of numerator and denominator is a known source of bias {cite('hahn1992', 'arias2016')}; the 2 x 2 shows its size and "
        "direction for Brazil.")
para(d, "The Black category behaves differently. By the mother's race, Black mothers' infants died more often than Brown mothers'; on the certificate they "
        "were mostly classified Brown, and the ratio stayed below 1 even over births classified as households classify infants, because the certificate uses "
        "the Black category less than households do (a companion paper examines who records it). For Black infants the usual indicator and the consistent one "
        "by the child disagree for a reason other than the mismatch of terms.")
para(d, "Strengths and limitations. Infant deaths were linked one-to-one to their births, with linkage scaled by certified race, and every term of the 2 x 2 "
        "comes from the same deaths and births. Limitations: the mother's race is a staff-entered declaration and the reference here, not a truth; the child's "
        "race in the denominator comes from households' classification in 2010, applied nationally and by region, without an interval of its own; the "
        "jackknife intervals do not include the error of the linkage; unlinked deaths were assumed to fall by the mother's race as linked deaths of the same "
        "certified race; the analysis after infancy rests on an estimator whose shares found cannot be checked by race; and the regional models were fitted "
        "separately for each classification, so the regional contrasts between them carry no joint uncertainty.")
para(d, "Implications. A rate of infant mortality by race should classify the deaths and the births alike. Linking deaths to their birth records, which the "
        "Ministry of Health's own systems allow, gives both by the mother's race; reporting the child's race requires a denominator of children classified the "
        "same way. Read as it is usually computed, the rate hides an excess of tens of thousands of deaths among the children of Brown mothers.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. The usual rate mixes the child's race and the mother's, and the mixture reverses the White to Brown "
        "inequality in infant mortality; consistently classified, the excess of Brown mothers' children is present, and that of Black mothers' children is "
        "present by the mother's race.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
