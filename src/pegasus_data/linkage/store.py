"""Link results kept in the lake (ADR-0107: a link is a query, persisted and reused).

A run is identified by its spec, method, period, geography and the spec's
content: a spec edited in ``curation/links.yml`` is a different linkage, so its
old results are not served for it. Each run stores its pairs as Parquet and its
report as JSON under ``<lake>/links/<spec>/``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .engine import raw_links

#: Spec keys that do not change which pairs a run produces: editing them must
#: not orphan stored runs. `person` names who the records are about, for
#: merging links into entities (linkage/entities.py); `same_event` what the pairs mean; `sensitivity` which side's
#: linked share measures the link (engine.side_counts).
_NOT_LINKING = ("person", "same_event", "sensitivity")


def _spec_digest(name: str) -> str:
    body = dict((raw_links().get("links") or {}).get(name) or {})
    for key in _NOT_LINKING:
        body.pop(key, None)
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

    @property
    def stem(self) -> str:
        return f"{self.method}_{self.geography}_{self.period}_{self.digest}"


def run_key(spec: str, method: str, period: object, geography: object) -> RunKey:
    return RunKey(spec, method, _scope(period), _scope(geography), _spec_digest(spec))


def links_dir(settings: Any) -> Path:
    return Path(settings.lake_dir) / "links"


def save(settings: Any, key: RunKey, pairs: pa.Table, summary: dict[str, Any]) -> Path:
    folder = links_dir(settings) / key.spec
    folder.mkdir(parents=True, exist_ok=True)
    pq.write_table(pairs, folder / f"{key.stem}.parquet", compression="zstd")
    report = {**summary, "run": {"spec": key.spec, "method": key.method, "period": key.period,
                                 "geography": key.geography, "spec_digest": key.digest}}
    (folder / f"{key.stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                            encoding="utf-8")
    return folder / f"{key.stem}.parquet"


def load(settings: Any, key: RunKey) -> tuple[pa.Table, dict[str, Any]] | None:
    folder = links_dir(settings) / key.spec
    pairs, report = folder / f"{key.stem}.parquet", folder / f"{key.stem}.json"
    if not (pairs.exists() and report.exists()):
        return None
    table, body = pq.read_table(pairs), json.loads(report.read_text(encoding="utf-8"))
    if _named_by_row(table):
        table, body = _relabel(settings, key.spec, table, body)
        pq.write_table(table, pairs.with_suffix(".tmp"), compression="zstd")
        pairs.with_suffix(".tmp").replace(pairs)
        report.write_text(json.dumps(body, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return table, body


def _named_by_row(table: pa.Table) -> bool:
    """Whether a run names records by the fallback identity, ``<_blob_sha256>:<_row>``, rather than by the content key."""
    for side in ("l", "r"):
        if side in table.column_names and table.num_rows:
            sample = [x for x in table.column(side).slice(0, 100).to_pylist() if x]
            if any(len(x.partition(":")[0]) == 64 and x.partition(":")[2].isdigit() for x in sample):
                return True
    return False


def _relabel(settings: Any, spec: str, table: pa.Table, body: dict[str, Any]) -> tuple[pa.Table, dict[str, Any]]:
    """A run's pairs renamed to each record's current identity (`identity.RECORD_ID_SQL`), read from the lake.

    Runs stored before the lake stamped ``_record_key`` named records ``<_blob_sha256>:<_row>``, while every reader
    since names them by the content key: a stored national run then matched none of its side's records, and the linked
    shares and cohort outcomes built on it read zero without an error (2026-10-10). Both names come from the same
    lake row, so the old one maps to the new one exactly. A record whose file is no longer in the lake (republished
    since) keeps its old name, and the count is recorded in the report."""
    from .._request import parse_dataset
    from .engine import load_links
    from .identity import DUP_SQL, RECORD_ID_SQL, connect

    sides = load_links()[spec]
    con = connect()
    out = table
    unmapped = {}
    for col, side in (("l", sides.left), ("r", sides.right)):
        if col not in table.column_names:
            continue
        system, series = parse_dataset(side.dataset)
        files = Path(settings.lake_dir) / system / f"{system}_{series or system}_*" / "**" / "*.parquet"
        con.register("p", pa.table({"old": table.column(col), "pos": pa.array(range(table.num_rows), pa.int64())}))
        con.execute("CREATE OR REPLACE TEMP TABLE blobs AS SELECT DISTINCT split_part(old, ':', 1) AS b FROM p "
                    "WHERE old LIKE '%:%'")
        con.execute(f"""CREATE OR REPLACE TEMP TABLE m AS
            SELECT _blob_sha256 || ':' || CAST(_row AS VARCHAR) AS old, {RECORD_ID_SQL} AS new
            FROM (SELECT _blob_sha256, _row, _source_path, _record_key, {DUP_SQL}
                  FROM read_parquet('{files.as_posix()}', union_by_name=true)
                  WHERE _blob_sha256 IN (SELECT b FROM blobs))""")
        new = con.execute("SELECT coalesce(m.new, p.old) AS id, m.new IS NULL AND p.old LIKE '%:%' AS miss "
                          "FROM p LEFT JOIN m USING (old) ORDER BY p.pos").to_arrow_table()
        if new.num_rows != table.num_rows:
            raise RuntimeError(f"{spec}: relabelling the {col} side changed the number of pairs (duplicate lake rows?)")
        unmapped[col] = sum(bool(x) for x in new.column("miss").to_pylist())
        out = out.set_column(out.schema.get_field_index(col), col, new.column("id"))
    return out, {**body, "identity": {"relabelled": "fallback <_blob_sha256>:<_row> to the content key (2026-10-10)",
                                      "unmapped": unmapped}}


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


__all__ = ["RunKey", "StoredResult", "links_dir", "load", "run_key", "runs", "save"]


def _params_path(settings: Any, spec: str) -> Path:
    return links_dir(settings) / "_params" / f"{spec}_{_spec_digest(spec)}.json"


def save_params(settings: Any, spec: str, summary: dict[str, Any], scope: str) -> Path:
    """A national run's error channels, threshold and calibration curve: the
    reference a slice pools toward and decides with (linkage-theory §3.2)."""
    path = _params_path(settings, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"spec": spec, "scope": scope, "models": summary.get("models") or [],
            "threshold_bits": summary.get("threshold_bits"), "calibration": summary.get("calibration") or {}}
    path.write_text(json.dumps(body, indent=1), encoding="utf-8")
    return path


def load_params(settings: Any, spec: str) -> dict[str, Any] | None:
    path = _params_path(settings, spec)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
