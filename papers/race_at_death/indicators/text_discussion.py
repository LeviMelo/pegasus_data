# The Discussion and references of the indicators paper. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, "Over the same deaths, the White to Brown ratio of infant and child mortality in Brazil depended on how the deaths and the denominators were classified. With both "
        "classified by the mother, children of White mothers died less often than children of Brown mothers, as in a linked cohort of 19.5 million births "
        f"{cite('reboucas2022')}. With certified deaths over births by the mother's race, the Ministry's infant indicator, the direction reversed, and it reversed in most of "
        "the country's regions. Over a census-based population the infant ratio was close to the mother's-race ratio, and at 1-4 years, as rates after infancy are computed, "
        "the excess of Brown children shrank toward none. The same certified deaths give a reversal or not depending on the denominator, because the census, like the "
        "certificate and unlike the mother, classifies part of Brown mothers' children as White.")
para(d, "Why the certificate reverses the ratio over births. The certificate records the mother's race for most children of White mothers but classes a quarter of Brown "
        "mothers' infants as White and more than half of Black mothers' infants as Brown. Deaths therefore move from the Brown to the White numerator while births stay "
        "where the mothers declared; Brown births outnumber White births, so the deaths moved out of the Brown category are many relative to the White deaths they join: the "
        "White rate rises and the Brown rate falls. The regional pattern follows from the same arithmetic. Where White births are rare, a few deaths moved into the White category double a small "
        "White rate; where they are the majority, the Brown rate loses the deaths moved out of it. Earlier Brazilian comparisons of infant mortality by race between sources "
        f"found differences in opposite directions {cite('cardoso2005', 'caldas2017')}; the present results show why both directions can occur, since the result depends on "
        "the denominator and on the composition of the place.")
para(d, "Strengths and limitations. The deaths of infants were linked one-to-one, with a false-link rate under 1% a year and equal linkage of White, Brown and Black "
        "certificates, so the reversal in infancy does not rest on the estimator used after infancy; the national and regional ratios are computed over the same births. "
        "Limitations: the mother's race on the birth record is itself filled by staff in practice and is a declaration, not a truth; the estimator after infancy finds only "
        "children who did not move and loses precision in the largest municipalities; the census-based population is modelled between and after censuses; the family's "
        "classification is a 2010 reference applied by mother's race and age, without an interval; and the regional mother's-race ratios rest on few White deaths where White "
        "births are rare.")
para(d, "Implications. An indicator of racial inequality in child mortality should classify the deaths as its denominator classifies the births. For infants, linking "
        "deaths to their birth records, which the Ministry's own systems allow, gives both by the mother's race. For older children, rates by the mother's race need "
        "person-years from births by the mother's race, or a linked cohort. Where certified race must be used, the ratio should be reported with its denominator named "
        "and read against the racial composition of the place, since the same certified deaths give opposite conclusions over births and over the census.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Brown children's excess mortality relative to White children, present with deaths and births classified by the "
        "mother, was reversed by the Ministry's infant indicator in most regions; over census-based denominators it was kept in infancy and compressed toward none at 1-4 years.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
