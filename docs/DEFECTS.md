# Defect catalogue — 22 August 2026

> **Status: every defect below is FIXED**, each with a regression test.
> Measured on live DATASUS, not inferred. See the summary at the foot.

Two sources, and they complement each other rather than overlap:

- **REVIEW.md** — an external static review of `src/`. Thorough on control flow.
  It could not run anything: no `pyarrow`, no network, no test execution.
- **Runtime testing** — this session, against live DATASUS with a real catalog.
  Measures what static reading cannot, and catches defects in code written after
  the review's snapshot.

Every P0 below was **re-verified by reading the current source**, because several
commits post-date the review's snapshot and a finding could already be fixed.
File:line references are to the code as it stands now.

Nothing here is fixed yet. This is the worklist.

---

## P0 — can silently return wrong or incomplete data

### P0-1 · A failed refresh falls back to the blob just judged stale
`acquire/fetcher.py:266-275` — **verified**

```python
self.fetch_many(wanted)          # return value discarded entirely
for p in wanted:
    digest = self.blobs.known_for(p)   # historical lookup, ignores this run
```

`known_for()` asks for the most recent previously successful fetch and checks
only that the file still exists on disk. It does not re-run freshness policy. So:
`_should_skip()` says stale → refresh fails → yesterday's blob is returned and
decoded as though acquisition succeeded. The code is **most willing to use stale
data exactly when its own logic said not to trust it**.

### P0-2 · Labels are not vintage-scoped, despite the docs
`api.py:653-659` — **verified**

```python
year_hint = min(years) if years else None
...
family_id=families[0]["family_id"] if len(families) == 1 else None,
year=year_hint,
```

Two failures in three lines. `load(years=range(1995, 2025))` renders **every row
with the 1995 vintage**; `years=None` renders historical rows with today's
codelist. And whenever more than one family is combined, `family_id=None` throws
away family-specific bindings, so a heterogeneous result is rendered as one
semantic context. `fetch()` does the same with `min(want_years)`.

A plausible wrong label is worse than a missing one. This is the case the whole
project exists to prevent.

### P0-3 · `load(columns=)` silently drops whole schema generations
`api.py:625-646` — **verified**

```python
errors.append(MissingColumnError(missing[0], family["family_id"], elsewhere))
continue
...
if not tables:
    if errors:
        raise errors[0]
```

`errors` is only raised when **no** family produced a table. If a later
generation has the column, the earlier generations are dropped and nothing is
said. A 1995–2025 request for a column added in 2006 returns 2006 onward and
looks like a dataset that simply starts in 2006.

The docstring at `api.py:570` promises the opposite: "A requested column that
does not exist in the target generation **raises**".

### P0-4 · `load()` has no file-axis guard
`retrieve.py:189` vs `api.py` — **verified**

`_check_axes`/`FilterHasNoAxis` appear only in `retrieve.py`. `api.py` never
references them. So `load(uf="AC")` against a national dataset filters a Hive
partition that does not exist and returns a false empty — the precise failure
`fetch()` was written to prevent. `Builder` writes non-axes as `uf=NA`/`year=0`
and `Lake.read()` applies the predicate blindly.

### P0-5 · Two incompatible dataset resolvers
`api.py:294-317` vs `retrieve.py::_families()` — **verified**

`_resolve_family()` uses exact `series = ?` SQL. `retrieve._families()` resolves
through the ontology, with a comment explaining, with measurements, why exact
matching is wrong. `load()` and `describe()` use the SQL one; `fetch()` uses the
ontology one. `DuckLake.register_all()` groups by raw `(system, series)`.

Confirmed at runtime: `load("CNES", "ST")` raised
`KeyError: no family found for system='CNES' series='ST'` on a catalog holding 35
CNES families.

For a package whose central abstraction is "one logical dataset despite unstable
filenames", there must be exactly one resolver.

### P0-6 · Partition replacement destroys before it writes
`persist/lake.py:113-118` — **verified**

```python
if replace:
    self._clear_partition(...)   # unlinks parquet AND deletes catalog rows
directory.mkdir(parents=True, exist_ok=True)
pq.write_table(table, target, ...)
```

Disk full, interrupt, or an Arrow raise between those lines leaves the partition
gone. If the write succeeds but the catalog update fails, the file exists without
metadata — and `ds.dataset()` globs the directory, so analytical state and
catalog state diverge silently.

---

## P0/P1 found only at runtime — the review could not see these

### R-1 · The shipped label pack costs 1.3 GB of RAM
`labelpack.py::_index()` — **measured**

```
baseline python              18 MB
after import pegasus_data    42 MB
after loading label pack   1309 MB   (9.2s, 2,238 codelists, 2,418,300 runs)
```

`_index()` materialises 2.4M runs as Python tuples in a dict. That is the ~1.3 GB
floor under **every** labelled fetch, whatever the result size — a 15,810-row
CNES-ST fetch peaks at 1,408 MB. The parquet is 19.8 MB on disk; the Python
object graph is ~66× that.

Mine, written this session, after the review's snapshot. Fix: keep it as an Arrow
table and slice by codelist, rather than exploding it into Python objects.

### R-2 · The documentation layer never loads on a fresh install
`retrieve.py::_ensure_reference_tables()` — **measured**

`pipeline.curate()` does not exist — `Pipeline` has no such method. I wrapped the
call in `try/except` and turned the `AttributeError` into a warning nobody reads:

```
could not load the shipped curation: 'Pipeline' object has no attribute 'curate'
```

Result: on a fresh root `variable_docs` and `dataset_docs` are both **0**, so
`info()` returns a dataset with no `what_one_row_is` and `describe()` has nothing
to describe — even though the YAML ships in the wheel. The real entry point is
`semantics.curation.load_curation`.

