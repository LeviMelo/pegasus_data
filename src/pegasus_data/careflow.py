"""What a care-flow graph says about places: self-sufficiency, catchments, communities, health regions.

The input is the table :func:`pegasus_data.proximity.care_flows` returns: edges ``from``, ``to``,
``weight`` (events), ``vintage`` and ``share``, with any further column (a ``by`` classifier) a
group of its own, except the state of a ``measure`` (``<role>_n``, ``<role>_sum``), which rides along on the edges and
is neither a group nor read here. Everything here is computed per vintage and group, from the edges alone.

* :func:`care_flow_profile`: per municipality, the events of its residents, the share treated at
  home (self-sufficiency), the events it treats, the share of those that come from elsewhere
  (importation), its main destination.
* :func:`care_flow_catchments`: nodal regions by dominant flow: each municipality follows the
  destination that takes most of its events until it reaches a municipality whose own largest
  destination is itself (a hub); a cycle between two or more is settled on the one that treats most.
* :func:`care_flow_communities`: directed-modularity communities (Leiden) of the flow graph. The
  null model is the flow expected from each place's out- and in-strength, so a community is a set
  of places whose patients use one another's hospitals more than their sizes explain. The resolution
  is a knob, and it decides how many communities there are: report it with any result.
* :func:`compare_flow_regions`: the communities against an official regionalisation (current health
  regions, health macro-regions, ...) from the shipped membership pack: agreement (ARI, NMI) and
  how much of the flow leaving a municipality each partition keeps inside a unit.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import pyarrow as pa

_FIXED = ("from", "to", "weight", "kind", "vintage", "share")


def _group_columns(flows: pa.Table) -> list[str]:
    """The columns of a flow table that are groups: a ``by`` classifier (a source column, never with a dot). Not the fixed
    columns and not a measure's state, which ``care_flows(measure=)`` names ``<entity>.<property>_n`` and ``_sum`` after
    the role (a role has a dot): a quantity summed on the edges, which no function here groups by."""
    return [c for c in flows.column_names if c not in _FIXED and "." not in c]


def _groups(flows: pa.Table) -> tuple[list[str], list[tuple[tuple, dict[tuple[str, str], int]]]]:
    """The group columns of a flow table and, per (vintage, group value), its ``(from, to) -> weight``."""
    extra = _group_columns(flows)
    columns = {c: flows.column(c).to_pylist() for c in ("vintage", "from", "to", "weight", *extra)}
    grouped: dict[tuple, dict[tuple[str, str], int]] = defaultdict(dict)
    for i in range(flows.num_rows):
        key = (columns["vintage"][i], *(columns[c][i] for c in extra))
        edges = grouped[key]
        edge = (columns["from"][i], columns["to"][i])
        edges[edge] = edges.get(edge, 0) + columns["weight"][i]
    return extra, sorted(grouped.items(), key=lambda kv: tuple(str(x) for x in kv[0]))


def _table(rows: list[dict[str, Any]], names: list[str]) -> pa.Table:
    return pa.table({n: [r[n] for r in rows] for n in names})


def care_flow_profile(flows: pa.Table) -> pa.Table:
    """Per vintage (and group) and municipality: who its residents use, and who uses its facilities.

    * ``resident_events``: events of its residents, wherever treated.
    * ``treated_at_home`` and ``self_sufficiency``: those treated in the municipality, and their share.
    * ``events_treated``: events that happened in it (``imported``: those of non-residents,
      ``import_share``: their share). ``net_flow`` is ``events_treated - resident_events``.
    * ``destinations``: how many municipalities treated its residents.
    * ``main_destination`` and ``main_destination_share``: the one that treated most (itself included).
    """
    extra, groups = _groups(flows)
    rows = []
    for key, edges in groups:
        out: dict[str, int] = defaultdict(int)
        into: dict[str, int] = defaultdict(int)
        best: dict[str, tuple[int, str]] = {}
        count: dict[str, int] = defaultdict(int)
        for (u, v), w in edges.items():
            out[u] += w
            into[v] += w
            count[u] += 1
            if u not in best or (w, -int(v)) > (best[u][0], -int(best[u][1])):
                best[u] = (w, v)
        for m in sorted(set(out) | set(into)):
            home = edges.get((m, m), 0)
            row = {"municipality": m, "vintage": key[0], **dict(zip(extra, key[1:], strict=True)),
                   "resident_events": out.get(m, 0), "treated_at_home": home,
                   "self_sufficiency": home / out[m] if out.get(m) else None,
                   "events_treated": into.get(m, 0), "imported": into.get(m, 0) - home,
                   "import_share": (into[m] - home) / into[m] if into.get(m) else None,
                   "net_flow": into.get(m, 0) - out.get(m, 0), "destinations": count.get(m, 0),
                   "main_destination": best[m][1] if m in best else None,
                   "main_destination_share": best[m][0] / out[m] if m in best else None}
            rows.append(row)
    names = ["municipality", "vintage", *extra, "resident_events", "treated_at_home", "self_sufficiency",
             "events_treated", "imported", "import_share", "net_flow", "destinations", "main_destination",
             "main_destination_share"]
    return _table(rows, names)


def _hubs(edges: dict[tuple[str, str], int]) -> dict[str, str]:
    """Origin -> hub, by following dominant destinations."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    into: dict[str, int] = defaultdict(int)
    for (u, v), w in edges.items():
        out[u][v] = w
        into[v] += w
    dominant = {u: min(d, key=lambda v: (-d[v], int(v))) for u, d in out.items()}
    hub: dict[str, str] = {}
    for start in dominant:
        path: list[str] = []
        seen: dict[str, int] = {}
        u = start
        while True:
            if u in hub:
                target = hub[u]
            elif u in seen:                    # a cycle of two or more: the one that treats most
                target = max(path[seen[u]:], key=lambda x: (into[x], -int(x)))
            elif dominant.get(u, u) == u:      # treats mostly its own, or has no residents' events to follow
                target = u
                hub[u] = u
            else:
                seen[u] = len(path)
                path.append(u)
                u = dominant[u]
                continue
            break
        for x in path:
            hub[x] = target
    return hub


