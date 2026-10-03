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

from ..semantics.curation import read_yaml
from .engine import LINKS_FILE, load_links
from .identity import connect
from .store import links_dir, run_key

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
    raw = read_yaml(LINKS_FILE).get("links") or {}
    out = {}
    for name, spec in load_links().items():
        person = (raw.get(name) or {}).get("person")
        if person:
            out[name] = (spec.left.dataset, str(person[0]), spec.right.dataset, str(person[1]))
    return out


def _stored_edges(settings: Any, period: object, geography: object, method: str) -> pa.Table:
    """Every stored pair of the scope as one edge table."""
    con = connect()
    parts = []
    for name, (lds, lrole, rds, rrole) in _person_of_specs().items():
        key = run_key(name, method, period, geography)
        path = links_dir(settings) / name / f"{key.stem}.parquet"
        if not path.exists():
            continue
        parts.append(f"""SELECT '{name}' AS spec, '{lds}' AS lds, '{lrole}' AS lrole, l,
                                 '{rds}' AS rds, '{rrole}' AS rrole, r, bits FROM '{path.as_posix()}'""")
    if not parts:
        raise FileNotFoundError("no stored links for this scope: run link() first")
    return con.execute(" UNION ALL ".join(parts) + " ORDER BY bits DESC").fetch_arrow_table()


def build_entities(*, period: object, geography: object, method: str = "probabilistic",
                   settings: Any = None) -> Entities:
    """Merge every stored link of the scope into persons, strongest evidence first."""
    from ..config import load_settings

    settings = settings or load_settings()
    edges = _stored_edges(settings, period, geography, method)
    spec = edges.column("spec").to_pylist()
    lnode = [f"{d}|{r}|{x}" for d, r, x in zip(edges.column("lds").to_pylist(), edges.column("lrole").to_pylist(),
                                                edges.column("l").to_pylist(), strict=True)]
    rnode = [f"{d}|{r}|{x}" for d, r, x in zip(edges.column("rds").to_pylist(), edges.column("rrole").to_pylist(),
                                                edges.column("r").to_pylist(), strict=True)]
    bits = edges.column("bits").to_numpy()
    index: dict[str, int] = {}
    for name in lnode + rnode:
        index.setdefault(name, len(index))
    parent = np.arange(len(index))
    # Per root: how many nodes of each kind it holds.
    kinds: list[Counter] = []
    for name in index:
        ds, role, _ = name.split("|", 2)
        kinds.append(Counter({(ds, role): 1}))

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    kept = 0
    refused: list[dict[str, Any]] = []
    by_spec: dict[str, dict[str, int]] = {}
    for i in range(len(spec)):
        a, b = find(index[lnode[i]]), find(index[rnode[i]])
        stats = by_spec.setdefault(spec[i], {"edges": 0, "kept": 0, "already_one_person": 0, "refused": 0})
        stats["edges"] += 1
        if a == b:
            stats["already_one_person"] += 1
            continue
        merged = kinds[a] + kinds[b]
        broken = [k for k in AT_MOST_ONE if merged[k] > 1]
        if all(merged[k] for k in EXCLUSIVE):
            broken.append(EXCLUSIVE)
        if broken:
            stats["refused"] += 1
            refused.append({"spec": spec[i], "left": lnode[i], "right": rnode[i], "bits": float(bits[i]),
                            "would_break": [str(k) for k in broken]})
            continue
        if kinds[a].total() < kinds[b].total():
            a, b = b, a
        parent[b] = a
        kinds[a] = merged
        kinds[b] = Counter()
        kept += 1
        stats["kept"] += 1
    names = list(index)
    persons = [int(find(i)) for i in range(len(names))]
    parts = [n.split("|", 2) for n in names]
    nodes = pa.table({
        "record": pa.array([p[2] for p in parts], pa.string()),
        "dataset": pa.array([p[0] for p in parts], pa.string()),
        "role": pa.array([p[1] for p in parts], pa.string()),
        "person": pa.array(persons, pa.int64()),
    })
    return Entities(nodes, kept, refused, by_spec)


def person_pairs(entities: Entities, left: tuple[str, str], right: tuple[str, str]) -> pa.Table:
    """Every (left record, right record) of one person, for two (dataset, role) kinds.

    The links a spec would draw, plus those implied through other links.
    """
    con = connect()
    con.register("n", entities.nodes)
    return con.execute(f"""SELECT a.record AS l, b.record AS r, a.person FROM n a JOIN n b USING (person)
        WHERE a.dataset = '{left[0]}' AND a.role = '{left[1]}' AND b.dataset = '{right[0]}' AND b.role = '{right[1]}'
    """).fetch_arrow_table()


__all__ = ["Entities", "build_entities", "person_pairs"]
