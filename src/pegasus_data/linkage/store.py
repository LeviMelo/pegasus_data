"""Link results kept in the lake (ADR-0107: a link is a query, persisted and reused).

A run is identified by its spec, method, period, geography and the spec's
content: a spec edited in ``curation/links.yml`` is a different linkage, so its
old results are not served for it. Each run stores its pairs as Parquet and its
report as JSON under ``<lake>/links/<spec>/``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..persist.kept import remove_if_free, write_json_atomic, write_parquet_atomic
from .engine import load_links, raw_links
from .roles import load_roles, table_key

#: Bumped when the engine, the levels, the placebo or the verdict rules change what a run holds: every stored run
#: written under another version is stale (`fingerprint`). 3: one placebo for both engines (`placebo`: the deterministic
#: control and the anchors' control move round the partner's range, as the probabilistic one does). 4: round the range
#: both sides hold (`placebo.shared_range`), not the partner's whole range (OQ 97).
#: 5: a cohort's passes judged horizon by horizon, each kept to its reach (`engine._pass_reach`), not dropped on its
#: whole window's chance.
LINKAGE_VERSION = 5
#: The identity rule of a run read from a state's files: the content key of the whole record, decoded whole even when
#: projected (`retrieve._decode_one`, 2026-11-09); before, the file and row. Only runs of a scope but the nation's carry it.
STATE_IDENTITY = "content-key-1"

#: Spec keys that do not change which pairs a run produces: editing them must
#: not orphan stored runs. `person` names who the records are about, for
#: merging links into entities (linkage/entities.py); `same_event` what the pairs mean; `sensitivity` which side's
#: linked share measures the link (engine.side_counts).
_NOT_LINKING = ("person", "same_event", "sensitivity")
#: Keys inside a linking part that describe the pairs for the quality measures and choose none of them: the outcome's
#: ``known`` (the events the left records itself) and a pass's ``known_only`` (`followup.quantities`). Hashing them
#: orphaned every stored sih_admissions_to_sim run when Q1 declared them (019cc63f; t07, 2026-11-23).
_NOT_LINKING_INSIDE = {"outcome": ("known",), "passes": ("known_only",)}


def _spec_digest(name: str) -> str:
    body = dict((raw_links().get("links") or {}).get(name) or {})
    for key in _NOT_LINKING:
        body.pop(key, None)
    if isinstance(body.get("outcome"), dict):
        body["outcome"] = {k: v for k, v in body["outcome"].items() if k not in _NOT_LINKING_INSIDE["outcome"]}
    for part in ("deterministic", "probabilistic"):
        sub = body.get(part)
        if isinstance(sub, dict) and isinstance(sub.get("passes"), list):
            body[part] = {**sub, "passes": [{k: v for k, v in p.items() if k not in _NOT_LINKING_INSIDE["passes"]}
                                            if isinstance(p, dict) else p for p in sub["passes"]]}
    if isinstance(body.get("passes"), list):
        body["passes"] = [{k: v for k, v in p.items() if k not in _NOT_LINKING_INSIDE["passes"]}
                          if isinstance(p, dict) else p for p in body["passes"]]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _scope(value: object) -> str:
    """A scope as a file-name part; nested scopes (a period and its partner's
    padded period) flatten: "2022-2021-2022". Formatting the inner tuple with
    str() put quotes and parentheses in the file name, and a SQL read of it
    failed (2026-10-03)."""
    if isinstance(value, (list, tuple)):
        return "-".join(_scope(v) for v in value)
    return str(value)


@dataclass(frozen=True, slots=True)
class RunKey:
    spec: str
    method: str
    period: str
    geography: str
    digest: str
    #: the digest of a parameterised spec's caller values (`engine.Codes.digest`): two topics' runs of one spec are two
    #: files. "" for a spec as declared, whose file names are unchanged
    params: str = ""

    @property
    def stem(self) -> str:
        return f"{self.method}_{self.geography}_{self.period}_{self.digest}" + (f"_p{self.params}" if self.params else "")


def run_key(spec: str, method: str, period: object, geography: object, params: str = "") -> RunKey:
    return RunKey(spec, method, _scope(period), _scope(geography), _spec_digest(spec), params)


def links_dir(settings: Any) -> Path:
    return Path(settings.lake_dir) / "links"


def _fingerprint_of(settings: Any, spec: str, period: str, seen: frozenset[str] = frozenset()) -> str:
    sides = load_links()[spec]
    years = sorted({int(t) for t in re.findall(r"\d{4}", period)})
    h = hashlib.sha256(f"{LINKAGE_VERSION}|{spec}|".encode())
    declared = load_roles()
    for side in (sides.left, sides.right):
        # the municipality role whose state publishes a record scores its error channels (engine); no role table holds it
        roles_of_side = declared.get(side.dataset.upper())
        h.update(f"{side.dataset}|setting={roles_of_side.setting if roles_of_side else None}|".encode())
        for year in range(years[0], years[-1] + 1) if years else ():
            h.update(f"{side.dataset}|{year}|{table_key(side.dataset, year, settings)}|".encode())
    # a link that takes a role from another stored link (`inherit`) is as current as that link
    body = (raw_links().get("links") or {}).get(spec) or {}
    for side in ("left", "right"):
        for item in ((body.get("probabilistic") or {}).get("inherit") or {}).get(side) or []:
            via = str(item["via"])
            if via not in seen:
                h.update(_fingerprint_of(settings, via, period, seen | {spec}).encode())
    return h.hexdigest()[:20]


def fingerprint(settings: Any, key: RunKey) -> str:
    """What a run depends on besides its spec: the engine's own version (``LINKAGE_VERSION``), each side's ``setting``
    and the role tables of the years it read, by their keys (`roles.table_key`: the datasets' roles, the codelists
    their labelled columns are labelled with, and the lake partition files of each year; not the label pack as a
    whole). A run is served only while its fingerprint is the current one. The record identity is a hash of the
    normalised fields, so a normalisation fix, a republished preliminary file or a changed role makes every stored id
    match nothing, and the runs built on them (linked shares, entities, inherited roles) read zero without an error
    (2026-10-10, again 2026-10-14). The label pack as a whole was in it until 2026-10-24, and the re-windowing of one
    system's labels (CIH, which no link reads) made every stored 2022 run stale.

    A run over a state (or any scope but the nation's) read its sides from the state's files, where until 2026-11-09 a
    projected read carried no content key: its ids were file and row, which the national read of the same records does
    not share. Such runs carry ``STATE_IDENTITY`` in their fingerprint, so those written before are stale once; the
    national runs, read from tables that always carried the key, are not."""
    base = _fingerprint_of(settings, key.spec, key.period)
    if str(key.geography).upper() == "BR":
        return base
    return hashlib.sha256(f"{base}|{STATE_IDENTITY}".encode()).hexdigest()


def save(settings: Any, key: RunKey, pairs: pa.Table, summary: dict[str, Any]) -> Path:
    """The pairs first, the report last: a run exists when its report does, and the report names the pairs file's
    size, so a crash between the two (or a reader between the two renames) never serves old pairs under a new report."""
    folder = links_dir(settings) / key.spec
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{key.stem}.parquet"
    write_parquet_atomic(pairs, target, compression="zstd")
    report = {**summary, "run": {"spec": key.spec, "method": key.method, "period": key.period,
                                 "geography": key.geography, "spec_digest": key.digest,
                                 "fingerprint": fingerprint(settings, key), "pairs_bytes": target.stat().st_size,
                                 **({"params": key.params} if key.params else {})}}
    write_json_atomic(report, folder / f"{key.stem}.json", ensure_ascii=False, indent=1, default=str)
    return target


def report(settings: Any, key: RunKey, *, allow_stale: bool = False) -> dict[str, Any] | None:
    """A stored run's report without its pairs, or None when there is none or it is not current: written under other
    inputs (``fingerprint``) or before runs carried one, or its pairs file is not the one the report describes.
    ``allow_stale`` returns it anyway with ``["stale"]`` naming why. The one currency rule of every reader: PegaSUS read
    the report file directly and took runs of the code before the placebo fix for current (2026-10-14)."""
    folder = links_dir(settings) / key.spec
    pairs, path = folder / f"{key.stem}.parquet", folder / f"{key.stem}.json"
    if not (pairs.exists() and path.exists()):
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    run = body.get("run") or {}
    stale = ""
    if run.get("pairs_bytes") != pairs.stat().st_size:
        stale = "pairs file is not the report's (or the run predates fingerprints)"
    elif run.get("fingerprint") != fingerprint(settings, key):
        stale = "inputs changed since the run (roles, labels, lake files or engine version)"
    if stale:
        if not allow_stale:
            return None
        body["stale"] = stale
    return body


def load(settings: Any, key: RunKey, *, allow_stale: bool = False) -> tuple[pa.Table, dict[str, Any]] | None:
    """A stored run (its pairs and its `report`), or None when there is none or it is not current; ``allow_stale``
    returns it anyway with ``report["stale"]`` naming why, for a reader that wants to see old runs."""
    body = report(settings, key, allow_stale=allow_stale)
    if body is None:
        return None
    return pq.read_table(links_dir(settings) / key.spec / f"{key.stem}.parquet"), body


def runs(settings: Any) -> list[dict[str, Any]]:
    """Every stored run's report, current spec or not (``current`` says which)."""
    out: list[dict[str, Any]] = []
    root = links_dir(settings)
    if not root.exists():
        return out
    for report in sorted(root.glob("*/*.json")):
        body = json.loads(report.read_text(encoding="utf-8"))
        run = body.get("run", {})
        try:
            run["current"] = run.get("spec_digest") == _spec_digest(run.get("spec", ""))
        except Exception:  # noqa: BLE001 - a spec deleted since is simply not current
            run["current"] = False
        try:
            run["fingerprint_current"] = run.get("fingerprint") == _fingerprint_of(settings, run.get("spec", ""),
                                                                                    str(run.get("period", "")))
        except Exception:  # noqa: BLE001
            run["fingerprint_current"] = False
        body["run"] = run
        body.pop("models", None)
        out.append(body)
    return out


@dataclass
class StoredResult:
    """A stored run, shaped like a fresh result for callers."""

    spec: str
    pairs: pa.Table
    report: dict[str, Any]

    @property
    def verdict(self) -> str:
        return str(self.report.get("verdict", ""))

    def summary(self) -> dict[str, Any]:
        return self.report


def _params_path(settings: Any, spec: str, period: str) -> Path:
    return links_dir(settings) / "_params" / f"{spec}_{_spec_digest(spec)}_{period}.json"


def save_params(settings: Any, key: RunKey, summary: dict[str, Any]) -> Path:
    """A national run's error channels (unrounded), threshold and calibration curve: the reference a slice of the same
    period pools toward and decides with (linkage-theory §3.2). One file per period: a single file per spec was
    overwritten by whichever national run came last, so a slice of 2021 decided with the threshold of 2025
    (22.93 against 25.27)."""
    path = _params_path(settings, key.spec, key.period)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"spec": key.spec, "scope": f"{key.geography} {key.period}", "models": summary.get("models") or [],
            "threshold_bits": summary.get("threshold_bits"), "calibration": summary.get("calibration") or {},
            "fingerprint": fingerprint(settings, key)}
    write_json_atomic(body, path, indent=1)
    return path