def care_flow_catchments(flows: pa.Table) -> pa.Table:
    """Nodal catchments by dominant flow: ``municipality`` -> ``hub`` (a municipality that mostly treats its own).

    ``dominant_share`` is the share of the municipality's events going to its main destination; a
    low share says the assignment is a plurality, not a majority.
    """
    extra, groups = _groups(flows)
    rows = []
    for key, edges in groups:
        hub = _hubs(edges)
        out: dict[str, int] = defaultdict(int)
        top: dict[str, int] = defaultdict(int)
        for (u, _v), w in edges.items():
            out[u] += w
            top[u] = max(top[u], w)
        rows += [{"municipality": u, "vintage": key[0], **dict(zip(extra, key[1:], strict=True)), "hub": hub[u],
                  "dominant_share": top[u] / out[u]} for u in sorted(out)]
    return _table(rows, ["municipality", "vintage", *extra, "hub", "dominant_share"])


def _need(*modules: str) -> None:
    import importlib

    for m in modules:
        try:
            importlib.import_module(m)
        except ImportError as error:
            raise ImportError(f"flow communities need the 'network' extra: pip install 'pegasus-data[network]' ({m})") from error


def care_flow_communities(flows: pa.Table, *, resolution: float = 1.0, seed: int = 0) -> pa.Table:
    """Directed-modularity communities (Leiden, ``RBConfiguration``) of the flow graph, per vintage and group.

    **Input** (``flows``, as `proximity.care_flows` returns it, or built by hand with the same columns):

    * ``from``, ``to``: municipality codes of residence and of treatment, one width throughout (the codes come back as
      given); a row with ``from == to`` is a self-flow and stays in the graph;
    * ``weight``: events on the edge (summed when an edge repeats);
    * ``vintage``: the period the edge belongs to (a year, or any label);
    * ``share`` and ``kind``: read by `care_flows`' other uses, ignored here;
    * **every other column without a dot is a group**, and communities are computed per group: a hand-built table with
      an extra column (a name, a count) is split by it. Drop what is not a classifier first. A column with a dot
      (a measure's ``<role>_n``/``_sum``) rides along and is not read.

    **Output**, one row per municipality, vintage and group: ``municipality``, ``vintage``, the group columns,
    ``community`` (the code of the municipality that treats most events inside the community, its anchor) and ``size``
    (its municipalities). A larger ``resolution`` gives more, smaller communities; report it with any result. The seed
    fixes the run.
    """
    _need("igraph", "leidenalg")
    import igraph
    import leidenalg

    extra, groups = _groups(flows)
    rows = []
    for key, edges in groups:
        nodes = sorted({x for e in edges for x in e})
        index = {m: i for i, m in enumerate(nodes)}
        graph = igraph.Graph(n=len(nodes), edges=[(index[u], index[v]) for u, v in edges], directed=True)
        graph.es["weight"] = [float(w) for w in edges.values()]
        part = leidenalg.find_partition(graph, leidenalg.RBConfigurationVertexPartition, weights="weight",
                                        resolution_parameter=resolution, n_iterations=-1, seed=seed)
        into: dict[str, int] = defaultdict(int)
        for (_u, v), w in edges.items():
            into[v] += w
        members = defaultdict(list)
        for m, c in zip(nodes, part.membership, strict=True):
            members[c].append(m)
        anchor = {c: max(ms, key=lambda x: (into[x], -int(x))) for c, ms in members.items()}
        for m, c in zip(nodes, part.membership, strict=True):
            rows.append({"municipality": m, "vintage": key[0], **dict(zip(extra, key[1:], strict=True)),
                         "community": anchor[c], "size": len(members[c])})
    return _table(rows, ["municipality", "vintage", *extra, "community", "size"])


