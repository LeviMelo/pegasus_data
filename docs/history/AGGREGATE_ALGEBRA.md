# The aggregate layer, from first principles

**Audience:** whoever decides what `aggregate()` is allowed to do. This is the
mathematical spine of `docs/AGGREGATE_DESIGN.md` — the *why* behind the phases,
written so the rules are derivable rather than memorised.

Every claim about the codebase here was measured on 2026-08-23; the numbers are
in the text so you can check them.

---

## 1. The one idea

An aggregate table is not "a smaller table". It is a **function**:

$$
a : K \rightarrow M
$$

from a **key space** $K$ (the cells: municipality × month × sex …) to a
**measure space** $M$ (what you accumulated in each cell), defined on finitely
many keys.

Rolling up is not "summing again". It is **pushforward along a map of key
spaces**. Given $\varphi : K \to K'$ — municipality → health region, or month →
year — the rolled-up table is

$$
(\varphi_{*}a)(k') \;=\; \bigoplus_{\varphi(k) = k'} a(k)
$$

Read that as: *the value at a coarse cell is everything underneath it, combined*.

Two things make this work, and **everything that goes wrong is one of them
failing**:

1. $(M, \oplus)$ must be a **commutative monoid** — associative, commutative,
   with an identity $e$. That is what makes "combine in any order, in any
   grouping" give the same answer.
2. $\varphi$ must be an actual **function** — total and single-valued on the
   support of $a$. That is what makes the coarse cells a genuine partition of
   the fine ones.

Hold on to those two. The rest of this document is consequences.

---

## 2. Store the state, not the answer

A measure has three parts, not one:

| part | type | what it does |
|---|---|---|
| **lift** | $A \to M$ | one raw observation becomes an accumulator |
| **merge** $\oplus$ | $M \times M \to M$ | two accumulators combine |
| **finalize** | $M \to V$ | the accumulator becomes the number shown |

The artifact stores $M$. The frontend applies `finalize` at the last moment.

| measure | $M$ | lift | $\oplus$ | $e$ | finalize |
|---|---|---|---|---|---|
| count | $\mathbb{N}$ | $1$ | $+$ | $0$ | id |
| sum | $\mathbb{R}$ | $x$ | $+$ | $0$ | id |
| **mean** | $\mathbb{R}\times\mathbb{N}$ | $(x,1)$ | componentwise $+$ | $(0,0)$ | $s/n$ |
| min / max | $\mathbb{R}\cup\{\pm\infty\}$ | $x$ | $\min$ | $+\infty$ | id |
| variance | $(n,\Sigma x,\Sigma x^2)$ | $(1,x,x^2)$ | $+$ | $(0,0,0)$ | $\frac{\Sigma x^2}{n}-\left(\frac{\Sigma x}{n}\right)^2$ |
| rate | $(\text{num},\text{den})$ | — | $+$ | $(0,0)$ | $\text{num}/\text{den}$ |
| distinct count | set, or a sketch | $\{x\}$ | $\cup$ | $\varnothing$ | $\lvert\cdot\rvert$ |

This is why `REQUEST.md` is right that you store `los_sum` and `los_n` rather
than `mean_los` — but the reason generalises past means. **Storing
`finalize(lift(x))` destroys $M$, and $M$ is the only thing that can be merged.**
Once you have written down a mean you can never legitimately combine it with
another.

The rule in one line: *the artifact holds monoid elements; only the display
holds numbers.*

### The measure that is not a monoid

**Median has no finite-state associative merge.** There is no bounded $M$ and
$\oplus$ that computes an exact median of a union from summaries of the parts.
Percentiles are the same. This is not an implementation gap — it is a
mathematical fact, and it is why every OLAP system either refuses medians or
computes them from raw data.

Two honest options, and the layer should offer exactly these:

* **refuse** the median at any level other than the one it was computed at;
* store an approximate mergeable **sketch** (t-digest, KLL), and label the result
  as approximate with its error bound.

What it must never do is average medians. That is meaningless and looks fine.

---

## 3. Additivity is per-axis, not global

This is the part most designs get wrong, `REQUEST.md` included.

`ledger.aggregation ∈ {additive, mean, non_summable}` (see
`semantics/ledger.py`) is a **global** claim about a field. Reality is finer.
Consider CNES bed counts, on a dataset whose declared grain is
`establishment-bed type-month`:

