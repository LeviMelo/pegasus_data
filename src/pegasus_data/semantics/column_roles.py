"""A role for every column: which entity's property it states, and how a model uses it.

Declared per dataset in ``curation/roles/<dataset>.yml`` (DESIGN §3.2 of
PegaSUS; handoff 2026-10-04 §2). Each column states three things:

* ``role``: ``<entity>.<property>``, from the test "if the same person had a
  different event, would this value change?": no, a person attribute; yes, an
  event attribute (a mark); it describes what the event points to, an
  institution or place attribute; it identifies, an identifier;
* ``kind``: how its values behave (:data:`KINDS`);
* ``model``: what a model may do with it (:data:`MODEL_MEANING`). A **stratum** must
  be carried by a population account (age, sex, race, residence); every other
  categorical fact about persons is a dimension or a mark.

A **place** (``kind: place``) states whose place it is, `place_of` (:data:`PLACE_OF`): the **subject**'s own (where the
person lives, was born or works), the **event**'s (where the event the role's entity names, its care, notification,
infection or exposure happened) or the **record**'s (where the record was made, kept or managed: the registry office, the
death-verification service, a managing authority, a laboratory or partner service it names). Its model says what a study
may do with it: the residence of the person is a **stratum** (always a subject's place); a **where** is the one an
event is placed at (always an event's place; a record's place is never one); every other place is a **mark** or a
**dimension**, still typed by `place_of`. Flows between places (`proximity.flows`) read the pair (residence, where).
A stratum that stands for another place because the file holds no residence names it, ``place_label`` ("probable place
of infection": FA-HUM's cases are placed where they were infected), so a reader is never told it is where they live.

Every column a study reads as a field (any kind, model not ``link_only`` or ``excluded``: categories, numbers, dates,
codes, places, institutions) also states its ``fact_domain`` (what it is a fact about: person, clinical, process or
administrative) with the evidence it rests on; one no documentation places stays undeclared.

An **outcome column** (the event's own result: SINAN's EVOLUCAO, a hospital stay's MORTE) also states which of its
codes mean death, ``fatal``: the codes of death by the event's own cause (the notified disease; a yes/no death flag's
"yes"), and ``fatal_other`` the codes of death from another cause, kept apart because a case fatality counts the
notified disease's deaths only. Both are written from the labels DATASUS publishes for the column (a comment beside
them names the codelist), never from a label a consumer matches at run time; a code that is neither (an outcome still
under investigation) is in neither list, and a column whose labels do not decide leaves them undeclared.

A **measure** (a ``kind: number`` that is a quantity, ``measure`` true) also states what it is measured in
(:data:`UNITS`): ``unit``, with the document line it rests on (``unit_evidence``) and, for a ``count``, what is counted
(``unit_of``). A measure whose unit no document gives has none and says why (``unit_unknown``), listed by
:func:`undeclared_units`, never guessed from the column's name. An amount of money is of the month it was billed in: it
names the column(s) that state that month (``competence``), and, when the layout's currency changed inside the column's
years, the first month in the unit (``unit_from``); a nominal amount is deflated with that month's price index, never
the year's.

A column the dataset does not file, because another dataset files it on the same record, is **reached through a key**
(``through``, ADR-0199): ``through: {key: AIH, dataset: SIH-RD}`` says "this column is the column of the same name of
SIH-RD, on the row that shares this record's ``AIH`` key" (``curation/joins.yml`` names each side's column and, where the
source repeats a key, its principal row). SIH-SP files the procedure lines of an admission with the patient's municipality
but no sex or age; its ``SEXO`` and ``IDADE_anos`` are SIH-RD's, so a count of SP's procedures by sex and age exists.
The column keeps the source's name and must state the same role and kind there (a sex is a sex); it is read only when
selected by name, from the source for the same period and geography, never filling a record's gap with a guess:
`semantics.through` reads it and reports the records whose key found no row.

A column linkage compares carries ``compare:`` in the same file (role -> how it is normalised, `linkage.roles`):
one declaration of a column, read by both.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..normalize.time import month_of, year_of
from ..ontology import dataset_key
from .epoch import curated

KINDS = frozenset({"category", "code_tree", "number", "date", "place", "institution", "identifier", "text"})
#: What each model means. A place's two models that say where something happened are defined in the module docstring.
MODEL_MEANING = {
    "stratum": "a property a population account carries (age, sex, race, residence): a study's units are strata of it",
    "dimension": "a categorical fact about persons or their events that a study may cut by",
    "event_type": "the code that says what kind of event a record is (a diagnosis, a procedure, a cause)",
    "mark": "a fact the record carries that no model conditions on: a quantity, a date it only names, or, for a place, "
            "one the record only names (`place_of` says whose it is)",
    "when": "the date the event happened",
    "where": "the place an event is placed at: where the event, its care, its notification or its infection happened",
    "institution": "the establishment or organisation the record is of",
    "link_only": "read only to link records, never as a field",
    "excluded": "set aside: not a fact about the event",
}
MODELS = frozenset(MODEL_MEANING)
#: What a measure is measured in (`unit`). A currency is nominal: reais (dollars) of the month the amount belongs to.
UNITS = {
    "BRL": "reais of the competence month, at that month's prices (nominal): constant reais need that month's price index",
    "USD": "US dollars of the competence month",
    "days": "days",
    "weeks": "weeks",
    "months": "months",
    "years": "years",
    "grams": "grams",
    "kg": "kilograms",
    "cm": "centimetres",
    "mm": "millimetres",
    "ml": "millilitres",
    "g/dL": "grams per decilitre (the layouts' \"g%\")",
    "mg/dL": "milligrams per decilitre",
    "score": "points of a score (Apgar 0 to 10, Barros)",
    "percent": "a percentage (the urea reduction rate: 100 x (urea before - urea after) / urea before)",
    "count": "a number of the things `unit_of` names",
}
#: The units that are an amount of money: they name the column(s) of the month the amount belongs to (`competence`).
CURRENCIES = frozenset({"BRL", "USD"})
#: The models a place column may have.
PLACE_MODELS = frozenset({"where", "mark", "stratum", "dimension", "link_only", "excluded"})
#: Whose place a place column is (`place_of`, required of every place). A stratum's is the subject's, a where's the event's.
PLACE_OF = {
    "subject": "the person's own place, whichever event is recorded: where they live (now or then), were born or work",
    "event": "where the event the role's entity names happened, or its care, notification, infection, exposure or "
             "history: the death's municipality, the hospital's, the notifying unit's, the infection's, a place of travel",
    "record": "where the record was made, kept or managed, or an institution it names served: the registry office, the "
              "death-verification service, a managing authority, a laboratory or partner service",
}
#: The keys a column's declaration may carry (`compare`: how linkage compares its roles, `linkage.roles`).
KEYS = frozenset({"role", "kind", "model", "years", "name", "missing", "missing_unknown", "note", "codelists", "domain",
                  "also", "derived", "measure", "unfilled", "review", "instruments", "instruments_evidence",
                  "fact_domain", "fact_domain_evidence", "width", "width_evidence", "unit", "unit_of", "unit_evidence",
                  "unit_unknown", "unit_from", "competence", "place_of", "fatal", "fatal_other", "through",
                  "place_label", "compare", "century", "precision"})
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
class Through:
    """Where a column the dataset does not file is read from: the column of the same name of ``dataset`` (as the role
    files spell it: ``SIH-RD``), on the row that shares this record's ``key`` (a key of ``curation/joins.yml``)."""

    key: str
    dataset: str


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
    #: A code the source stores as a number (a DBF ``N`` field): its code system's width, the leading zeros the number
    #: lost (`canonical_codes` restores them for a join; the lake keeps the value as filed), with the measurement that
    #: shows it. SINAN's ID_UNIDADE: "477" is CNES 0000477, Hospital Oswaldo Cruz in its notifications' Recife.
    width: int | None = None
    width_evidence: str | None = None
    #: What a measure is measured in (`UNITS`), what a `count` counts, the document line it rests on; or why no document
    #: gives one (`unit_unknown`). A currency also names the column(s) of the month its amounts belong to (`competence`:
    #: year and month columns, or one AAAAMM column) and, when the currency changed inside its years, the first AAAAMM
    #: in the unit (`unit_from`).
    unit: str | None = None
    unit_of: str | None = None
    unit_evidence: str | None = None
    unit_unknown: str | None = None
    unit_from: int | None = None
    competence: tuple[str, ...] = ()
    #: For a place: whose it is (`PLACE_OF`). None for every other column.
    place_of: str | None = None
    #: For an outcome column: the codes that mean death by the event's own cause (``fatal``: SINAN's "Óbito pelo agravo
    #: notificado"; a yes/no death flag's "Sim") and death from another cause (``fatal_other``: "Óbito por outras
    #: causas"), each from the labels DATASUS publishes for the column. None: not declared (a consumer computing a case
    #: fatality finds no code to count and must say so, never match a label).
    fatal: tuple[str, ...] | None = None
    fatal_other: tuple[str, ...] | None = None
    #: For a column another dataset files on the same record (SIH-SP's sex and age, SIH-RD's): where it is read from
    through: Through | None = None
    #: For a stratum standing for a place that is not the subject's residence: that place, in words (`place_label`).
    place_label: str | None = None
    #: For a date written with a two-digit year (AAMMDD: SIM's ICD-9-era DATAOBITO, 950914): the century its years are of
    #: ('19'), the layout's fact a reader cannot measure (a six-digit date reads as MMAAAA as readily).
    century: str | None = None
    #: For a date that is not a day: ``month`` (a month in one column, AAAAMM: a competence) or ``year``. A day date's
    #: layout is measured (`normalize.time.date_layout`); what the column dates is not, and a reader treats a month apart
    #: (its year does not spill over a billing tail).
    precision: str | None = None

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
                "measure": self.measure, "unit": self.unit,
                "missing": None if self.missing is None else list(self.missing),
                "fatal": None if self.fatal is None else list(self.fatal),
                "fatal_other": None if self.fatal_other is None else list(self.fatal_other),
                "domain": None if self.domain is None else list(self.domain), "fact_domain": self.fact_domain,
                **({"fact_domain_evidence": self.fact_domain_evidence} if self.fact_domain else {}),
                **({"width": self.width, "width_evidence": self.width_evidence} if self.width else {}),
                **({"missing_unknown": self.missing_unknown} if self.missing_unknown else {}),
                **({"unfilled": list(self.unfilled)} if self.unfilled else {}),
                **({"unit_of": self.unit_of} if self.unit_of else {}),
                **({"unit_evidence": self.unit_evidence} if self.unit_evidence else {}),
                **({"unit_unknown": self.unit_unknown} if self.unit_unknown else {}),
                **({"unit_from": self.unit_from} if self.unit_from else {}),
                **({"competence": list(self.competence)} if self.competence else {}),
                **({"place_of": self.place_of} if self.place_of else {}),
                **({"place_label": self.place_label} if self.place_label else {}),
                **({"through": {"key": self.through.key, "dataset": self.through.dataset}} if self.through else {}),
                **({"instruments": list(self.instruments), "instruments_evidence": self.instruments_evidence}
                   if self.instruments else {})}


