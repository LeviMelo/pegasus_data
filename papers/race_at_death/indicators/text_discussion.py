# The Discussion and references of the indicators paper. Executed by build.py after text_results.py.
# ruff: noqa: F821
d.add_heading("Discussion", level=1)
para(d, "Over the same deaths, the White to Brown and Black to Brown ratios of infant mortality in Brazil depended on how the deaths were classified. With deaths and "
        "births classified by the mother, children of White mothers died less often than children of Brown mothers, and children of Black mothers more often, as in a "
        f"linked cohort of 19.5 million births {cite('reboucas2022')}. With certified deaths over births by the mother's race, the usual infant indicator, both directions "
        "reversed. After infancy the White to Brown ratios behaved in the same way. Over a census-based population the infant ratio was close to the mother's-race ratio; at "
        "1-4 years it was near 1, a value that depends on how the population account dates children's race between censuses and that this study cannot validate.")
para(d, f"Why the certificate reverses the ratios over births. The certificate records the mother's race for most children of White mothers but classes a quarter "
        f"({f2(CBP['Parda>Branca']['est'])}) of Brown mothers' infants as White and more than half ({f2(CBP['Preta>Parda']['est'])}) of Black mothers' infants as Brown, and "
        f"some White mothers' infants ({f2(CBP['Branca>Parda']['est'])}) as Brown. Births stay where the mothers declared. Brown births outnumber White births, so the "
        "deaths moved from the Brown to the White numerator are many relative to the White deaths they join, and the White rate rises; Black mothers' infants moved into "
        "the Brown numerator lower the Black rate. Where White births are rare, the ratio of the two ratios was largest, as this arithmetic predicts; elsewhere the regional "
        f"differences were smaller and mostly not credible. Earlier Brazilian comparisons of infant mortality by race between sources found differences in opposite "
        f"directions {cite('cardoso2005', 'caldas2017')}; the present results show how both directions can occur from the same deaths, since the result depends on the "
        "denominator and on the composition of the place.")
para(d, "Strengths and limitations. The deaths of infants were linked one-to-one, with a false-link rate under 1% a year and a linked share that differed by less than "
        "one point between White, Brown and Black certificates, so the primary contrast does not rest on the estimator used after infancy; the national and regional "
        "ratios are computed over the same births. Limitations: the mother's race on the birth record is itself entered by staff and is the reference here, not a truth, "
        "so a reversal means a departure from the mother's declaration; unlinked deaths were assumed to fall by the mother's race as linked ones; the estimator after "
        "infancy finds only children who did not move and was restricted to municipalities where it reproduces the linkage; the census-based population is modelled "
        "between and after censuses and its ratios carry no interval; the family's classification is a 2010 reference applied by mother's race and age, without an "
        "interval; the national intervals do not include the error of the linkage; the regional mother's-race ratios rest on few White deaths and are drawn toward the "
        "national value; and the analyses beyond the primary contrast are exploratory.")
para(d, "Implications. An indicator of racial inequality in child mortality should classify the deaths as its denominator classifies the births. For infants, linking "
        "deaths to their birth records, which the Ministry of Health's own systems allow, gives both by the mother's race. For older children, rates by the mother's race "
        "need person-years from births by the mother's race, or a linked cohort. Where certified race must be used, the ratio should be reported with its denominator "
        "named and read against the racial composition of the place.")
para(d, f"In conclusion, this study set out {OBJECTIVE}. Brown children's excess infant mortality relative to White children, and Black children's relative to Brown, "
        "present with deaths and births classified by the mother, were reversed by the usual infant indicator, nationally and in most regions by posterior means.")
d.add_heading("References", level=1)
for i, k in enumerate(order, 1):
    para(d, f"{i}. {reference_text(k)}")
d.save(OUT / "manuscript.docx")