def compare_flow_regions(flows: pa.Table, communities: pa.Table, *, against: str = "health_region_current") -> dict[str, Any]:
    """Flow communities against an official regionalisation (a classification of the membership pack).

    Returns ``summary`` (one dict per vintage and group) and ``regions`` (one row per official unit).
    In the summary:

    * ``adjusted_rand`` and ``nmi``: agreement of the two partitions over the municipalities that
      are in both (``municipalities``; ``without_membership`` are the ones with no official unit).
    * ``away_kept_official`` and ``away_kept_flow``: of the events treated outside the resident's
      own municipality, the share whose destination is in the same official unit, and in the same
      flow community. Fewer and larger units keep more by construction: read them with the counts
      ``n_official`` and ``n_flow``.
    * ``self_sufficiency``: the share treated at home, for reference.

    In ``regions``, per official unit: its municipalities, ``resident_events``, the share of its
    residents' events treated inside it (``contained``), and its ``main_community`` with the share
    of the unit's resident events whose municipality is in it (``main_community_share``).
    """
    _need("sklearn")
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    from .geography import memberships

    extra, groups = _groups(flows)
    cover = {}
    official: dict[str, str | None] = {}
    assigned = communities.to_pylist()
    for key, edges in groups:
        comm = {r["municipality"]: r["community"] for r in assigned
                if r["vintage"] == key[0] and all(r[c] == v for c, v in zip(extra, key[1:], strict=True))}
        cover[key] = (edges, comm)
        for m in {x for e in edges for x in e}:
            if m not in official:
                member = memberships(m).get(against)
                official[m] = member.member_code if member else None
    summary, region_rows = [], []
    for key, (edges, comm) in cover.items():
        nodes = sorted(comm)
        both = [m for m in nodes if official.get(m)]
        total = sum(edges.values())
        home = sum(w for (u, v), w in edges.items() if u == v)
        away = total - home
        kept_o = sum(w for (u, v), w in edges.items() if u != v and official.get(u) and official.get(u) == official.get(v))
        kept_f = sum(w for (u, v), w in edges.items() if u != v and comm[u] == comm[v])
        a = [official[m] for m in both]
        b = [comm[m] for m in both]
        tag = dict(zip(extra, key[1:], strict=True))
        summary.append({"vintage": key[0], **tag, "municipalities": len(both),
                        "without_membership": len(nodes) - len(both), "n_official": len(set(a)), "n_flow": len(set(b)),
                        "adjusted_rand": float(adjusted_rand_score(a, b)), "nmi": float(normalized_mutual_info_score(a, b)),
                        "self_sufficiency": home / total, "away_kept_official": kept_o / away, "away_kept_flow": kept_f / away,
                        "events": total})
        resident: dict[str, int] = defaultdict(int)
        inside: dict[str, int] = defaultdict(int)
        by_comm: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for (u, v), w in edges.items():
            unit = official.get(u)
            if not unit:
                continue
            resident[unit] += w
            if official.get(v) == unit:
                inside[unit] += w
            by_comm[unit][comm[u]] += w
        n_mun: dict[str, int] = defaultdict(int)
        for m in both:
            n_mun[cast(str, official[m])] += 1
        for unit in sorted(resident):
            main = max(by_comm[unit], key=lambda c: (by_comm[unit][c], c))
            region_rows.append({"vintage": key[0], **tag, "region": unit, "municipalities": n_mun[unit],
                                "resident_events": resident[unit], "contained": inside[unit] / resident[unit],
                                "main_community": main, "main_community_share": by_comm[unit][main] / resident[unit],
                                "communities": len(by_comm[unit])})
    names = ["vintage", *extra, "region", "municipalities", "resident_events", "contained", "main_community",
             "main_community_share", "communities"]
    return {"summary": summary, "regions": _table(region_rows, names)}