| roll-up | valid? | why |
|---|---|---|
| sum beds over **municipalities**, one month | **yes** | disjoint establishments, same instant |
| sum beds over **months**, one establishment | **no** | that is *bed-months*, not beds |

The correct time reducer for a stock quantity is `mean`, `last`, or `max` — never
`sum`. Meanwhile admissions *are* summable over both.

So measures fall into three classes, which is standard OLAP theory and is the
right vocabulary here:

* **fully additive** — additive along every axis. Admissions, deaths, cost.
* **semi-additive** — additive along some axes and not others. Bed counts,
  staff counts, population, any *stock*. The classic non-health example is a
  bank balance: additive across accounts, nonsense across time.
* **non-additive** — additive along none. Rates, ratios, indices, percentages.
  These are only ever stored as their components.

The distinction is **flow vs stock**. A flow is a thing that happened during an
interval (an admission, a death, a real spent) and accumulates over time. A stock
is a thing that *was the case* at an instant (a bed existing, a person alive) and
does not.

**Design consequence:** a measure declaration must name additivity **per axis**,
not once. Something like `additive_over: [geography, dimensions]`,
`time: last`. Anything else silently produces bed-months.

---

## 4. When $\varphi$ is not a function

The second failure mode, and the one this project has already been bitten by.

$\varphi$ must be **total** (every key maps somewhere) and **single-valued**
(exactly one somewhere). Real DATASUS breaks both.

### 4.1 Partial: the map is not total

`metropolitan_region` covers **1,325 of ~5,570** municipalities. Most belong to
none. So $\varphi$ is undefined on 76% of the key space, and

$$
\sum_{k' \in K'} (\varphi_{*}a)(k') \;\neq\; \sum_{k \in K} a(k)
$$

Mass is lost. The rolled-up total is a *subset* total, and it is not the national
figure — but it looks exactly like one.

**Rule:** a pushforward along a partial map must report the unmapped mass, or
carry an explicit `(unmapped)` member. Never silently drop it. The compiled
geography already records `partial_coverage: true` per classification for exactly
this.

### 4.2 Multi-valued: the map is not single-valued

Seven columns are declared `multi_valued` — SINASC's `CODANOMAL` (up to five
ICD-10 codes in one field) and SIM's `LINHAA`–`LINHAII` (the causal chain on a
death certificate).

Group births by "congenital anomaly" and a birth with three anomalies appears in
three cells. Now:

* `count(births)` summed over anomaly cells **triple-counts that birth**;
* the anomaly dimension is not a partition of births, it is a *relation*.

**Rule:** a multi-valued dimension makes counts of the *grain* non-additive along
it. Either the measure changes meaning (`count(anomaly mentions)`, which *is*
additive) or the roll-up is refused. Both are defensible; silently summing is
not. Note the two measures differ and both are legitimate — the layer must make
you say which one you meant.

### 4.3 Contested: the map is not well-defined

`memberships()` reports 46 municipalities where publishing systems assign
*differently-named* health regions. There $\varphi$ is a relation, not a
function, until you name a system.

**Rule, already implemented:** `Membership.contested` marks it, and naming a
system makes $\varphi$ a function again. An aggregate must roll up through *its
own system's* regionalisation, or its totals will not reconcile with DATASUS's
published output for the same query.

### 4.4 Non-disjoint source rows

Subtler, and not a geography problem. An AIH re-presented after rejection appears
under two competences (`curation/joins.yml` says so in the `AIH` caveats).
Counting admissions across competence counts the *episode* twice.

`joins.yml` already carries `rows_per_key: one | many | unmeasured`. `SIH.SP` is
`many` — one row per professional act — so `COUNT(*)` there counts services, not
admissions, while looking identical.

**Rule:** the identity of the thing being counted is part of the measure, which
is the next section.

---

## 5. The grain types the measure

`COUNT(*)` has no meaning until you say what a row is.

All 132 datasets declare `unit_of_analysis`, in 39 distinct kinds. The useful
split is whether the grain contains a **period component**:

| grain | datasets | `COUNT(*)` counts |
|---|---:|---|
| `notification` | 55 | notifications |
| `authorisation` | 10 | authorisations |
| `death` | 7 | deaths |
| **`establishment-month`** | **5** | **establishment-months, not establishments** |
| `admission` | 4 | admissions |
| `live birth` | 4 | live births |
| `professional-establishment-month` | 1 | professional-establishment-months |
| `establishment-bed type-month` | 1 | establishment-bed-type-months |

For a period-bearing grain, `COUNT(rows over Jan–Mar)` is **three times** the
establishment count if every establishment reported every month. That is not a
bug; it is the correct count of a different thing. The failure is calling it
"establishments".

So a measure carries a **unit**, and the unit is checked:

```
admissions       = count(admission)          # grain matches -> additive
establishments   = distinct(establishment)   # grain is establishment-month
                                             # -> needs a distinct sketch, not a sum
establishment_months = count(establishment-month)   # additive, honestly named
```

`count(establishment)` over an establishment-month grain must be **refused** in
favour of one of the last two. That refusal is the whole value of formalising
grain.

The good news, measured: the prose already names the components.
`establishment-bed type-month` is literally `[establishment, bed_type, month]`.
The formalisation is a structured component list beside the existing string, for
**39** distinct grains — not 132 hand-written files.

---

## 6. Support, zero, and structural absence

Three things look identical in a sparse table and mean different things:

| what | meaning | correct treatment |
|---|---|---|
| **sparse zero** | the combination happened zero times | materialise as $e$ on demand |
| **structural absence** | the column did not exist in that schema generation | **undefined**, not zero |
| **sentinel** | a real observation whose dimension value is unknown (`9`, `999999`) | its own member |

SIH.RD has **20 schema generations**. A municipality × year artifact spanning
1992–2026 whose dimension column appears only in later generations will show a
clean run of zeros in the early years. That reads as "nothing happened". It
means "we could not have known".

`schema_presence` and `availability()` already know exactly when each column
existed, so this is checkable rather than guessable.

**Design consequence — and this is a real addition to `REQUEST.md`:** the
artifact needs a **support mask** alongside the cells. Per (period, dimension),
whether that dimension was *available*. Without it, a time series cannot
distinguish a genuine drop to zero from a column that had not been invented yet,
and no amount of care in the measure algebra recovers the difference.

The identity element matters here too. $\text{finalize}(e)$ is $0$ for a count
and **undefined** for a mean — $0/0$ is not $0$. An empty cell must not display
as a zero mean.

---

## 7. Rates, standardisation, and the trap underneath

Store $(\text{num}, \text{den})$, finalize as $\text{num}/\text{den}$. Merging is
componentwise, so

$$
\text{rate}(A \cup B) = \frac{\text{num}_A + \text{num}_B}{\text{den}_A + \text{den}_B}
$$

which is the **crude combined rate** — correct, and *not* the mean of the two
rates. That is the thing `ledger.aggregation`'s docstring already warns about.

Two consequences worth knowing before building:

**Age-standardised rates are not recoverable from crude components.** You need
the age-stratified numerators and denominators *and* the standard population. So
a standardisable rate must keep age as a retained dimension — you cannot
reconstruct it later from a collapsed artifact. `population_series` already
records `stratifications` and an `age_standardizable` flag per series, which is
exactly the input this needs.

**Simpson's paradox is a feature of correct arithmetic, not an error.** The
crude combined rate can move in the opposite direction to every stratum-specific
rate, because the strata have different denominators. Nothing is wrong; the
combined number answers a different question. A layer that can show both the
crude and the stratified answer is being honest. One that only shows the crude
one will eventually mislead somebody about a real health question.

And the denominator must be *named*. `population_series` distinguishes `POPSVS`,
`POPTCU`, `projpop`, `censo`. Two rates computed on different series are not
comparable, so a rate measure declares its series rather than picking one.

---

## 8. So what is `aggregate()`?

Two surfaces, and keeping them apart is the point.

### Build side — maintainer, offline, expensive

```
AggregateSpec  (declared in curation)
      |
      v
build_aggregate(spec)  ->  AggregateArtifact + manifest
```

The spec says: which dataset; which **grain**; which **axis bindings** (from
`semantic_axes`, which already declares `geography: {residence, facility}` and
`time: {competence, admission, discharge}`); which dimensions to retain; which
**measures**, each with its per-axis additivity and its unit.

