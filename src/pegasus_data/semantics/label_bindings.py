"""Which codelist labels a column: decided once per (system, family, field).

A ``.DEF`` binds a column to every tabulation axis that mentions it: 31 tables
for SIH's ``CNES`` (the national establishment list and 27 per-state partitions
of it), 34 for ``MUNIC_RES`` (the municipality names and their rollups into
regions), 294 for PNI's ``MUNIC``. The renderer used to weigh up to twelve of
them against every file it read, and to refuse outright above twelve (124
fields). The choice could therefore differ from one file of a dataset to the
next, it was paid for on every read, and large families of columns were never
labelled at all (STATUS M1, ADR-0072).

This module makes the decision once:

- :func:`weigh` picks the table that decodes the observed codes, measured, with
  no cap. Per-state partitions of a national table are collapsed first. The
  finest grain wins ties. A table that only rolls codes up (a municipality to
  its region) is never a label, and neither is one that decodes less than half.
- :func:`compile_bindings` runs it over real files sampled from every family
  (two states where the family is partitioned by state) and stores one row per
  field in ``label_bindings``. The rows ship in the seed catalog.
- :func:`resolve` is what the renderer calls: the stored row if there is one,
  otherwise the same :func:`weigh` on the column in hand, stored for next time.

Curation outranks all of it: a curated codelist is applied without weighing,
and is recorded here with its measured coverage as ``basis='curated'`` so that
the table audits every column.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..catalog.store import Catalog, utcnow
from ..inventory.naming import UF_CODES

#: Below this share of observed codes, no candidate is the column's codelist.
TOO_WEAK = 0.5
#: Candidates within this share of the best are ties; grain decides between them.
SHARE_TIE = 0.05
#: Mapping codes to fewer than this share of distinct labels is a ROLLUP: it
#: answers a coarser question (which region) than the column asks (which place).
ROLLUP = 0.5
#: A decision is STORED only on enough evidence: every observed code decoded,
#: or at least this many distinct codes. Two small samples of an empty column,
#: or one code in two decoded, are not grounds for a permanent answer; the
#: decision then waits for a read that sees more (live compile 2026-09-28).
MIN_EVIDENCE = 5


@dataclass(frozen=True, slots=True)
class LabelBinding:
    codelists: tuple[str, ...]
    basis: str  # 'curated' | 'measured' | 'none'
    share: float | None = None
    grain: float | None = None
    observed: int = 0
    candidates: int = 0
    reason: str = ""
    sample: tuple[str, ...] = field(default_factory=tuple)

    @property
    def labels(self) -> bool:
        return bool(self.codelists) and self.basis != "none"

    @property
    def conclusive(self) -> bool:
        """Enough evidence to store: a curated or unbound answer, a complete
        decode, or a measurement over at least ``MIN_EVIDENCE`` distinct codes."""
        if self.basis == "curated" or self.reason == "no codelist is bound to this field":
            return True
        if self.labels and self.share is not None and self.share >= 1.0:
            return True
        return self.observed >= MIN_EVIDENCE


def collapse_partitions(candidates: Iterable[str]) -> list[str]:
    """Drop ``XAC``..``XTO`` when the national ``XBR`` is also a candidate.

    ``TCNESBR`` and ``TCNESAC`` are the same classification, national and one
    state's slice. Measured on Acre's file both decode everything, and the
    state slice then labels nothing in São Paulo.
    """
    names = list(dict.fromkeys(str(c).upper() for c in candidates))
    present = set(names)
    return [
        n for n in names
        if not (len(n) > 2 and n[-2:] in UF_CODES and n[-2:] != "BR" and f"{n[:-2]}BR" in present)
    ]


def _affinity(field_name: str, codelist: str) -> int:
    field_name, codelist = field_name.upper(), codelist.upper()
    squashed = field_name.replace("_", "")
    if codelist in (field_name, squashed):
        return 0
    if squashed.startswith(codelist) or codelist.startswith(squashed):
        return 1
    return 2


def weigh(
    field_name: str,
    candidates: Sequence[str],
    observed: set[str],
    load: Callable[[str], Mapping[str, str] | None],
) -> LabelBinding:
    """The candidate that decodes the observed codes, or a reasoned ``none``."""
    pool = collapse_partitions(candidates)
    if not pool:
        return LabelBinding((), "none", reason="no codelist is bound to this field")
    if not observed:
        return LabelBinding((), "none", candidates=len(pool), reason="no values were observed to measure against")
    scored: list[tuple[str, float, float]] = []
    for codelist in pool:
        lookup = load(codelist)
        if not lookup:
            continue
        hits = [lookup[v] for v in observed if v in lookup]
        share = len(hits) / len(observed)
        grain = (len(set(hits)) / len(hits)) if hits else 0.0
        scored.append((codelist, share, grain))
    if not scored:
        return LabelBinding((), "none", observed=len(observed), candidates=len(pool),
                            reason=f"none of the {len(pool)} bound tables is materialised")
    # A rollup names a group (a municipality's region), never the code, so it
    # leaves the pool before coverage is compared: a 100% region table must not
    # outrank the municipality table that decodes 75%.
    identities = [c for c in scored if c[2] >= ROLLUP]
    if not identities:
        top = max(scored, key=lambda c: c[1])
        if top[1] >= TOO_WEAK:
            return LabelBinding((), "none", share=round(top[1], 4), grain=round(top[2], 4),
                                observed=len(observed), candidates=len(pool),
                                reason=f"only rollups decode it: {top[0]!r} maps the codes to {top[2]:.0%} "
                                       "as many labels, so it names a group, not the code")
        return LabelBinding((), "none", share=round(top[1], 4), observed=len(observed), candidates=len(pool),
                            reason=f"no bound table decodes the column: the best, {top[0]!r}, "
                                   f"matches {top[1]:.0%} of {len(observed)} observed codes")
    best = max(s for _, s, _ in identities)
    if best < TOO_WEAK:
        top = max(identities, key=lambda c: c[1])
        return LabelBinding((), "none", share=round(top[1], 4), observed=len(observed), candidates=len(pool),
                            reason=f"no bound table decodes the column: the best, {top[0]!r}, "
                                   f"matches {top[1]:.0%} of {len(observed)} observed codes")
    labels = [c for c in identities if best - c[1] <= SHARE_TIE + 1e-9]
    chosen = max(labels, key=lambda c: (c[2], c[1], -_affinity(field_name, c[0]), c[0]))
    return LabelBinding((chosen[0],), "measured", share=round(chosen[1], 4), grain=round(chosen[2], 4),
                        observed=len(observed), candidates=len(pool),
                        reason=f"decodes {chosen[1]:.0%} of {len(observed)} observed codes; "
                               f"{len(pool)} tables weighed")


# ------------------------------------------------------------------ storage


def stored(store: Catalog, system: str, family_id: str, field_name: str) -> LabelBinding | None:
    try:
        rows = store.query(
            "SELECT * FROM label_bindings WHERE system=? AND family_id=? AND field_name=?",
            (system.upper(), family_id, field_name.upper()),
        )
    except Exception:  # noqa: BLE001 - a catalog older than the table has no rows
        return None
    if not rows:
        return None
    r = rows[0]
    return LabelBinding(
        tuple(json.loads(r["codelists"] or "[]")), str(r["basis"]),
        r["share"], r["grain"], int(r["observed"] or 0), int(r["candidates"] or 0),
        str(r["reason"] or ""), tuple(json.loads(r["sample"] or "[]")),
    )


def record(store: Catalog, system: str, family_id: str, field_name: str, binding: LabelBinding) -> None:
    """Persist a conclusive decision. A read-only catalog, or thin evidence,
    keeps it for this call only."""
    if store.read_only or not binding.conclusive:
        return
    store.execute(
        """
        INSERT INTO label_bindings (system, family_id, field_name, codelists, basis, share, grain,
                                    observed, candidates, reason, sample, decided_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name) DO UPDATE SET
          codelists=excluded.codelists, basis=excluded.basis, share=excluded.share,
          grain=excluded.grain, observed=excluded.observed, candidates=excluded.candidates,
          reason=excluded.reason, sample=excluded.sample, decided_at=excluded.decided_at
        """,
        (system.upper(), family_id, field_name.upper(), json.dumps(list(binding.codelists)), binding.basis,
         binding.share, binding.grain, binding.observed, binding.candidates, binding.reason,
         json.dumps(list(binding.sample)), utcnow()),
    )


def resolve(
    store: Catalog | None,
    system: str,
    family_id: str,
    field_name: str,
    candidates: Sequence[str],
    observed: set[str],
    load: Callable[[str], Mapping[str, str] | None],
) -> LabelBinding:
    """The decision for one column: stored, or weighed now and stored."""
    if store is not None and family_id:
        found = stored(store, system, family_id, field_name)
        if found is not None:
            return found
    decision = weigh(field_name, candidates, observed, load)
    if store is not None and family_id:
        record(store, system, family_id, field_name, decision)
    return decision


# ------------------------------------------------------------------ compile


def _samples(store: Catalog, family_id: str, per_family: int) -> list[dict[str, Any]]:
    """The cheapest files of a family, from as many different states as asked."""
    rows = store.query(
        """
        SELECT f.path, f.size, fa.geo_code, fa.year, fa.normalized_date, fam.system, fam.series
          FROM family_files ff
          JOIN files f ON f.path = ff.path AND f.gone_at IS NULL
          JOIN file_facts fa ON fa.path = ff.path
          JOIN families fam ON fam.family_id = ff.family_id
         WHERE ff.family_id = ? AND fa.year IS NOT NULL
         ORDER BY f.size, f.path
        """,
        (family_id,),
    )
    # The representation a read would choose (a .dbc over its .xml or .csv.zip
    # republication), then the cheapest: sampling the .xml made the read select
    # the .dbc and the exact-path filter left nothing (111 failed samples).
    from ..inventory.strata import _census_rank

    rows = sorted(rows, key=lambda r: (_census_rank(str(r["path"])), int(r["size"] or 0), str(r["path"])))
    chosen: list[dict[str, Any]] = []
    seen_geo: set[str] = set()
    for r in rows:
        geo = str(r["geo_code"] or "")
        if geo in seen_geo:
            continue
        seen_geo.add(geo)
        chosen.append(dict(r))
        if len(chosen) >= per_family:
            break
    return chosen


def compile_bindings(
    settings: Any,
    *,
    systems: Sequence[str] | None = None,
    per_family: int = 2,
    max_bytes_per_file: int = 60_000_000,
    resume: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Sample every family's files, weigh every bound field, store the decisions.

    Values come from :func:`~pegasus_data.retrieve.fetch` with ``labels=False``:
    the same decode and normalisation a read performs, so the decision is made on
    the codes the renderer will see (normalised municipality codes, trimmed
    strings). Curated fields are recorded as ``curated`` with their measured
    coverage; they are never re-decided.
    """
    import pyarrow.compute as pc

    from ..retrieve import fetch
    from ..semantics.curation import load_variable_docs
    from ..view import _bindings, _single_lookup, compose_key

    counts = {"families": 0, "fields": 0, "measured": 0, "curated": 0, "none": 0, "deferred": 0,
              "files": 0, "failed": 0}
    # The plan is read first and the catalog released: `fetch` opens the same
    # catalog to write, and a connection held open across it made every sample
    # wait out the lock timeout (the first compile, 2026-09-28).
    planner = Catalog(settings.catalog_path, read_only=True)
    try:
        where = "WHERE system IN ({})".format(",".join("?" * len(systems))) if systems else ""
        plan = [
            (str(f["family_id"]), str(f["system"]), str(f["series"] or ""),
             [s for s in _samples(planner, str(f["family_id"]), per_family)
              if int(s["size"] or 0) <= max_bytes_per_file])
            for f in planner.query(
                f"SELECT family_id, system, series FROM families {where} ORDER BY system, family_id",
                tuple(x.upper() for x in systems or ()),
            )
        ]
    finally:
        planner.close()

    done: set[str] = set()
    if resume:
        reader = Catalog(settings.catalog_path, read_only=True)
        try:
            done = {str(r["family_id"]) for r in reader.query("SELECT DISTINCT family_id FROM label_bindings")}
        except Exception:  # noqa: BLE001 - no table yet, nothing done
            done = set()
        finally:
            reader.close()
    for family_id, system, series, samples in plan:
        if not samples or family_id in done:
            continue
        observed: dict[str, Counter[str]] = {}
        used: list[str] = []
        for sample in samples:
            month = int(sample["normalized_date"] or 0) % 100
            if on_progress:
                on_progress(f"{family_id}: {sample['path']}")
            try:
                table = fetch(
                    system, series=series or None, uf=sample["geo_code"] or None,
                    years=[int(sample["year"])], months=[month] if month else None,
                    labels=False, provenance=True, settings=settings, max_bytes=None,
                    on_missing_column="null_fill", _only_paths=[str(sample["path"])],
                )
            except Exception as exc:  # noqa: BLE001 - one bad sample is not the compile
                counts["failed"] += 1
                if on_progress:
                    on_progress(f"  failed: {type(exc).__name__}: {exc}"[:300])
                continue
            if "_source_path" in table.column_names:
                table = table.filter(pc.equal(table.column("_source_path"), sample["path"]))
            counts["files"] += 1
            used.append(str(sample["path"]))
            key_docs = _keyed_docs(settings, system)
            for name in table.column_names:
                if name.startswith("_"):
                    continue
                # Row counts, not only distinct values: the form-dictionary rung
                # is judged on rows (ADR-0080). A column with a curated composite
                # key is measured on the key, as it is looked up (ADR-0088).
                key = key_docs.get(name.upper())
                values_array = table.column(name).combine_chunks()
                composed = compose_key(table, key) if key else None
                if composed is not None:
                    values_array = composed
                tally = pc.value_counts(values_array).to_pylist()
                bucket = observed.setdefault(name.upper(), Counter())
                for item in tally:
                    value = item["values"]
                    if value is not None and str(value).strip():
                        bucket[str(value).strip()] += int(item["counts"])
        if not used:
            continue
        counts["families"] += 1
        year = int(samples[0]["year"])
        store = Catalog(settings.catalog_path)
        try:
            candidates_by_field = _bindings(store, system, family_id)
            docs = load_variable_docs(store, system)
            from .curation import harvested_codelist

            series = str(series or "").upper()
            for name, values in observed.items():
                candidates = candidates_by_field.get(name) or []
                doc = docs.get(name)
                if not (candidates or getattr(doc, "codelist", None)
                        or harvested_codelist(system, series, name)):
                    continue

                def load(codelist: str, _year: int = year, _system: str = system) -> Mapping[str, str] | None:
                    return _single_lookup(settings.lake_dir, codelist, _system, _year, None)

                decision = decide(
                    system=system, family_id=family_id, series=series, field_name=name,
                    doc=doc, candidates=candidates, counts=values, load=load,
                    store=store, use_stored=False,
                )
                if decision.basis == "curated" and decision.share is None and values:
                    # A curated decision is recorded with its measured coverage.
                    merged: dict[str, str] = {}
                    for codelist in decision.codelists:
                        merged.update({k: v for k, v in (load(codelist) or {}).items() if k not in merged})
                    total = sum(values.values())
                    hits = [merged[v] for v in values if v in merged]
                    decision = LabelBinding(**{
                        **_as_dict(decision),
                        "share": round(sum(values[v] for v in values if v in merged) / total, 4),
                        "grain": round(len(set(hits)) / len(hits), 4) if hits else None,
                    })
                decision = LabelBinding(**{**_as_dict(decision), "sample": tuple(used)})
                record(store, system, family_id, name, decision)
                _record_gaps(store, system, family_id, name, decision, values, load)
                counts["fields"] += 1
                counts[decision.basis if decision.conclusive else "deferred"] += 1
        finally:
            store.close()
    return counts


