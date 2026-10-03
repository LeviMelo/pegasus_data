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

from ..semantics.curation import read_yaml
from .engine import LINKS_FILE

#: Spec keys that do not change which pairs a run produces: editing them must
#: not orphan stored runs. `person` names who the records are about, for
#: merging links into entities (linkage/entities.py).
_NOT_LINKING = ("person",)


def _spec_digest(name: str) -> str:
    body = dict((read_yaml(LINKS_FILE).get("links") or {}).get(name) or {})
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
    return pq.read_table(pairs), json.loads(report.read_text(encoding="utf-8"))


def runs(settings: Any) -> list[dict[str, Any]]:
    """Every stored run's report, current spec or not (``current`` says which)."""
    out = []
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