def roles_dir() -> Path:
    from ..config import curation_root

    return curation_root() / "roles"


@curated
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
        body = read_yaml(path, shared=True)
        dataset = str(body.get("dataset") or path.stem).upper()
        rows = []
        for column, spec in (body.get("columns") or {}).items():
            # the declared spelling is the column's name: a derived column is mixed-case
            # (IDADE_anos), and upper-casing it named a column no table has (PegaSUS, 2026-10-04)
            rows.append(_column(dataset, str(column), spec or {}, path.name))
        out[dataset] = tuple(rows)
    _agree_with_linkage(out)
    _competence_declared(out)
    _through_declared(out)
    return out


def _codes(spec: dict[str, Any], key: str, bad: Any) -> tuple[str, ...] | None:
    """A declared list of codes (``fatal``, ``fatal_other``): strings, each once, at least one."""
    if key not in spec:
        return None
    raw = spec[key]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise bad(f"{key} is the list of the outcome's codes, at least one (leave it out when no label decides)")
    if any(not isinstance(v, str) for v in raw):
        raise bad(f"{key} codes are strings ('2', not 2): a code is matched as filed")
    if len(set(raw)) != len(raw):
        raise bad(f"{key} repeats a code")
    return tuple(raw)


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
    if kind == "place" and model not in PLACE_MODELS:
        raise bad(f"a place is one of {sorted(PLACE_MODELS)}, not {model!r}")
    if model == "where" and kind != "place":
        raise bad("`where` is a place's model: where the event happened")
    place_of = spec.get("place_of")
    if kind == "place":
        if place_of not in PLACE_OF:
            raise bad(f"a place states whose it is, `place_of` one of {sorted(PLACE_OF)}, not {place_of!r}")
        if model == "stratum" and place_of != "subject":
            raise bad(f"a stratum is the subject's place, not the {place_of}'s")
        if model == "where" and place_of != "event":
            raise bad(f"a `where` is the place an event is placed at, not the {place_of}'s: a place that only the "
                      "record names (a registry office, a managing authority) is a mark")
    elif place_of is not None:
        raise bad("`place_of` is declared for places only")
    century = spec.get("century")
    if century is not None and (kind != "date" or not (isinstance(century, str) and century.isdigit() and len(century) == 2)):
        raise bad("`century` ('19', '20') is declared on a date written with a two-digit year")
    precision = spec.get("precision")
    if precision is not None and (kind != "date" or precision not in ("month", "year")):
        raise bad("`precision` (month, year) is declared on a date that is not a day")
    place_label = spec.get("place_label")
    if place_label is not None and not (kind == "place" and model == "stratum"):
        raise bad("`place_label` names the place a stratum stands for; it is declared on a place stratum only")
    through = None
    if "through" in spec:
        raw = spec["through"]
        if not isinstance(raw, dict) or set(raw) != {"key", "dataset"} or not all(
                isinstance(raw[k], str) and raw[k].strip() for k in raw):
            raise bad("`through` is {key: <a key of joins.yml>, dataset: <the dataset that files the column>}")
        if model in ("link_only", "excluded"):
            raise bad("a column reached through a key is a field a study reads, not a link key or a set-aside column")
        if spec.get("derived"):
            raise bad("a derived column is made from this dataset's own columns; it is not reached through a key")
        through = Through(raw["key"].strip().upper(), dataset_key(raw["dataset"].strip()))
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
    fatal, fatal_other = (_codes(spec, key, bad) for key in ("fatal", "fatal_other"))
    if (fatal is not None or fatal_other is not None) and kind != "category":
        raise bad("fatal and fatal_other are declared for a category (an outcome's codes)")
    if fatal_other is not None and fatal is None:
        raise bad("fatal_other without fatal: a case fatality counts the event's own deaths first")
    if fatal and fatal_other and set(fatal) & set(fatal_other):
        raise bad(f"{sorted(set(fatal) & set(fatal_other))} are both fatal and fatal_other: a code is one or the other")
    for name, codes in (("fatal", fatal), ("fatal_other", fatal_other)):
        if codes and missing and set(codes) & set(missing):
            raise bad(f"{sorted(set(codes) & set(missing))} are both {name} and missing: a death is a recorded outcome")
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
    width = spec.get("width")
    if width is not None and (not isinstance(width, int) or width < 1):
        raise bad(f"width {width!r} is the code system's number of characters")
    if width is not None and not str(spec.get("width_evidence") or "").strip():
        raise bad("a width needs its width_evidence: the layout's numeric field, or codes matched at that width")
    if width is None and "width_evidence" in spec:
        raise bad("width_evidence without width")
    unit = spec.get("unit")
    unit_unknown = spec.get("unit_unknown")
    unit_of = spec.get("unit_of")
    unit_from = spec.get("unit_from")
    competence = tuple(str(c) for c in spec.get("competence") or ())
    if unit is not None or unit_unknown is not None:
        if not measure:
            raise bad("a unit is declared for a measure (a number that is a quantity)")
        if unit is not None and unit_unknown is not None:
            raise bad("a unit is declared or unknown, not both")
    if unit is not None:
        if str(unit) not in UNITS:
            raise bad(f"unit {unit!r} not in {sorted(UNITS)}")
        if not str(spec.get("unit_evidence") or "").strip():
            raise bad("a unit needs its unit_evidence: the layout or dictionary line it rests on")
    elif "unit_evidence" in spec or "unit_of" in spec or "unit_from" in spec or "competence" in spec:
        raise bad("unit_evidence, unit_of, unit_from and competence belong to a declared unit")
    if unit_unknown is not None and not str(unit_unknown).strip():
        raise bad("unit_unknown states why no document gives the unit")
    if (unit == "count") != (unit_of is not None):
        raise bad("`unit_of` says what a `count` counts, and only a `count` has one")
    if unit_of is not None and not str(unit_of).strip():
        raise bad("unit_of states what is counted")
    if (unit in CURRENCIES) != bool(competence):
        raise bad("an amount of money names the column(s) of the month it belongs to (`competence`), and nothing else does")
    if len(competence) > 2:
        raise bad(f"competence is a year and a month column or one AAAAMM column, not {list(competence)}")
    if unit_from is not None and (unit not in CURRENCIES or not isinstance(unit_from, int) or month_of(unit_from) is None
                                  or not 1900 <= cast(int, year_of(unit_from)) <= 2100):
        raise bad(f"unit_from {unit_from!r} is the first AAAAMM an amount is in the unit, for a currency")
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
                      " ".join(str(spec["fact_domain_evidence"]).split()) if fact is not None else None,
                      int(width) if width is not None else None,
                      " ".join(str(spec["width_evidence"]).split()) if width is not None else None,
                      str(unit) if unit is not None else None,
                      " ".join(str(unit_of).split()) if unit_of is not None else None,
                      " ".join(str(spec["unit_evidence"]).split()) if unit is not None else None,
                      " ".join(str(unit_unknown).split()) if unit_unknown is not None else None,
                      int(unit_from) if unit_from is not None else None, competence,
                      str(place_of) if place_of is not None else None, fatal, fatal_other, through,
                      place_label=" ".join(str(place_label).split()) if place_label else None,
                      century=century, precision=precision)