The artifact is a sparse Parquet dataset partitioned by year, plus a support
mask, plus a manifest whose identity is

$$
h\big(\text{spec},\ \text{source fingerprints},\ \text{schema versions},\ \text{semantic versions},\ \text{engine version}\big)
$$

Rebuild exactly when $h$ changes. Note that **semantic versions must be in the
hash**: changing `geography.parquet` changes every health-region roll-up, and an
artifact that does not notice is stale in a way nobody can see.

### Serve side — frontend, online, cheap

```python
aggregate("sih_rd_municipality_month",
          measures=["admissions", "deaths", "mean_los"],
          where={"period": ("2022-01", "2023-12"), "uf": "AL"},
          by=["health_region", "year", "sex"])
```

Mechanically this is: filter → pushforward along the requested $\varphi$ → merge
→ finalize. No microdata is touched. It is arithmetic on a few thousand rows.

And it **refuses**, with a reason, when: the measure is not additive along a
requested axis; $\varphi$ is partial and the caller has not accepted the lost
mass; the dimension is multi-valued and the measure counts the grain; the
requested span crosses a structural-absence boundary; a classification is
contested and no system was named.

Those refusals are the product. Anyone can write a `GROUP BY`.

### Why this is worth building at all

Measured on real data: `fetch("SIH-RD", uf="AC", years=2022)` takes **130 s** for
49,547 admissions. The same rows at municipality × month × sex are **989 cells** —
**50×** compression, and 419× at municipality alone. Acre is ~0.4% of national
SIH volume.

That ratio is also the design constraint. `DIAG_PRINC` has ~14,000 ICD codes;
putting it in the same artifact as sex × age multiplies cells by roughly $10^3$
and the artifact stops being smaller than the microdata it replaces. Hence: **one
artifact per (dataset, axis binding, dimension set)** — never one universal cube.

---

## 9. What it needs, in dependency order

| # | need | state |
|---|---|---|
| 0 | supramunicipal geography (the $\varphi$ for space) | **built** — `geography.py`, 98,584 rows in 140 KB |
| 1 | structured **grain** — components, period-bearing or not | prose only; 39 kinds to formalise |
| 2 | **measure algebra** — lift/merge/finalize, per-axis additivity, units | nothing exists |
| 3 | **`ledger.aggregation` populated** | mechanism exists, table is **empty** in this catalog (needs a `semantics` run) |
| 4 | **support mask** — available vs zero vs absent | nothing exists; `schema_presence` has the inputs |
| 5 | **spec + build + fingerprint** | nothing exists; `_resources.py` is the pattern |
| 6 | **serving verb + refusals** | nothing exists |
| 7 | **population series** for rates | table exists with stratifications and standardisability |

Items 1–2 are the real intellectual work. 0 is done. 3–7 are engineering on
existing foundations.

---

## 10. The phases, and what each must prove

**Phase 1 — grain and the algebra.** No artifact. Just the monoid types, the
per-axis additivity declaration, the grain components, and the refusals.

*Acceptance:* merging two `mean` states equals the mean of the union;
`finalize(e)` is undefined for a mean and 0 for a count; a stock measure refuses
`sum` over time; `count(establishment)` is refused on an establishment-month
grain and suggests the two honest alternatives; a median is refused or returns a
labelled approximation.

**Phase 2 — spec, build, fingerprint.** Vertical slice:
**SIH.RD → municipality × month × {sex, age band}**, measures `admissions`,
`deaths`, `los{n,sum}`, `cost_sum`, under **both** the `residence` and `facility`
bindings that `semantic_axes` already declares.

*Acceptance:* the artifact reproduces a direct `GROUP BY` on the microdata
exactly; changing `geography.parquet` invalidates the fingerprint; the support
mask marks the pre-1998 span for any dimension absent then.

**Phase 3 — serving.** `aggregate()` with filter, pushforward, merge, finalize.

*Acceptance:* municipality × year served without touching microdata; mean LOS
derived from state matches the direct computation; municipality → UF equals
direct aggregation; municipality → metropolitan region **reports the unmapped
76%** rather than silently dropping it; rolling up a contested municipality
without naming a system is refused or flagged.

