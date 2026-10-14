"""Entities: stored links merged into persons (docs/plans/linkage-theory.md §3.3).

Every link spec says which person its two records are about (``person:`` in
``curation/links.yml``: a delivery's *mother* is the admission's *patient*).
A record observes one or more persons (a birth declaration observes a baby and
a mother), so the nodes here are ``(record, person role)``, and a stored pair
is an edge saying two nodes are one person.

Edges are merged strongest first (descending evidence, bits) into persons,
under the constraints a person obeys:

- at most one birth record as the baby, and at most one death certificate;
- never the baby and the mother of a birth at once.

An edge whose merge would break a constraint is refused and reported, not
forced: the weaker evidence yields. Records then belong to persons, and any
two records of one person are linked whether or not a spec joined them
directly. Two routes to the same pair agreeing or not (triangles) measure the
links against each other.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute  # noqa: F401 - pa.compute

from ..semantics.curation import read_yaml
from .engine import link_method, links_file, load_links, stored_key
from .identity import connect
from .store import load

#: How many records of one kind a person can have. A kind is (dataset, role).
AT_MOST_ONE = {("SINASC-DN", "baby"), ("SIM-DO", "deceased")}
#: Roles one person cannot hold together in the same dataset.
EXCLUSIVE = (("SINASC-DN", "baby"), ("SINASC-DN", "mother"))


@dataclass
class Entities:
    nodes: pa.Table                      # record, dataset, role, person
    edges_kept: int = 0
    edges_refused: list[dict[str, Any]] = field(default_factory=list)
    by_spec: dict[str, dict[str, int]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        sizes = Counter(Counter(self.nodes.column("person").to_pylist()).values())
        return {
            "nodes": self.nodes.num_rows,
            "persons": int(sum(sizes.values())),
            "persons_by_records": dict(sorted(sizes.items())),
            "edges_kept": self.edges_kept,
            "edges_refused": len(self.edges_refused),
            "by_spec": self.by_spec,
        }


def _person_of_specs() -> dict[str, tuple[str, str, str, str]]:
    """spec -> (left dataset, left person role, right dataset, right person role)."""
    raw = read_yaml(links_file()).get("links") or {}
    out = {}
    for name, spec in load_links().items():
        person = (raw.get(name) or {}).get("person")
        if person:
            out[name] = (spec.left.dataset, str(person[0]), spec.right.dataset, str(person[1]))
    return out


#: stored edge tables by scope and the runs' signature (`_stored_edges`): one load serves every call of a scope until a
#: run, or what it depends on, changes
_EDGES: dict[tuple, pa.Table] = {}


def _signature(settings: Any, keys: list[Any]) -> str:
    """What the stored runs of a scope are as files and as current inputs: a re-run (refresh) that changes pairs
    changes the files' time and size, a rebuilt lake or role changes the fingerprint."""
    import hashlib

    from . import store

    h = hashlib.sha256()
    for key in keys:
        path = store.links_dir(settings) / key.spec / f"{key.stem}.parquet"
        stat = path.stat() if path.exists() else None
        h.update(f"{key.stem}|{stat.st_mtime_ns if stat else 0}|{stat.st_size if stat else 0}|"
                 f"{store.fingerprint(settings, key) if stat else ''};".encode())
    return h.hexdigest()