Mine, this session. The `except` that hid it is its own lesson.

### R-3 · Four of ten public functions reject `root=`

| function | `root=` | `settings=` |
|---|---|---|
| `fetch` `explore` `info` `translate` `availability` `compendium` | yes | yes |
| **`describe` `search` `export` `load`** | **no** | **no** |

`search(path, query)` takes a *filesystem path* as its first argument — an
entirely different calling convention from every neighbour. A user who has been
passing `root=` everywhere hits `TypeError` on a quarter of the surface.

### R-4 · `export()` does not match its own documentation
README documents `export(system, series, *, format=...)` with an `out=` argument.
The real signature takes `path=`. `export(out=...)` raises `TypeError`.

### R-5 · A cold fetch of 12 files costs 282s and 85 MB
**measured** — this is REVIEW's HI-14, with numbers

```
fresh:  fetch CNES-ST AC 2023     282.3s   peak_rss 1408MB   disk +85.2MB
warm:   same query                  8.4s                     disk  +0.0MB
```

12 files, **0.7 MB downloaded**. The 85 MB is the catalog: 80,515 file rows, the
whole CNES tree. The 282s is crawl + inventory + a schema census over **271
strata across all 13 CNES datasets** to serve one.

Gratuitous twice over: the package already ships `tree.parquet` with all 207,251
paths, so it crawled what it was already carrying; and it censused 13 datasets to
answer about one.

Confirmed again with a second system on the same root: `fetch("SIM-DO")` on a
catalog already holding CNES took **207s** and set `discovered=True`.

### R-6 · `translate()` ignores the shipped label pack
```
TranslationImpossible: the catalog holds no codelists, so nothing can be
labelled. `pegasus-data unpack <bundle>` fills ...
```
Raised on a root where `fetch(labels=True)` labels 115 columns successfully.
`translate()` checks the catalog dictionary and never consults the pack, so it
tells the user to go and download something they already have.

### R-7 · An unknown dataset takes 18.3s to be refused
`fetch("CNES-ZZ")` → `DatasetUnknown` after 18.3s. The name is not in the
ontology and cannot become valid; this should be immediate.

---

## Measurements, for reference

```
explore()                          0.7s     130MB
explore('CNES')                    1.2s     167MB
info('CNES.ST')                    0.7s     153MB
availability('CNES-ST')            0.2s     149MB
compendium()                       0.8s    1087MB

fetch CNES-ST AC 2023 (cold)     282.3s    1408MB   +85.2MB disk
fetch CNES-ST AC 2023 (warm)       8.4s    1327MB
fetch CNES-ST AC+AL+AM 2023       42.8s    1475MB
fetch CNES-PF AC 2023             44.8s    1499MB   241,636 rows
fetch CNES-ST all UF 2023-01     179.1s    2411MB   387,216 rows
fetch labels=False                14.7s    1500MB
fetch columns=[3 of 212]           5.7s    1375MB
```

Two things stand out. Memory never drops below ~1.1 GB once the pack is loaded
(R-1). And `columns=[3]` at 5.7s against 14.7s for the full table shows the
projection helps but does not avoid the decode — REVIEW's HI-07.

---

## Not yet verified

The review's remaining P1/P2 findings are plausible and specific but I have not
personally confirmed them: HI-02 through HI-28 except HI-14, and all of ME-01
through ME-21. Several are strongly implied by what is confirmed here — HI-18
(whole-partition materialisation) is visible at `lake.py:111`, and HI-01
(warm fetch still opens FTP) is consistent with the 8.4s warm number.

They should be verified before being fixed, not assumed.


---

## Status

All six P0s and all seven runtime defects are fixed, on `main`, with the full
suite green (714 passing).

| id | was | now |
|---|---|---|
| P0-1 | a failed refresh served yesterday's blob | `ensure()` returns only what this run resolved; `allow_stale=` is explicit and recorded |
| P0-2 | one vintage and one binding for the whole result | rendered per `(family, year)`, row-level from the lake's own partition column |
| P0-3 | whole generations dropped in silence | raises, as its docstring already promised |
| P0-4 | `load(uf=)` on a national dataset returned a false empty | one axis policy, `retrieve.axis_refusal()`, used by both paths |
| P0-5 | two dataset resolvers that disagreed | one, through the ontology |
| P0-6 | the partition was deleted before its replacement existed | staged, validated, then swapped |
| R-1 | label pack cost 1,309 MB and 9.2 s | 132 MB, sub-second, pushed into the Parquet scan |
| R-2 | curation never loaded; `info()` had nothing | 4,298 variable docs and 132 dataset docs on first use |
| R-3 | four of ten functions rejected `root=` | all ten accept `root=` and `settings=` |
| R-5 | cold fetch 282 s / 1,408 MB for 12 files | **30 s / 287 MB** |
| R-6 | `translate()` refused, citing a bundle you already have | uses the shipped pack |
| R-7 | an unknown dataset took 18.3 s to be refused | **0.8 s**, with suggestions |

Two things the fixes turned up that were worth more than the defects:

**A curated refusal was never enforced.** `sihsus/_shared.yml` marks SEXO and
COD_IDADE "DELIBERATELY UNBOUND" — SIH's own table maps `1→Masculino`,
`2→Feminino` *and* `3→Feminino`. The refusal was prose, so once bindings were
seeded the renderer labelled from exactly the contradictory table. It is now
`code_system: none`, which the renderer honours.

**Labelled counts went down, and that is the fix working.** CNES-ST reports 83
labelled rather than 115 because the curated decisions finally apply.

What the external review raised beyond these — HI-02 through HI-28 except
HI-14, and ME-01 through ME-21 — is still open and still unverified. It should
be verified before being fixed, not assumed.
