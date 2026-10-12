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

Every column a study reads as a field (any kind, model not ``link_only`` or ``excluded``: categories, numbers, dates,
codes, places, institutions) also states its ``fact_domain`` (what it is a fact about: person, clinical, process or
administrative) with the evidence it rests on; one no documentation places stays undeclared.

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
#: The keys a column's declaration may carry.
KEYS = frozenset({"role", "kind", "model", "years", "name", "missing", "missing_unknown", "note", "codelists", "domain",
                  "also", "derived", "measure", "unfilled", "review", "instruments", "instruments_evidence",
                  "fact_domain", "fact_domain_evidence"})
#: What a column is a fact about (`fact_domain`; ``domain`` is taken: a measurement's numeric range). A study
#: reads person, clinical and process columns as the groups a population or its care can differ by; an administrative
#: one (billing, financing, management, record type) says nothing about people or disease.
FACT_DOMAINS = ("person", "clinical", "process", "administrative")
#: The models a study reads as a field (not a link key and not set aside): the non-categorical columns that state a
#: ``fact_domain``.
FIELD_MODELS = MODELS - {"link_only", "excluded"}
#: SIGTAP's registration instruments (``tb_registro``): 01 BPA consolidado, 02 BPA individualizado, 03-05 AIH principal,
#: especial and secundário, 06-07 APAC principal and secundário, 08-09 RAAS domiciliar and psicossocial, 10 e-SUS APS.
INSTRUMENTS = frozenset(f"{n:02d}" for n in range(1, 11))
#: The properties a population account carries, the only admissible strata.
STRATA = frozenset({"age", "birth_date", "sex", "race", "residence"})
_ROLE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
#: Properties whose numbers are codes, not quantities: their sums and logs mean nothing (ADR-0154). A calendar index
#: (a property ending in ``week`` or ``year``: case.diagnosis_week, notification.week) is one by its name's own
#: statement, whatever the form (SINAN-HANS's diagnosis week was modelled as a measurement until 2026-10-08).
NOT_MEASURES = frozenset({"age_coded", "time"})
_CALENDAR = re.compile(r"(^|_)(week|year)$")


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
    #: Why the sources cannot decide the "not recorded" codes (``missing`` stays undeclared): a column examined, not a
    #: column waiting (P1's coverage names the reason instead of a gap)
    missing_unknown: str | None = None
    #: Years inside ``years`` in which the column is present but fills no record (`field_fill`): a span cannot hold
    #: SIM-DO's DTCONCASO, filled 2012-2013 and from 2017, or SINASC's CODPAISRES, empty in 2014, 2015 and 2017
    unfilled: tuple[int, ...] = ()
    #: For a SIGTAP-coded column: the registration instruments (``INSTRUMENTS``) whose procedures it can carry, with the
    #: document or measurement that says so (`can_record` reads them against SIGTAP's ``rl_procedimento_registro``).
    instruments: tuple[str, ...] = ()
    instruments_evidence: str | None = None
    #: What the column is a fact about (`FACT_DOMAINS`), with the dictionary or layout line it rests on. None: not placed
    #: from the documentation, listed by `undeclared_fact_domains`, never guessed.
    fact_domain: str | None = None
    fact_domain_evidence: str | None = None

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
                "domain": None if self.domain is None else list(self.domain), "fact_domain": self.fact_domain,
                **({"fact_domain_evidence": self.fact_domain_evidence} if self.fact_domain else {}),
                **({"missing_unknown": self.missing_unknown} if self.missing_unknown else {}),
                **({"unfilled": list(self.unfilled)} if self.unfilled else {}),
                **({"instruments": list(self.instruments), "instruments_evidence": self.instruments_evidence}
                   if self.instruments else {})}


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

    unknown_keys = set(spec) - KEYS
    if unknown_keys:
        raise bad(f"unknown keys {sorted(unknown_keys)}: a misspelt key would be silently ignored")
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
        measure = bool(spec["measure"]) if "measure" in spec else not (prop in NOT_MEASURES or _CALENDAR.search(prop))
    elif "measure" in spec:
        raise bad("`measure` is declared for numbers only")
    missing = tuple(str(v) for v in spec["missing"]) if "missing" in spec else None
    dom = spec.get("domain")
    if dom is not None and (len(dom) != 2 or float(dom[0]) > float(dom[1])):
        raise bad(f"domain {dom!r} is not [lo, hi]")
    domain = (float(dom[0]), float(dom[1])) if dom is not None else None
    unknown = spec.get("missing_unknown")
    if unknown is not None and missing is not None:
        raise bad("missing codes are declared or unknown, not both")
    if unknown is not None and not str(unknown).strip():
        raise bad("missing_unknown states why the sources cannot decide")
    unfilled = tuple(sorted(int(y) for y in spec.get("unfilled") or ()))
    instruments = tuple(str(i).zfill(2) for i in spec.get("instruments") or ())
    if set(instruments) - INSTRUMENTS:
        raise bad(f"instruments {sorted(set(instruments) - INSTRUMENTS)} are not SIGTAP registers {sorted(INSTRUMENTS)}")
    if instruments and "SIGTAP" not in (spec.get("codelists") or ()):
        raise bad("instruments are declared for a SIGTAP-coded column")
    if instruments and not str(spec.get("instruments_evidence") or "").strip():
        raise bad("instruments need their instruments_evidence: the document or measurement that says so")
    if not instruments and "instruments_evidence" in spec:
        raise bad("instruments_evidence without instruments")
    fact = spec.get("fact_domain")
    if fact is not None and str(fact) not in FACT_DOMAINS:
        raise bad(f"fact_domain {fact!r} not in {list(FACT_DOMAINS)}")
    if fact is not None and not str(spec.get("fact_domain_evidence") or "").strip():
        raise bad("a fact_domain needs its fact_domain_evidence: the dictionary or layout line it rests on")
    if fact is None and "fact_domain_evidence" in spec:
        raise bad("fact_domain_evidence without fact_domain")
    lo, hi = (years + (None, None))[:2] if len(years) == 2 else (None, None)
    if unfilled and ((lo is not None and unfilled[0] < lo) or (hi is not None and unfilled[-1] > hi)):
        raise bad(f"unfilled years {list(unfilled)} lie outside its years {list(years)}")
    return ColumnRole(dataset, column, role, kind, model, also, spec.get("name"),
                      tuple(str(c) for c in spec.get("codelists") or ()),
                      (years[0], years[1]) if len(years) == 2 else (None, None),  # type: ignore[arg-type]
                      spec.get("review") != "draft", spec.get("note"), bool(spec.get("derived")), measure, missing,
                      domain, str(unknown).strip() if unknown is not None else None, unfilled, instruments,
                      " ".join(str(spec["instruments_evidence"]).split()) if instruments else None,
                      str(fact) if fact is not None else None,
                      " ".join(str(spec["fact_domain_evidence"]).split()) if fact is not None else None)


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
            if role.type in ("year", "birth_from_age"):
                # computed from the column(s): a birth year from a birth date, a birth date from an age and a date. The
                # column keeps its own role; none may claim to state the derived property
                for source in role.also:
                    if source.upper() not in columns:
                        raise ValueError(f"roles/{dataset}.yml: linkage role {name} reads {source}, which is not declared")
                continue
            if name != column.role and name not in column.also:
                raise ValueError(f"roles/{dataset}.yml: {role.column} is {column.role}, but linkage reads it as {name}; "
                                 "add it to `also` or correct one of them")


