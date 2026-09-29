# IBGE as a geography authority — the audit, the API, and what we take from it

**Audited 2026-08-23** against `https://servicodados.ibge.gov.br/api/v1/localidades`
and the shipped label pack. Every number below is reproducible from the code in
`src/pegasus_data/sources/ibge_localidades.py`.

**The decision in one line:** IBGE supplies territorial identity, DATASUS keeps
the health-service geography it invented, and each membership records which
authority answered. This is a **supplement**, not a replacement — the replacement
case does not survive measurement.

---

## 1. Why this was opened

Geography kept producing wrong answers. `CIRAC` — Acre's 24-row health-region
table — was declared as the *national* roll-up and returned nothing outside Acre
(FINDINGS §3n). `RSAUDBR` turned out to carry two incompatible regionalisations
under one codelist name. `BR_MACSAUD` conflicts with itself on 66% of
municipalities, so no health macroregion ships at all.

The question was whether DATASUS's geography is trustworthy, and if not whether
a maintained authority should replace it.

---

## 2. The API

### Which one is current

| endpoint | status | what it is |
|---|---|---|
| `servicodados.ibge.gov.br/api/**v1**/localidades` | **current** | the territorial ontology — this is what we use |
| `…/api/v2/localidades/*` | **503** | does not exist |
| `…/api/v3/localidades/*` | **503** | does not exist |
| `…/api/v3/agregados` | current | *statistical tables*, a different service (this is the SIDRA-style aggregates API) |

`v1` is not a legacy version here. For **localidades** it is the only version;
the higher version numbers on `servicodados` belong to other services. The
aggregates API (`/v3/agregados`, 70 aggregates) answers "what are the published
statistics", which is not the question this document is about.

### What each endpoint returns

Measured on the audit date:

| path | rows | note |
|---|---:|---|
| `/v1/localidades/regioes` | 5 | the great regions |
| `/v1/localidades/estados` | 27 | UFs |
| `/v1/localidades/municipios` | **5,571** | **the one we use** |
| `/v1/localidades/mesorregioes` | 137 | legacy, retired 2017 |
| `/v1/localidades/microrregioes` | 558 | legacy, retired 2017 |
| `/v1/localidades/regioes-intermediarias` | 133 | current, replaced mesorregião |
| `/v1/localidades/regioes-imediatas` | 510 | current, replaced microrregião |

### One request is enough

`/municipios` returns the **whole hierarchy nested inside each municipality**, so
there is nothing to paginate and nothing to join client-side:

```json
{
  "id": 1100015,
  "nome": "Alta Floresta D'Oeste",
  "microrregiao": {
    "id": 11006, "nome": "Cacoal",
    "mesorregiao": { "id": 1102, "nome": "Leste Rondoniense",
      "UF": { "id": 11, "sigla": "RO", "nome": "Rondônia",
              "regiao": { "id": 1, "sigla": "N", "nome": "Norte" } } }
  },
  "regiao-imediata": {
    "id": 110005, "nome": "Cacoal",
    "regiao-intermediaria": { "id": 1102, "nome": "Ji-Paraná",
      "UF": { … } }
  }
}
```

Both hierarchies are present in the same record: the **legacy** chain
(micro → meso → UF → região) and the **current** chain
(imediata → intermediária → UF → região).

Note the id is IBGE's **7-digit** code. DATASUS writes the same municipality with
six digits, dropping the check digit, and a join by equality between the two
matches nothing — §7.1, and the single most common way a Brazilian health
analysis loses its denominator. `Municipality` carries both.

---

## 3. The audit

### 3.1 Municipality identity — DATASUS is very nearly right

| source | plausible municipalities |
|---|---:|
| **IBGE** | **5,571** |
| `BR_MUNICIPALFA` | 5,585 |
| `MUNICBR` | 5,647 |
| `BR_MUNICIP` | 5,647 |

Only **three** IBGE municipalities are absent from `BR_MUNICIPALFA`:

| code | name | explanation |
|---|---|---|
| `530010` | Brasília | **not actually missing** — covered by the range row `530000–539999` |
| `431454` | Pinto Bandeira | present in `MUNICBR` under the older code `431453` |
| `510183` | Boa Esperança do Norte | created 2021, not yet installed |

So municipality coverage is **not** a reason to replace anything. IBGE's value
here is as an independent **validator**, and as the source of truth when a code
changes.

> **A correction worth recording.** An earlier pass of this audit reported
> "Pescaria Brava (420547) appears in zero codelists" as a headline finding. The
> code was wrong — Pescaria Brava is `4212650` → `421265` — and the municipality
> is present. The finding was an artifact of a misremembered code, not of the
> data. Checked against IBGE, the real gap is three codes, two of them
> explicable. This is the same failure mode as FINDINGS §3e and §3k: a confident
> claim built on an unverified premise.

### 3.2 Meso- and microregion — measured IDENTICAL, once compared correctly

Comparing **labels** suggested DATASUS and IBGE disagree badly:

| comparison | agreement by label |
|---|---:|
| `MESOBR` vs IBGE mesorregião | **14.3%** |
| `MICROBR` vs IBGE microrregião | 74.1% |

That number is an **artifact of the comparison**. `.CNV` labels are width-limited,
so DATASUS writes `Leste RO` where IBGE writes `Leste Rondoniense`, and
`Colorado Oeste` for `Colorado do Oeste`. Comparing **partitions** — which
municipalities group together, regardless of what the group is called — gives the
real answer:

| comparison | DATASUS groups | IBGE groups | DATASUS groups split by IBGE | IBGE groups split by DATASUS |
|---|---:|---:|---:|---:|
| `MICROBR` vs IBGE microrregião | 558 | 558 | **0** | **0** |
| `MESOBR` vs IBGE mesorregião | 139 | 137 | **0** | 2 |

`MICROBR` **is** IBGE's microregion classification, exactly. `MESOBR` is IBGE's
mesoregion classification plus two extra groups, and both extras are the same
thing: DATASUS files three municipalities under "Ignorado" where IBGE knows the
answer.

| municipality | DATASUS | IBGE |
|---|---|---|
| `431936`, `432146` | `4300 Ignorado RS` | `4301 Noroeste Rio-grandense` |
| `510619` | `5100 Ignorado MT` | `5101 Norte Mato-grossense` |

This is the FINDINGS §3e lesson again: **most apparent contradiction was
manufactured by the comparison method.** Had the audit stopped at the label
comparison it would have concluded DATASUS's geography was 86% wrong. It is not
wrong at all; it is abbreviated.

### 3.3 What DATASUS does not publish at all

IBGE **retired** mesorregiões and microrregiões in 2017 and replaced them with
**Regiões Geográficas Imediatas** (510) and **Intermediárias** (133). Neither
appears in any of the 2,348 codelists the label pack ships. Every DATASUS
geography roll-up above the municipality is on a classification IBGE deprecated
nine years ago.

That is the strongest argument for adding IBGE, and it is an argument for
*addition* rather than replacement: the legacy classifications must stay,
because thirty years of health data is tabulated against them.

### 3.4 What IBGE does not have

**Health regions.** The *Região de Saúde* (CIR), the *colegiado de gestão* and
the health macroregion are Ministry of Health constructs. IBGE publishes no
equivalent and no crosswalk to them. They stay with DATASUS, which is the
decisive reason this cannot be a replacement.

---

## 4. What we take, and from whom

| classification | authority | members | why |
|---|---|---:|---|
| `uf` | IBGE | 27 | identity |
| `ibge_macroregion` | IBGE | 5 | identity |
| `ibge_intermediate_region` | IBGE | 133 | **current**; DATASUS publishes none |
| `ibge_immediate_region` | IBGE | 510 | **current**; DATASUS publishes none |
| `ibge_mesoregion` | IBGE | 137 | legacy, kept; IBGE has full names and resolves the 3 "Ignorado" |
| `ibge_microregion` | IBGE | 558 | legacy, kept; measured identical to `MICROBR` |
| `health_region` | DATASUS | 467 | Ministry construct, IBGE has none |
| `health_colegiado` | DATASUS | 303 | Ministry construct |
| `metropolitan_region` | DATASUS | 95 | partial coverage by design |
| `citizenship_territory`, `pndr_region`, `agglomeration`, `capital` | DATASUS | — | programme groupings |

Every row of `geography.parquet` carries an `authority` column, and
`Membership.authority` reports it, because a caller who rolls up to a health
region and a caller who rolls up to an intermediate region are trusting different
institutions and should be able to see which.

`MESOBR` and `MICROBR` moved to the `excluded:` block of
`curation/geography.yml` with their measurements — **superseded, not wrong**,
which is a distinction the file records explicitly.

---

## 5. How it is wired

```
IBGE /v1/localidades/municipios
        |
        v
sources/ibge_localidades.py   fetch_municipalities() -> tuple[Municipality]
        |                     save_cache() / load_cached() for offline rebuilds
        v
geography.build_geography_pack(..., ibge=municipalities)
        |                     merges with the .CNV compile, one row per
        |                     (municipality, classification, system, window, authority)
        v
resources/geography.parquet   ~132k rows, ~152 KB, SHIPS
        |
        v
geography.memberships(code)   -> Membership(..., authority="ibge" | "datasus")
```

**The raw IBGE payload does not ship.** It is 2.5 MB of JSON against a 152 KB
compiled pack, and it is re-fetchable in about a second — so per ARCHITECTURE
§14a it is build-time state, not package content. `save_cache()` writes it
wherever the maintainer wants for an offline rebuild.

### Rebuilding

```python
from pegasus_data.sources.ibge_localidades import fetch_municipalities
from pegasus_data.geography import build_geography_pack

build_geography_pack("src/pegasus_data/resources/geography.parquet",
                     ibge=fetch_municipalities())
```

The fetch is one request, about a second, and refuses to compile a response with
fewer than 5,000 municipalities so a truncated answer cannot quietly become the
shipped pack.

---

## 6. What is still open

* **Health macroregion still ships nothing.** `BR_MACSAUD` conflicts on 66% of
  municipalities and `MSAUDBR` on 4%; IBGE has no equivalent. Resolving it needs
  a Ministry source this project does not yet read.
* **46 municipalities have contested health regions** — publishing systems
  disagree on the name. IBGE cannot arbitrate, because it does not model health
  regions at all.
* **Vintage.** IBGE's endpoint returns *today's* division. Municipalities move
  between regions and regions are redrawn, so a 1995 record rolled up through
  today's hierarchy is being placed where it would be *now*. The compiled rows
  carry empty validity windows to say the vintage is unknown rather than
  asserting they are valid for all time. IBGE does publish historical divisions
  and wiring them in is the natural next step.