def load_params(settings: Any, key: RunKey) -> dict[str, Any] | None:
    """The national reference of ``key``'s spec and period, or None when there is none or it is not current."""
    path = _params_path(settings, key.spec, key.period)
    if not path.exists():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    return body if body.get("fingerprint") == fingerprint(settings, key) else None


__all__ = ["LINKAGE_VERSION", "RunKey", "StoredResult", "fingerprint", "links_dir", "load", "load_params", "run_key",
           "runs", "save", "save_params"]


@contextmanager
def carried_currency(settings: Any) -> Iterator[dict[str, int]]:
    """Keep current, across a rewrite of the lake's storage that changes no record (`persist.lake.reencode_lake`), the
    role tables and stored runs that were current before it. Their keys hash the lake files' sizes and times
    (`roles.table_key`), which a rewrite changes while every record, and so every identity, stays the same: without
    this, 13 GB of role tables and every stored run would be stale and recomputed for nothing. Only what was current
    before is carried; a role table is moved to its new key in the cache's stored form (`roles.stored_form`), a run's
    report takes the new fingerprint."""
    from .roles import stored_form, table_key

    caches: list[tuple[Path, str, int]] = []
    stale: list[Path] = []      # a table under a key no lake state can give again is never served: it goes
    for path in sorted((Path(settings.lake_dir) / "roles").glob("*/*.parquet")):
        head, _, key = path.stem.partition("__")
        if re.fullmatch(r"\d{4}_BR", head) and table_key(path.parent.name, int(head[:4]), settings) == key:
            caches.append((path, path.parent.name, int(head[:4])))
        else:
            stale.append(path)
    current: list[tuple[Path, RunKey]] = []
    for path in sorted(links_dir(settings).glob("*/*.json")):
        run = (json.loads(path.read_text(encoding="utf-8")).get("run") or {})
        try:
            key = RunKey(str(run["spec"]), str(run["method"]), str(run["period"]), str(run["geography"]),
                         str(run["spec_digest"]), str(run.get("params", "")))
        except KeyError:
            continue
        if key.stem == path.stem and report(settings, key) is not None:
            current.append((path, key))
    counts = {"role_tables_carried": len(caches), "role_tables_stale_removed": len(stale), "runs_carried": len(current)}
    yield counts
    for path in stale:
        remove_if_free(path)        # one a reader holds open is left for a later prune
    for path, dataset, year in caches:
        new = table_key(dataset, year, settings)
        if new is None:
            continue
        target = path.with_name(f"{year}_BR__{new}.parquet")
        try:
            table = pq.read_table(path)
        except FileNotFoundError:
            # replaced while the lake was rewritten: a build of the same year writes the new table and removes the old
            # (`roles._national_year`); the re-encode of 2026-11-21 stopped here, the new table being the current one
            continue
        write_parquet_atomic(stored_form(table), target, compression="zstd")
        if target != path:
            remove_if_free(path)
    for path, key in current:
        body = json.loads(path.read_text(encoding="utf-8"))
        body["run"]["fingerprint"] = fingerprint(settings, key)
        write_json_atomic(body, path, ensure_ascii=False, indent=1, default=str)