**Phase 4 — break it on CNES.** `CNES.ST` is establishment-month with
semi-additive stock measures. If the abstraction assumes flows and `COUNT(rows)`
means events, it fails here — which is why it goes fourth and not last.

*Acceptance:* bed counts refuse `sum` over time and offer `mean`/`last`;
`distinct(establishment)` works over a period; nothing about the SIH slice needs
rewriting to accommodate it.

---

## 10a. The SIDRA-shaped end product `[wish, not committed]`

Recorded because it sharpens the Phase 3 acceptance test. **Not a settled plan.**

The target the project owner describes: a flat geography × time grid where each
dimension can be set to specific categories *or* to **Total** — race as
{branca, preta, parda, amarela, indígena} or aggregated; sex as {M, F} or Total.
That is SIDRA's model, and the design above already produces it without
additions.

**"Total" is `φ : K → 1`** — the pushforward to a one-point space. The same
operation as municipality → health region, with a smaller target. If `⊕` is a
commutative monoid, marginalising an axis is free and already correct. SIDRA's
flexibility is not a feature set; it is a consequence of storing monoid elements
instead of numbers.

Every dimension is then a **chain of levels** with Total at the top, and they
are all the same structure:

```
municipality -> health_region -> UF -> Brazil
month        -> year
ICD code     -> group -> chapter
single year  -> age band -> broad group
M / F / Ign  -> Total
```

`joins.yml`'s `rollup_to` relations are already the edges of these chains. One
choice of level per dimension is a **cuboid**; the set of all such choices is the
**cube lattice**; the artifact is the **base cuboid** and every other view is
derived by pushforward. A SIDRA-like UI is a lattice navigator.

### What DATASUS makes harder than IBGE, measured

* **Categories are labels, not codes.** SINASC `SEXO` has **12 codes mapping to
  3 labels** — 3 through 9 all mean "Ignorado". `RACACOR` has 11 codes including
  a junk `'0' -> Zero`; SIH `RACA` carries `'L' -> 1`, a `.CNV` artifact. An axis
  built from codes shows seven "Ignorado" rows and a category called "Zero".
* **Total must include the sentinel, or Total != sum of parts.** Showing
  {Masculino, Feminino, Total} while dropping Ignorado makes the Total exceed the
  sum and read as a bug. There are two legitimate denominators — all records, and
  records with a known value — and both must be NAMED rather than silently
  chosen. Proposed: `total` and `total_known` as explicit categories.
* **Some axes have no valid Total at all.** Multi-valued dimensions (§4.2),
  semi-additive measures over time (§3), partial geographies (§4.1).
* **The same concept differs across datasets.** SINASC `RACACOR` and SIH `RACA`
  are both race/colour with different codelists and category sets. Scope
  classifications per dataset, as SIDRA scopes them per table.

### The invariant this imposes

**Every cuboid must derive from ONE base cuboid.** Computing `sex=Total` and
`sex=M,F,Ign` independently lets them disagree — different source vintages,
different retrieval moments. Deriving all views by pushforward from one
materialised base makes internal consistency structural rather than hoped for.

It also answers which cuboids to precompute: with 50x compression measured,
**base-only, derive on demand, cache the hot ones**.

### What it adds to Phase 3's acceptance

> Can `aggregate()` produce a SIDRA-shaped table with Total on any axis, and
> refuse the axes where Total is meaningless — naming which of §1's two
> structures broke?

## 11. What I would refuse to build

* **A universal cube.** §8. Dimensionality destroys the compression that is the
  entire justification.
* **A second binding vocabulary.** `semantic_axes` exists and `FINDINGS` §3l
  records that it was kept for precisely this. A parallel one recreates the
  duplication its removal was meant to end.
* **Query-time aggregation as the normal path.** 130 s per state-year. It may
  exist as an escape hatch for an unmaterialised slice, but it must be opt-in and
  must say it is doing the expensive thing.
* **Silent roll-up of anything in §4.** A partial map, a multi-valued dimension,
  a contested membership or a semi-additive measure across the wrong axis — each
  produces a number that is wrong and looks right. That is the failure mode this
  project has spent the most time on, and the algebra above exists to make each
  one representable as a refusal instead.
