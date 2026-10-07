"""A role for every column: which entity's property it states, and how a model uses it.

Declared per dataset in ``curation/roles/<dataset>.yml`` (DESIGN §3.2 of
PegaSUS; handoff 2026-10-04 §2). Each column states three things:

* ``role``: ``<entity>.<property>``, from the test "if the same person had a
  different event, would this value change?": no, a person attribute; yes, an
  event attribute (a mark); it describes what the event points to, an
  institution or place attribute; it identifies, an identifier;
* ``kind``: how its values behave (:data:`KINDS`);
* ``model``: what a model may do with it (:data:`MODELS`). A **stratum** must
  be carried by a population account (age, sex, race, residence); every other
  categorical fact about persons is a dimension or a mark.

The linkage roles of ``curation/roles.yml`` name some of these columns for
comparison; each must agree with the column's declared role (one mechanism,
two uses).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

KINDS = frozenset({"category", "code_tree", "number", "date", "place", "institution", "identifier", "text"})
MODELS = frozenset({"stratum", "dimension", "event_type", "mark", "when", "where", "institution",
                    "link_only", "excluded"})
#: The properties a population account carries, the only admissible strata.
STRATA = frozenset({"age", "birth_date", "sex", "race", "residence"})
_ROLE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
#: Properties whose numbers are codes, not quantities: their sums and logs mean nothing (ADR-0154).
NOT_MEASURES = frozenset({"age_coded", "year", "birth_year", "epi_week", "onset_week", "time"})


@dataclass(frozen=True, slots=True)
class ColumnRole:
    dataset: str
    column: str
    role: str
    kind: str
    model: str
    also: tuple[str, ...] = ()
    name: str | None = None
    codelists: tuple[str, ...] = ()
    years: tuple[int | None, int | None] = (None, None)
    reviewed: bool = True
    note: str | None = None
    #: Made by the query (IDADE_anos, ADR-0070), not filed by DATASUS.
    derived: bool = False
    #: For a `number`: whether its values are a measurement (a quantity whose sums and logs mean something). Not for a
    #: packed or coded number (an age with its unit, a clock time, a year, a week): `NOT_MEASURES` by property, or the
    #: column's own `measure: false`.
    measure: bool | None = None
    #: For a measurement: the codes that mean "not recorded" (an empty tuple: the source names none, so every value is
    #: one; None: not yet declared, and the measurement is not to be modelled), and its documented domain [lo, hi].
    missing: tuple[str, ...] | None = None
    domain: tuple[float, float] | None = None

    @property
    def entity(self) -> str:
        return self.role.split(".", 1)[0]

    @property
    def property(self) -> str:
        return self.role.split(".", 1)[1]

    def as_dict(self) -> dict[str, Any]:
        return {"dataset": self.dataset, "column": self.column, "role": self.role, "entity": self.entity,
                "property": self.property, "kind": self.kind, "model": self.model, "also": list(self.also),
                "name": self.name, "codelists": list(self.codelists), "first_year": self.years[0],
                "last_year": self.years[1], "reviewed": self.reviewed, "derived": self.derived, "note": self.note,
                "measure": self.measure, "missing": None if self.missing is None else list(self.missing),
                "domain": None if self.domain is None else list(self.domain)}


def roles_dir() -> Path:
    from ..config import curation_root

    return curation_root() / "roles"


@lru_cache(maxsize=1)
def load_column_roles() -> dict[str, tuple[ColumnRole, ...]]:
    """Every declared dataset's columns, validated; a violation is an error."""
    from .curation import read_yaml

    out: dict[str, tuple[ColumnRole, ...]] = {}
    folder = roles_dir()
    if not folder.exists():
        return out
    for path in sorted(folder.glob("*.yml")):
        if path.name.endswith(".draft.yml"):
            continue
        body = read_yaml(path)
        dataset = str(body.get("dataset") or path.stem).upper()
        rows = []
        for column, spec in (body.get("columns") or {}).items():
            # the declared spelling is the column's name: a derived column is mixed-case
            # (IDADE_anos), and upper-casing it named a column no table has (PegaSUS, 2026-10-04)
            rows.append(_column(dataset, str(column), spec or {}, path.name))
        out[dataset] = tuple(rows)
    _agree_with_linkage(out)
    return out


