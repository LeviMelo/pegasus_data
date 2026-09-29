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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
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
    from ..view import _bindings, _single_lookup

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
        observed: dict[str, set[str]] = {}
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
            for name in table.column_names:
                if name.startswith("_"):
                    continue
                values = pc.unique(table.column(name).combine_chunks()).to_pylist()
                bucket = observed.setdefault(name.upper(), set())
                bucket.update(str(v).strip() for v in values if v is not None and str(v).strip())
        if not used:
            continue
        counts["families"] += 1
        year = int(samples[0]["year"])
        store = Catalog(settings.catalog_path)
        try:
            candidates_by_field = _bindings(store, system, family_id)
            docs = load_variable_docs(store, system)
            for name, values in observed.items():
                candidates = candidates_by_field.get(name) or []
                doc = docs.get(name)
                curated = [doc.codelist, *doc.codelists] if doc is not None and getattr(doc, "codelist", None) else []
                if not candidates and not curated:
                    continue

                def load(codelist: str, _year: int = year, _system: str = system) -> Mapping[str, str] | None:
                    return _single_lookup(settings.lake_dir, codelist, _system, _year, None)

                if curated:
                    merged: dict[str, str] = {}
                    for codelist in curated:
                        merged.update({k: v for k, v in (load(codelist) or {}).items() if k not in merged})
                    hits = [merged[v] for v in values if v in merged]
                    decision = LabelBinding(
                        tuple(curated), "curated",
                        share=round(len(hits) / len(values), 4) if values else None,
                        grain=round(len(set(hits)) / len(hits), 4) if hits else None,
                        observed=len(values), candidates=len(curated),
                        reason="declared in curation", sample=tuple(used),
                    )
                else:
                    decision = weigh(name, candidates, values, load)
                    decision = LabelBinding(**{**_as_dict(decision), "sample": tuple(used)})
                record(store, system, family_id, name, decision)
                counts["fields"] += 1
                counts[decision.basis if decision.conclusive else "deferred"] += 1
        finally:
            store.close()
    return counts


def _as_dict(binding: LabelBinding) -> dict[str, Any]:
    return {k: getattr(binding, k) for k in binding.__dataclass_fields__}