def _stored_edges(settings: Any, period: object, geography: object, method: str | None,
                  exclude: frozenset[str] = frozenset()) -> pa.Table:
    """Every stored pair of the scope's viable runs as one edge table, with its p_match (1 where the run carries none).
    A run stored with the verdict "not viable" (SINAN's dengue deaths in 2015: its controls matched like its pairs)
    merges no one. Kept in memory by the runs' signature, which the table carries (``signature`` in its metadata)."""
    runs = [(name, spec, stored_key(name, method or link_method(name), period, geography))
            for name, spec in _person_of_specs().items() if name not in exclude]
    signature = _signature(settings, [key for _n, _s, key in runs])
    memo = (str(period), str(geography), method, signature)
    if memo in _EDGES:
        return _EDGES[memo]
    con = connect()
    parts = []
    for name, (lds, lrole, rds, rrole), key in runs:
        stored = load(settings, key)               # through the store: only a current run
        if stored is None or stored[1].get("verdict") == "not viable":
            continue
        view = f"run_{len(parts)}"
        con.register(view, stored[0])
        if "bits" in stored[0].column_names:
            pm = "p_match" if "p_match" in stored[0].column_names else "1.0"
            ev = "bits"
        else:
            # a deterministic run has no evidence per pair: each pair is right with probability 1 - chance and weighs
            # log2((1 - chance) / chance) bits (`uncertainty.run_probability`); the run had failed the union for want of
            # a bits column (2026-10-11)
            from .uncertainty import run_probability

            p, b = run_probability(stored[1])
            pm, ev = repr(p), f"CAST({b!r} AS DOUBLE)"
        parts.append(f"""SELECT '{name}' AS spec, '{lds}' AS lds, '{lrole}' AS lrole, l,
                                 '{rds}' AS rds, '{rrole}' AS rrole, r, {ev} AS bits, CAST({pm} AS DOUBLE) AS p_match
                          FROM {view}""")
    if not parts:
        raise FileNotFoundError("no stored links for this scope: run link() first")
    # a total order: a draw keeps each edge by its position, and ties on bits (every pair of a deterministic run has
    # the same) came back in any order, so one draw was another link set on each call (2026-10-12)
    edges = con.execute(" UNION ALL ".join(parts) + " ORDER BY bits DESC, spec, l, r").to_arrow_table()
    edges = edges.replace_schema_metadata({b"signature": signature.encode()})
    _EDGES[memo] = edges
    while len(_EDGES) > 4:
        _EDGES.pop(next(iter(_EDGES)))
    return edges


def build_entities(*, period: object, geography: object, method: str | None = None,
                   settings: Any = None, draw: int | None = None, exclude: frozenset[str] = frozenset(),
                   seeds: tuple[str, str, Any] | None = None) -> Entities:
    """Merge every stored link of the scope into persons, strongest evidence first, each link's run by its own method
    (`link_method`) unless ``method`` names one. ``draw`` (a seed) merges one
    plausible link set: each edge kept with its p_match (`uncertainty.draws`), so an analysis over persons carries the
    linkage's uncertainty by repeating it over draws and combining (`uncertainty.combine`). ``exclude`` leaves links
    out (`triangles`: the persons the other links make). ``seeds`` (dataset, role, record ids) merges only the link
    graph's components that hold those records: components never interact, so their persons are exactly those of the
    whole merge (a cohort of 2,000 notifications needs not the year's 500,000 deaths-to-admissions pairs)."""
    from ..config import load_settings

    settings = settings or load_settings()
    edges = _stored_edges(settings, period, geography, method, exclude)
    keep = None
    if seeds is not None and edges.num_rows:
        # the seeds' components of the undrawn graph, once per scope and cohort: a draw only removes edges, so its
        # seeded components lie inside them (a cohort's ten draws had each rebuilt them over 552,219 edges, 2026-10-12).
        # Keyed by the runs' signature, not by the edges' number: a re-run that changes pairs but not their count
        # served the old graph's components for the new edges.
        key = (str(period), str(geography), method, tuple(sorted(exclude)), (edges.schema.metadata or {}).get(b"signature"),
               _seeds_digest(seeds))
        keep = _SEEDED.get(key)
        if keep is None:
            keep = _SEEDED[key] = _component_mask(edges, seeds)
            while len(_SEEDED) > 16:
                _SEEDED.pop(next(iter(_SEEDED)))
    if draw is not None:
        p = edges.column("p_match").to_numpy(zero_copy_only=False)
        import zlib

        rng = np.random.default_rng([int(draw), zlib.crc32(str(period).encode())])     # reproducible across processes
        drawn = rng.random(len(p)) < p      # over the whole set: each edge keeps its own draw, seeded or not
        edges = edges.filter(pa.array(drawn if keep is None else drawn & keep))
        if keep is not None and edges.num_rows:
            edges = edges.filter(pa.array(_component_mask(edges, seeds)))   # the draw may split a seed's component
    elif keep is not None:
        edges = edges.filter(pa.array(keep))
    return _merge(edges)