def _competence_declared(declared: dict[str, tuple[ColumnRole, ...]]) -> None:
    """Every column a currency names as its competence is a date column of the same dataset: a month the caller can read."""
    for dataset, columns in declared.items():
        kinds = {c.column.upper(): c.kind for c in columns}
        for c in columns:
            for month in c.competence:
                if kinds.get(month.upper()) != "date":
                    raise ValueError(f"roles/{dataset}.yml: {c.column} names {month} as its competence, which is not a declared date column")


def _through_declared(declared: dict[str, tuple[ColumnRole, ...]]) -> None:
    """Every column reached through a key is the same column of a dataset that files it: that dataset declares it with
    the same role and kind (a sex is a sex) and files it itself (no chain of keys), and the key of ``joins.yml`` has
    this dataset and that one as members, so the columns that join are declared once, there."""
    from ..ontology import Ontology

    keys = Ontology.load().keys
    for dataset, columns in declared.items():
        for c in columns:
            if c.through is None:
                continue
            where = f"roles/{dataset}.yml: {c.column}"
            try:
                source = _declared_key_in(declared, c.through.dataset)
            except KeyError:
                raise ValueError(f"{where}: reached through {c.through.dataset}, which declares no column roles") from None
            theirs = next((s for s in declared[source] if s.column == c.column), None)
            if theirs is None:
                raise ValueError(f"{where}: {source} declares no column of that name to read it from")
            lo, hi = c.years
            if (lo is not None and theirs.years[0] is not None and lo < theirs.years[0]) or (
                    hi is not None and theirs.years[1] is not None and hi > theirs.years[1]):
                raise ValueError(f"{where}: is declared for {list(c.years)} but {source} files it for {list(theirs.years)}")
            if theirs.through is not None:
                raise ValueError(f"{where}: {source}'s {c.column} is itself reached through a key; name the dataset that files it")
            if (theirs.role, theirs.kind) != (c.role, c.kind):
                raise ValueError(f"{where}: is {c.role} ({c.kind}) but {source}'s is {theirs.role} ({theirs.kind}): "
                                 "one column states one property")
            key = keys.get(c.through.key)
            if key is None:
                raise ValueError(f"{where}: curation/joins.yml declares no key {c.through.key}")
            for name in (dataset, source):
                if key.member_for(name) is None:
                    raise ValueError(f"{where}: {name} is not a member of the {key.name} key of curation/joins.yml")


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
    keys = [dataset_key(dataset)] if dataset else sorted(declared)
    return [(d, c.column) for d in keys for c in declared.get(d, ())
            if (c.kind == "category" or c.model in FIELD_MODELS) and c.fact_domain is None]