def undeclared_fact_domains(dataset: str | None = None) -> list[tuple[str, str]]:
    """The columns no ``fact_domain`` places (``(dataset, column)``), for one dataset or all: every categorical column
    and every other column a study reads as a field (``FIELD_MODELS``). The list a reviewer closes, never a default."""
    declared = load_column_roles()
    keys = [dataset.upper().replace(".", "-")] if dataset else sorted(declared)
    return [(d, c.column) for d in keys for c in declared.get(d, ())
            if (c.kind == "category" or c.model in FIELD_MODELS) and c.fact_domain is None]


def roles(dataset: str, period: object = None) -> list[dict[str, Any]]:
    """The role of every column of a dataset, as rows (``pegasus-data roles <dataset>``).

    A role can sit on a different column in each layout generation (SIM-DOFET's residence is MUNIRES in 1979-1995 and
    CODMUNRES from 1996; both rows are returned, each with its ``first_year``/``last_year``). A caller that reads one
    year must not collapse them by role: pass ``period`` (a year, or a ``(first, last)`` pair / range / list of years)
    and only the columns whose years intersect it are returned; a column with no declared years always is."""
    rows = _all_roles(dataset)
    if period is None:
        return rows
    ys = [int(period)] if isinstance(period, (int, str)) else [int(y) for y in period]
    lo, hi = min(ys), max(ys)
    return [r for r in rows if (r["first_year"] is None or r["first_year"] <= hi)
            and (r["last_year"] is None or r["last_year"] >= lo)]


def _all_roles(dataset: str) -> list[dict[str, Any]]:
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