def _merge(edges: pa.Table) -> Entities:
    """Persons from an edge table (strongest first). Edges are merged in their order under the constraints of a person
    (`AT_MOST_ONE`, `EXCLUSIVE`), but only where a constraint can bind: the link graph's connected components never
    interact, and a component with no two nodes of an at-most-one kind and no exclusive pair can refuse nothing, so its
    edges all merge, and which of them are kept (the others re-state a merge already made) is its minimum spanning
    forest under the edge order. Those are found in C (scipy); the order-dependent union-find runs over the few
    components that can refuse (about 3% of edges), where it took 97 s over 2.4 M edges before."""
    import pyarrow.compute as pc
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components, minimum_spanning_tree

    m = edges.num_rows
    if not m:
        return Entities(pa.table({"record": pa.array([], pa.string()), "dataset": pa.array([], pa.string()),
                                  "role": pa.array([], pa.string()), "person": pa.array([], pa.int64())}))

    def names(side: str) -> pa.Array:
        cols = [edges.column(f"{side}ds"), edges.column(f"{side}role"), edges.column(side)]
        return pc.binary_join_element_wise(*[pc.cast(c, pa.string()) for c in cols], "|").combine_chunks()

    def kinds(side: str) -> pa.Array:
        return pc.binary_join_element_wise(pc.cast(edges.column(f"{side}ds"), pa.string()),
                                           pc.cast(edges.column(f"{side}role"), pa.string()), "|").combine_chunks()

    enc = pc.dictionary_encode(pa.concat_arrays([names("l"), names("r")]))
    idx = enc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    li, ri = idx[:m], idx[m:]
    n = len(enc.dictionary)
    kenc = pc.dictionary_encode(pa.concat_arrays([kinds("l"), kinds("r")]))
    kidx = kenc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    kind_names = kenc.dictionary.to_pylist()
    kind_of = np.full(n, -1, np.int64)
    kind_of[li], kind_of[ri] = kidx[:m], kidx[m:]
    kind_id = {name: i for i, name in enumerate(kind_names)}
    ncomp, label = connected_components(coo_matrix((np.ones(m), (li, ri)), shape=(n, n)), directed=False)

    # components that hold two nodes of an at-most-one kind, or every kind of the exclusive set
    constrained = np.zeros(ncomp, bool)
    for ds, role in AT_MOST_ONE:
        k = kind_id.get(f"{ds}|{role}")
        if k is not None:
            constrained |= np.bincount(label[kind_of == k], minlength=ncomp) >= 2
    exclusive = [kind_id.get(f"{ds}|{role}") for ds, role in EXCLUSIVE]
    if all(k is not None for k in exclusive):
        both = np.ones(ncomp, bool)
        for k in exclusive:
            both &= np.bincount(label[kind_of == k], minlength=ncomp) > 0
        constrained |= both
    tied = constrained[label[li]]                     # per edge: lies in a component that can refuse

    spec_enc = pc.dictionary_encode(edges.column("spec").combine_chunks())
    spec_code = spec_enc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    spec_name = spec_enc.dictionary.to_pylist()
    kept_edge = np.zeros(m, bool)

    # unconstrained edges: the first of each node pair, kept when it is in the minimum spanning forest by position
    free = np.nonzero(~tied)[0]
    if len(free):
        lo, hi = np.minimum(li[free], ri[free]), np.maximum(li[free], ri[free])
        _, first = np.unique(lo * n + hi, return_index=True)
        cand = free[first]
        tree = minimum_spanning_tree(coo_matrix((cand + 1.0, (np.minimum(li[cand], ri[cand]),
                                                              np.maximum(li[cand], ri[cand]))), shape=(n, n)).tocsr())
        kept_edge[tree.data.astype(np.int64) - 1] = True

    # constrained edges: the order-dependent union-find with the person's constraints
    parent = np.arange(n)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    held: dict[int, Counter] = {}          # per root: how many nodes of each kind it holds

    def kinds_of(root: int) -> Counter:
        if root not in held:
            held[root] = Counter({kind_names[kind_of[root]]: 1})
        return held[root]

    wanted = {f"{ds}|{role}": (ds, role) for ds, role in AT_MOST_ONE}
    bits = edges.column("bits").to_numpy()
    refused: list[dict[str, Any]] = []
    refused_edge = np.zeros(m, bool)
    for i in np.nonzero(tied)[0].tolist():
        a, b = find(int(li[i])), find(int(ri[i]))
        if a == b:
            continue
        merged = kinds_of(a) + kinds_of(b)
        broken: list[tuple[Any, ...]] = [wanted[k] for k in wanted if merged[k] > 1]
        if all(merged[f"{ds}|{role}"] for ds, role in EXCLUSIVE):
            broken.append(EXCLUSIVE)
        if broken:
            refused_edge[i] = True
            refused.append({"spec": spec_name[spec_code[i]], "left": enc.dictionary[int(li[i])].as_py(),
                            "right": enc.dictionary[int(ri[i])].as_py(), "bits": float(bits[i]),
                            "would_break": [str(k) for k in broken]})
            continue
        if kinds_of(a).total() < kinds_of(b).total():
            a, b = b, a
        parent[b] = a
        held[a] = merged
        held.pop(b, None)
        kept_edge[i] = True

    person = label.astype(np.int64)
    for node in np.nonzero(constrained[label])[0].tolist():
        person[node] = ncomp + find(node)

    by_spec: dict[str, dict[str, int]] = {}
    first_seen = np.unique(spec_code, return_index=True)
    for code in first_seen[0][np.argsort(first_seen[1])].tolist():
        mine = spec_code == code
        by_spec[spec_name[code]] = {
            "edges": int(mine.sum()), "kept": int((mine & kept_edge).sum()),
            "already_one_person": int((mine & ~kept_edge & ~refused_edge).sum()), "refused": int((mine & refused_edge).sum())}

    record = np.empty(n, dtype=object)
    record[li] = pc.cast(edges.column("l"), pa.string()).to_numpy(zero_copy_only=False)
    record[ri] = pc.cast(edges.column("r"), pa.string()).to_numpy(zero_copy_only=False)
    take = pa.array(kind_of)
    dataset = pc.take(pa.array([k.split("|", 1)[0] for k in kind_names], pa.string()), take)
    role = pc.take(pa.array([k.split("|", 1)[1] for k in kind_names], pa.string()), take)
    nodes = pa.table({"record": pa.array(record, pa.string()), "dataset": dataset, "role": role,
                      "person": pa.array(person, pa.int64())})
    return Entities(nodes, int(kept_edge.sum()), refused, by_spec)