@lru_cache(maxsize=32)
def _keyed_docs_cached(catalog_path: str, system: str) -> dict[str, tuple[str, ...]]:
    store = Catalog(Path(catalog_path), read_only=True)
    try:
        from .curation import load_variable_docs

        return {n: tuple(d.key) for n, d in load_variable_docs(store, system).items() if d.key}
    finally:
        store.close()


def _keyed_docs(settings: Any, system: str) -> dict[str, tuple[str, ...]]:
    """``FIELD -> key columns`` for the system's fields that declare a composite key."""
    return _keyed_docs_cached(str(settings.catalog_path), system)


def _record_gaps(
    store: Catalog,
    system: str,
    family_id: str,
    field_name: str,
    decision: LabelBinding,
    values: Mapping[str, int],
    load: Callable[[str], Mapping[str, str] | None],
) -> None:
    """Every observed code the decided tables leave untranslated (ADR-0085).

    Two kinds: ``missing``, where no table has the code, and ``opaque``, where
    the label it gets is itself a code ("05", "16eeee AP", "52 .. Junho" for a
    YYYYMM). An opaque label is not a translation, and counting it as one
    hid the problem the user saw in CNES.
    """
    store.execute(
        "DELETE FROM label_gaps WHERE system = ? AND family_id = ? AND field_name = ?",
        (system, family_id, field_name),
    )
    if not decision.codelists or not values:
        return
    labels: dict[str, str] = {}
    for codelist in decision.codelists:
        for code, label in (load(codelist) or {}).items():
            labels.setdefault(code, label)
    rows = []
    now = utcnow()
    joined = ",".join(decision.codelists)
    for code, n in values.items():
        label = labels.get(code)
        if label is None:
            rows.append((system, family_id, field_name, code, n, joined, now, "missing", None))
        elif is_opaque(code, label):
            rows.append((system, family_id, field_name, code, n, joined, now, "opaque", label))
    if rows:
        store.executemany(
            "INSERT OR REPLACE INTO label_gaps (system, family_id, field_name, code, row_count, codelists, "
            "measured_at, kind, label) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )


_WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
_REPEATED = re.compile(r"^(.)\1+$")


def is_opaque(code: str, label: str) -> bool:
    """A label that does not say what the code means.

    It has no real word left once the code and any placeholder runs
    ("eeee", "xxx") are removed: "05", "A1", "16eeee", "201 .. 202". A label
    whose words are there ("Ignorado", "16eeee AP - gestão estadual Amapá")
    is meaningful, though the second is also noisy.
    """
    text = label.strip()
    if not text:
        return True
    words = [w for w in _WORD.findall(text) if not _REPEATED.match(w.lower())]
    plain_code = "".join(ch for ch in code if ch.isalnum()).upper()
    words = [w for w in words if w.upper() != plain_code]
    return not words


def _as_dict(binding: LabelBinding) -> dict[str, Any]:
    return {k: getattr(binding, k) for k in binding.__dataclass_fields__}


# ------------------------------------------------------------------ decide
#
# ONE ladder of evidence for "which table labels this column", used by the
# renderer at query time and by `compile_bindings` at build time. The two used
# to be separate implementations and drifted: ADR-0080 had to be added to
# both, and the harvested dictionaries reached only one (ADR-0082).

#: The form's own dictionary is taken when it decodes this share of the ROWS.
FORM_DICTIONARY_ROWS = 0.95


def candidates_for(doc: object, candidates: Sequence[str]) -> list[str]:
    """The pool weighed for a column: bound tables, plus a per-form curated list."""
    if doc is not None and getattr(doc, "per_form", False) and getattr(doc, "codelist", None):
        return list(dict.fromkeys([doc.codelist, *doc.codelists, *candidates]))  # type: ignore[attr-defined]
    return list(candidates)


def decide(
    *,
    system: str,
    family_id: str,
    series: str,
    field_name: str,
    doc: object,
    candidates: Sequence[str],
    counts: Mapping[str, int],
    load: Callable[[str], Mapping[str, str] | None],
    store: Catalog | None = None,
    vintage: int | None = None,
    use_stored: bool = True,
) -> LabelBinding:
    """The label decision for one column of one family, best evidence first.

    1. ``codes:`` written in the curation for this column (ADR-0079);
    2. the family's own form dictionary, when it decodes >= 95% of the ROWS
       (ADR-0080: rare undocumented codes must not discard it);
    3. a curated ``codelist:``, unless it lists per-form alternatives;
    4. a reviewed adjudication (store only);
    5. the stored decision (store and ``use_stored`` only);
    6. measured weighing of the candidate pool.
    """
    from .curation import harvested_codelist, inline_codelist

    observed = {str(k) for k in counts}
    total = sum(counts.values())
    if doc is not None and getattr(doc, "codes", None):
        # The column's own table first; a table it was also bound to stays as
        # the fallback (ADR-0079). Returning the inline table alone left
        # PA_UFDIF's 0/1 undecoded once its measured 9 was written (ADR-0105).
        chain = (str(doc.codelist), *(str(c) for c in getattr(doc, "codelists", None) or ()))  # type: ignore[attr-defined]
        return LabelBinding(chain, "curated", observed=len(observed), candidates=len(chain),
                            reason="inline code table in the curation")
    if series:
        harvested = harvested_codelist(system, series, field_name)
        if harvested:
            table = inline_codelist(harvested) or {}
            covered = sum(n for v, n in counts.items() if v in table)
            if not total or covered >= FORM_DICTIONARY_ROWS * total:
                return LabelBinding(
                    (harvested,), "curated",
                    share=round(covered / total, 4) if total else None,
                    observed=len(observed), reason="the form's own data dictionary",
                )
    if doc is not None and getattr(doc, "codelist", None) and not getattr(doc, "per_form", False):
        curated = (str(doc.codelist), *(str(c) for c in doc.codelists))  # type: ignore[attr-defined]
        return LabelBinding(curated, "curated", observed=len(observed), candidates=len(curated),
                            reason="declared in curation")
    if store is not None:
        try:
            from .relations import RelationType, relations_for

            artifacts = sorted({
                item.artifact
                for item in relations_for(
                    system, f"{system}.{series}" if family_id else "*", field_name,
                    relation_type=RelationType.LABEL_OF, catalog=store,
                    # An adjudication with a validity window decides ONE era.
                    vintage=vintage,
                )
            })
            if len(artifacts) == 1:
                return LabelBinding((artifacts[0],), "curated", reason="reviewed adjudication")
        except Exception:  # noqa: BLE001 - old/read-only catalogs keep safe behaviour
            pass
    pool = candidates_for(doc, candidates)
    if use_stored and store is not None and family_id:
        found = stored(store, system, family_id, field_name)
        if found is not None:
            return found
    decision = weigh(field_name, pool, observed, load)
    if use_stored and store is not None and family_id:
        record(store, system, family_id, field_name, decision)
    return decision