def _column(dataset: str, column: str, spec: dict[str, Any], where: str) -> ColumnRole:
    def bad(message: str) -> ValueError:
        return ValueError(f"{where}: {column}: {message}")

    role, kind, model = str(spec.get("role", "")), str(spec.get("kind", "")), str(spec.get("model", ""))
    if not _ROLE.match(role):
        raise bad(f"role {role!r} is not <entity>.<property>")
    if kind not in KINDS:
        raise bad(f"kind {kind!r} not in {sorted(KINDS)}")
    if model not in MODELS:
        raise bad(f"model {model!r} not in {sorted(MODELS)}")
    prop = role.split(".", 1)[1]
    if model == "stratum" and prop not in STRATA and not prop.startswith("age_"):
        raise bad(f"a stratum must be a property a population account carries {sorted(STRATA)}, not {prop!r}")
    if kind == "identifier" and model not in ("link_only", "excluded"):
        raise bad("an identifier is link_only or excluded")
    also = tuple(str(a) for a in spec.get("also") or ())
    for extra in also:
        if not _ROLE.match(extra):
            raise bad(f"also {extra!r} is not <entity>.<property>")
    years = tuple(spec.get("years") or (None, None))
    measure = None
    if kind == "number":
        measure = bool(spec["measure"]) if "measure" in spec else prop not in NOT_MEASURES
    elif "measure" in spec:
        raise bad("`measure` is declared for numbers only")
    missing = tuple(str(v) for v in spec["missing"]) if "missing" in spec else None
    dom = spec.get("domain")
    if dom is not None and (len(dom) != 2 or float(dom[0]) > float(dom[1])):
        raise bad(f"domain {dom!r} is not [lo, hi]")
    domain = (float(dom[0]), float(dom[1])) if dom is not None else None
    return ColumnRole(dataset, column, role, kind, model, also, spec.get("name"),
                      tuple(str(c) for c in spec.get("codelists") or ()),
                      (years[0], years[1]) if len(years) == 2 else (None, None),  # type: ignore[arg-type]
                      spec.get("review") != "draft", spec.get("note"), bool(spec.get("derived")), measure, missing,
                      domain)


def _agree_with_linkage(declared: dict[str, tuple[ColumnRole, ...]]) -> None:
    """Every linkage role names a column whose declared roles include it."""
    from ..linkage.roles import load_roles

    for dataset, spec in load_roles().items():
        columns = {c.column.upper(): c for c in declared.get(dataset, ())}
        if not columns:
            continue
        for name, role in spec.roles.items():
            column = columns.get(role.column.upper())
            if column is None:
                raise ValueError(f"roles/{dataset}.yml: linkage role {name} reads {role.column}, which is not declared")
            if name != column.role and name not in column.also:
                raise ValueError(f"roles/{dataset}.yml: {role.column} is {column.role}, but linkage reads it as {name}; "
                                 "add it to `also` or correct one of them")


def roles(dataset: str) -> list[dict[str, Any]]:
    """The role of every column of a dataset, as rows (``pegasus-data roles <dataset>``)."""
    from .._request import parse_dataset

    declared = load_column_roles()
    key = dataset.upper().replace(".", "-")
    if key not in declared:
        system, series = parse_dataset(dataset)
        for candidate in (f"{system}-{series}", f"{system}", f"{series}"):
            alias = {"SIHSUS-RD": "SIH-RD", "CIHA-CIHA": "CIHA"}.get(candidate, candidate)
            if alias in declared:
                key = alias
                break
        if key not in declared and system.upper() == "SINAN" and "SINAN-*" in declared:
            key = "SINAN-*"     # the notification block every agravo's form carries (roles/SINAN-_notification.yml)
    if key not in declared:
        raise KeyError(f"no column roles declared for {dataset!r}; declared: {sorted(declared)}")
    return [c.as_dict() for c in declared[key]]