def undeclared_units(dataset: str | None = None) -> list[tuple[str, str]]:
    """The measures that state neither a ``unit`` nor why none is known (``(dataset, column)``), for one dataset or all:
    every number that is a quantity (``measure``) and that a study reads (``FIELD_MODELS``). The list a reviewer closes,
    never a default."""
    declared = load_column_roles()
    keys = [dataset_key(dataset)] if dataset else sorted(declared)
    return [(d, c.column) for d in keys for c in declared.get(d, ())
            if c.kind == "number" and c.measure and c.model in FIELD_MODELS and c.unit is None and c.unit_unknown is None]


def roles(dataset: str, period: object = None) -> list[dict[str, Any]]:
    """The role of every column of a dataset, as rows (``pegasus-data roles <dataset>``).

    A role can sit on a different column in each layout generation (SIM-DOFET's residence is MUNIRES in 1979-1995 and
    CODMUNRES from 1996; both rows are returned, each with its ``first_year``/``last_year``). A caller that reads one
    year must not collapse them by role: pass ``period`` (a year, or a ``(first, last)`` pair / range / list of years)
    and only the columns whose years intersect it are returned; a column with no declared years always is.

    A measure's row carries ``unit`` (one of :data:`UNITS`, or None), with ``unit_evidence`` and, for a ``count``, ``unit_of``;
    a measure without one says why in ``unit_unknown``. An amount of money also carries ``competence`` (the column(s) of the
    month it belongs to) and, if its currency changed inside its years, ``unit_from`` (the first AAAAMM in the unit)."""
    rows = _all_roles(dataset)
    if period is None:
        return rows
    ys = [int(period)] if isinstance(period, (int, str)) else [int(y) for y in cast(Iterable[Any], period)]
    lo, hi = min(ys), max(ys)
    return [r for r in rows if (r["first_year"] is None or r["first_year"] <= hi)
            and (r["last_year"] is None or r["last_year"] >= lo)]