#: the seeds' component masks of undrawn edge sets, by scope and cohort (`build_entities`)
_SEEDED: dict[tuple, np.ndarray] = {}


def _seeds_digest(seeds: tuple[str, str, Any]) -> str:
    import hashlib

    ds, role, ids = seeds
    return hashlib.sha256("|".join([ds, role, *sorted(map(str, ids))]).encode()).hexdigest()


def _component_mask(edges: pa.Table, seeds: tuple[str, str, Any]) -> np.ndarray:
    """Which edges lie in a connected component of the link graph holding a seed record (``seeds``: dataset, role,
    ids). Nodes are numbered by Arrow's dictionary encoding (a Python dictionary over 1.1 M node names took 2 s)."""
    import pyarrow.compute as pc
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    ds, role, ids = seeds

    def names(side):
        cols = [edges.column(f"{side}ds"), edges.column(f"{side}role"), edges.column(side)]
        return pc.binary_join_element_wise(*[pc.cast(c, pa.string()) for c in cols], "|").combine_chunks()

    enc = pc.dictionary_encode(pa.concat_arrays([names("l"), names("r")]))
    idx = enc.indices.to_numpy(zero_copy_only=False).astype(np.int64)
    m = edges.num_rows
    li, ri = idx[:m], idx[m:]
    n = len(enc.dictionary)
    _, label = connected_components(coo_matrix((np.ones(m), (li, ri)), shape=(n, n)), directed=False)
    at = pc.index_in(pa.array([f"{ds}|{role}|{x}" for x in ids], pa.string()), value_set=enc.dictionary)
    at = at.drop_null().to_numpy(zero_copy_only=False).astype(np.int64)
    return np.isin(label[li], np.unique(label[at]))


