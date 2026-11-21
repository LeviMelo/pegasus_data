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
           "pages": item.get("page") or item.get("article-number"), "authors": [f"{a.get('family', '')} {''.join(w[0] for w in a.get('given', '').split())}".strip() for a in item.get("author", [])]}
    out[key] = rec
    print(key, "|", rec["year"], "|", "; ".join(rec["authors"][:4]), "|", rec["title"][:90], "|", rec["journal"][:40], rec["volume"], rec["pages"], "|", rec["doi"])
    time.sleep(1.0)
json.dump(out, open("crossref.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