def declared_key(dataset: str) -> str:
    """The key of ``dataset`` in the role files (``SIM-DO``, ``SIH-RD`` for ``SIHSUS-RD``, ``SINAN-*`` for every
    SINAN agravo's notification block); ``KeyError`` when no role file covers it."""
    return _declared_key_in(load_column_roles(), dataset)


def _declared_key_in(declared: dict[str, tuple[ColumnRole, ...]], dataset: str) -> str:
    """`declared_key` over the role files already read (the loader checks them before it returns them)."""
    from .._request import parse_dataset

    key = dataset_key(dataset)
    if key not in declared:
        from fnmatch import fnmatchcase

        from .curation import system_spellings

        system, series = parse_dataset(dataset)
        # the system under each of its declared spellings (SIHSUS is SIH), with its series or alone (CIHA-CIHA is CIHA)
        spellings = system_spellings(system) or [system]
        candidates = [*(f"{sp}-{series}" for sp in spellings), *spellings, series]
        key = next((c for c in candidates if c in declared), key)
        if key not in declared:
            # a roles file declared for a pattern of datasets (SINAN-*: the notification block every agravo carries)
            key = next((k for k in sorted(declared)
                        if "*" in k and any(fnmatchcase(c, k) for c in candidates)),  # type: ignore[type-var]  # suspected bug: series None puts None in candidates
                       key)
    if key not in declared:
        raise KeyError(f"no column roles declared for {dataset!r}; declared: {sorted(declared)}")
    return key


