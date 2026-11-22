"""Each reference looked up at Crossref by its bibliographic string; the top match is kept for reading against the claim."""
import json
import sys
import time
import urllib.parse
import urllib.request

QUERIES = {
    "noymer2011": "Noymer Penner Saperstein Cause of death affects racial classification on death certificates PLoS ONE 2011",
    "saperstein2012": "Saperstein Penner Racial fluidity and inequality in the United States American Journal of Sociology 2012",
    "muniz2017": "Muniz Bastos Classificatory volatility and (in)consistency of racial inequality Cadernos de Saude Publica 2017",
    "bailey2013": "Bailey Loveman Muniz Measures of race and the analysis of racial inequality in Brazil Social Science Research 2013",
    "miranda2015": "Miranda A resurgence of black identity in Brazil? Evidence from an analysis of recent censuses Demographic Research 2015",
    "cardoso2005": "Cardoso Santos Coimbra Mortalidade infantil segundo raca/cor no Brasil: o que dizem os sistemas nacionais de informacao Cadernos de Saude Publica 2005",
    "chor2005": "Chor Lima Aspectos epidemiologicos das desigualdades raciais em saude no Brasil Cadernos de Saude Publica 2005",
    "caldas2017": "Caldas Santos Borges Mortalidade infantil segundo cor ou raca com base no Censo Demografico de 2010 e nos sistemas nacionais de informacao em saude Cadernos de Saude Publica 2017",
    "telles1998": "Telles Lim Does it matter who answers the race question? Racial classification and income inequality in Brazil Demography 1998",
    "benchimol2015": "Benchimol The REporting of studies Conducted using Observational Routinely-collected health Data (RECORD) statement PLoS Medicine 2015",
    "travassos2004": "Travassos Williams The concept and measurement of race and their relationship to public health: a review focused on Brazil and the United States Cadernos de Saude Publica 2004",
    "fellegi1969": "Fellegi Sunter A theory for record linkage Journal of the American Statistical Association 1969",
    "doidge2019": "Doidge Harron Reflections on modern methods: linkage error bias International Journal of Epidemiology 2019",
    "braz2013": "Braz Oliveira Reis Machado Avaliacao da completude da variavel raca/cor nos sistemas nacionais de informacao em saude Saude em Debate 2013",
    "liebler2017": "Liebler Porter Fernandez Noon Ennis America's churning races: race and ethnicity response changes between Census 2000 and the 2010 Census Demography 2017",
    "arias2008": "Arias Schauman Eschbach Sorlie Backlund The validity of race and Hispanic origin reporting on death certificates in the United States Vital and Health Statistics 2008",
    "romero2006": "Romero Cunha Avaliacao da qualidade das variaveis socio-economicas e demograficas dos obitos de criancas menores de um ano registrados no Sistema de Informacoes sobre Mortalidade do Brasil Cadernos de Saude Publica 2006",
    "loveman2012": "Loveman Muniz Bailey Brazil in black and white? Race categories, the census, and the study of inequality Ethnic and Racial Studies 2012",
}
THEORY = {
    "schwartzman2007": "Schwartzman Does money whiten? Intergenerational changes in racial classification in Brazil American Sociological Review 2007",
    "marteleto2012": "Marteleto Educational inequality by race in Brazil, 1982-2007: structural changes and shifts in racial classification Demography 2012",
    "roth2016": "Roth The multiple dimensions of race Ethnic and Racial Studies 2016",
    "harris2002": "Harris Sim Who is multiracial? Assessing the complexity of lived race American Sociological Review 2002",
    "campbell2007": "Campbell Troyer The implications of racial misclassification by observers American Sociological Review 2007",
    "saperstein2006": "Saperstein Double-checking the race box: examining inconsistency between survey measures of observed and self-reported race Social Forces 2006",
    "telles2002": "Telles Racial ambiguity among the Brazilian population Ethnic and Racial Studies 2002",
    "bailey2008": "Bailey Unmixing for race making in Brazil American Journal of Sociology 2008",
    "sorlie1992": "Sorlie Rogot Johnson Validity of demographic characteristics on the death certificate Epidemiology 1992",
    "hahn1992": "Hahn Mulinare Teutsch Inconsistencies in coding of race and ethnicity between birth and death in US infants JAMA 1992",
    "saperstein2010": "Saperstein Penner The race of a criminal record: how incarceration colors racial perceptions Social Problems 2010",
    "freeman2011": "Freeman Penner Saperstein Scheutz Ambady Looking the part: social status cues shape race perception PLoS ONE 2011",
    "carvalho2004": "Carvalho Wood Andrade Estimating the stability of census-based racial/ethnic classifications: the case of Brazil Population Studies 2004",
    "francis2013": "Francis Tannuri-Pianto Endogenous race in Brazil: affirmative action and the construction of racial identity among young adults Economic Development and Cultural Change 2013",
    "reboucas2022": "Reboucas Goes Pescarini Ethnoracial inequalities and child mortality in Brazil: a nationwide longitudinal study of 19 million newborn babies Lancet Global Health 2022",
    "penner2008": "Penner Saperstein How social status shapes race Proceedings of the National Academy of Sciences 2008",
    "araujo2009": "Araujo Costa Hogan Mota Araujo Oliveira Diferenciais de raca/cor da pele em anos potenciais de vida perdidos por causas externas Revista de Saude Publica 2009",
    "soares2011": "Soares Filho Vitimizacao por homicidios segundo caracteristicas de raca no Brasil Revista de Saude Publica 2011",
    "harron2017": "Harron Dibben Boyd Hjern Azimaee Barreto Goldstein Challenges in administrative data linkage for research Big Data and Society 2017",
}
METHODS = {
    "riebler2016": "Riebler Sorbye Simpson Rue An intuitive Bayesian spatial model for disease mapping that accounts for scaling Statistical Methods in Medical Research 2016",
    "besag1991": "Besag York Mollie Bayesian image restoration with two applications in spatial statistics Annals of the Institute of Statistical Mathematics 1991",
    "rue2009": "Rue Martino Chopin Approximate Bayesian inference for latent Gaussian models by using integrated nested Laplace approximations Journal of the Royal Statistical Society B 2009",
    "moran1950": "Moran Notes on continuous stochastic phenomena Biometrika 1950",
    "anselin1995": "Anselin Local indicators of spatial association LISA Geographical Analysis 1995",
    "assuncao1999": "Assuncao Reis A new proposal to adjust Moran's I for population density Statistics in Medicine 1999",
    "bates2015": "Bates Maechler Bolker Walker Fitting linear mixed-effects models using lme4 Journal of Statistical Software 2015",
    "merlo2006": "Merlo Chaix Ohlsson A brief conceptual tutorial of multilevel analysis in social epidemiology: using measures of clustering in multilevel logistic regression Journal of Epidemiology and Community Health 2006",
    "simpson2017": "Simpson Rue Riebler Martins Sorbye Penalising model component complexity: a principled, practical approach to constructing priors Statistical Science 2017",
    "keele2015": "Keele Titiunik Geographic boundaries as regression discontinuities Political Analysis 2015",
}
TARGET = "crossref.json"
if sys.argv[1:] == ["theory"]:
    QUERIES, TARGET = THEORY, "crossref_theory.json"