def person_pairs(entities: Entities, left: tuple[str, str], right: tuple[str, str]) -> pa.Table:
    """Every (left record, right record) of one person, for two (dataset, role) kinds.

    The links a spec would draw, plus those implied through other links.
    """
    con = connect()
    con.register("n", entities.nodes)
    return con.execute(f"""SELECT a.record AS l, b.record AS r, a.person FROM n a JOIN n b USING (person)
        WHERE a.dataset = '{left[0]}' AND a.role = '{left[1]}' AND b.dataset = '{right[0]}' AND b.role = '{right[1]}'
    """).to_arrow_table()


def triangles(*, period: object, geography: object, settings: Any = None,
              exclude: frozenset[str] = frozenset()) -> dict[str, dict[str, Any]]:
    """Each stored link of the scope against the persons the OTHER links make: of its pairs whose left record the other
    links also reach a right record of the same kind for, how many reach the same one (agree) and how many another
    (disagree). Two independent routes to one pair measure the links against each other, which no link's own controls
    can (2026-10-02: 3,085 newborn triangles agreed, 76 did not, 97.6 %). A link with no other route has none.
    ``exclude`` leaves links out, as `build_entities` does."""
    from ..config import load_settings

    settings = settings or load_settings()
    edges = _stored_edges(settings, period, geography, None, exclude)       # loaded once for every spec
    out: dict[str, dict[str, Any]] = {}
    con = connect()
    for name, (lds, lrole, rds, rrole) in _person_of_specs().items():
        mask = pa.compute.equal(edges.column("spec"), name)
        direct = edges.filter(mask).select(["l", "r"])
        if direct.num_rows == 0:
            continue
        rest = edges.filter(pa.compute.invert(mask))
        if rest.num_rows == 0:
            out[name] = {"pairs": direct.num_rows, "with_route": 0, "agree": 0, "disagree": 0, "agreement": None}
            continue
        others = _merge(rest)
        routed = person_pairs(others, (lds, lrole), (rds, rrole))
        con.register("d", pa.table({"l": _as_str(direct.column("l")), "r": _as_str(direct.column("r"))}))
        con.register("o", pa.table({"l": _as_str(routed.column("l")), "r": _as_str(routed.column("r"))}))
        row = con.execute("""SELECT count(*) FILTER (WHERE agree) AS agree, count(*) FILTER (WHERE NOT agree) AS disagree
            FROM (SELECT d.l, bool_or(o.r = d.r) AS agree FROM d JOIN o USING (l) GROUP BY d.l, d.r)""").fetchone()
        con.unregister("d")
        con.unregister("o")
        agree, disagree = int(row[0]), int(row[1])
        out[name] = {"pairs": direct.num_rows, "with_route": agree + disagree, "agree": agree, "disagree": disagree,
                     "agreement": round(agree / (agree + disagree), 4) if agree + disagree else None}
    return out


def _as_str(column: Any) -> pa.Array:
    """A record identity column as strings (stored runs and persons name records alike)."""
    return pa.compute.cast(column, pa.string())


__all__ = ["Entities", "build_entities", "person_pairs", "triangles"]