def declared_columns(dataset: str) -> tuple[ColumnRole, ...]:
    """The declared columns of ``dataset`` (as :func:`declared_key` finds them), each with its role."""
    return load_column_roles()[declared_key(dataset)]


def _all_roles(dataset: str) -> list[dict[str, Any]]:
    return [c.as_dict() for c in declared_columns(dataset)]


def column_of(dataset: str, role: str) -> str:
    """The one column of ``dataset`` that states ``role`` (its ``role`` or an ``also``): a study names the property it
    needs, never the column. More than one, or none, raises."""
    found = sorted({c.column for c in declared_columns(dataset) if c.role == role or role in (c.also or ())})
    if len(found) != 1:
        raise KeyError(f"{dataset}: {len(found)} columns state {role!r} ({found}); one is needed")
    return found[0]


def facility_code_field(dataset: str) -> str | None:
    """The column that holds the record's own establishment as a CNES code: the one column of the dataset typed
    ``kind: institution`` with the CNES register's codelist (``CADGERBR``); when a layout files several (APAC's
    executing and requesting units, SINAN's notifying and treating units), the one whose role property is the
    record's own ``facility`` or ``cnes``. None when the roles name none or leave it ambiguous: the caller says so
    and asks for the column, it does not guess one."""
    return _institution_field(dataset, "CADGERBR", ("facility", "cnes"))


def facility_cnpj_field(dataset: str) -> str | None:
    """The column that holds the record's own establishment as a CNPJ (SIH's ``CGC_HOSP``, APAC's ``AP_CNPJCPF``,
    BPA's ``PA_CNPJCPF``): the column with the role ``facility.cnpj`` (not the maintainer's). None when the dataset
    files none."""
    try:
        found = {c.column for c in declared_columns(dataset) if c.role == "facility.cnpj"}
    except KeyError:
        return None
    return found.pop() if len(found) == 1 else None


def _institution_field(dataset: str, codelist: str, properties: tuple[str, ...]) -> str | None:
    try:
        columns = declared_columns(dataset)
    except KeyError:
        return None
    found = [c.column for c in columns if c.kind == "institution" and codelist in c.codelists]
    if len(found) > 1:
        found = [c.column for c in columns if c.column in found and c.property in properties]
    return found[0] if len(set(found)) == 1 else None