if sys.argv[1:] == ["methods"]:
    QUERIES, TARGET = METHODS, "crossref_methods.json"
out = {}
for key, q in QUERIES.items():
    url = "https://api.crossref.org/works?rows=1&query.bibliographic=" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={"User-Agent": "reference-check/1.0"})
    try:
        item = json.load(urllib.request.urlopen(req, timeout=40))["message"]["items"][0]
    except Exception as e:  # noqa: BLE001
        print(key, "FAILED", e)
        continue
    rec = {"doi": item.get("DOI"), "title": (item.get("title") or [""])[0], "journal": (item.get("container-title") or [""])[0],
           "short_journal": (item.get("short-container-title") or [""])[0],
           "year": (item.get("issued", {}).get("date-parts") or [[None]])[0][0], "volume": item.get("volume"), "issue": item.get("issue"),
           "pages": item.get("page") or item.get("article-number"), "authors": [f"{a.get('family', '')} {''.join(w[0] for w in a.get('given', '').split())}".strip() for a in item.get("author", [])],
           "abstract": item.get("abstract"), "type": item.get("type")}
    out[key] = rec
    print(key, "|", rec["year"], "|", "; ".join(rec["authors"][:4]), "|", rec["title"][:90], "|", rec["journal"][:40], rec["volume"], rec["pages"], "|", rec["doi"])
    time.sleep(1.0)
json.dump(out, open(TARGET, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
