"""The curated variable dictionary: the door for human judgement (§4).

Three times this design created a slot for a person to write into and then left
no way to reach it. ``SOURCE_AUTHORITY['manual'] = 0`` outranked every extracted
source, and nothing could produce a manual entry. ``'layout_doc'`` was declared
authoritative before anything emitted one. The prefix→system map deliberately
holds its first answer against contradicting evidence — correctly, because a
reorganisation and a shared prefix are indistinguishable from one crawl — and
offered no way to adjudicate. All three are the same missing thing.

The split between here and SQLite is by *provenance*, not by size. The extracted
dictionary is machine output: millions of code→label rows, regenerable from the
FTP tree, and nobody should hand-edit it. What a variable **means** is the
opposite — a few thousand assertions, each made by a person or read out of a
document, none of it recomputable. Assertions belong in version control where a
diff shows who changed an interpretation and when. So ``curation/*.yml`` is the
source of truth for meaning, this module loads it, and the catalog holds the
result for querying alongside everything else.

Entries carry the rung of evidence that produced them (§4.5). An inferred
description is useful; an inferred description presented as documented is
precisely the failure this module exists to prevent, so ``source='inferred'``
requires the reasoning to be written out and refuses to load without it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..catalog.store import CatalogStore, utcnow
from .epoch import curated, curation_fingerprint

#: Rungs of evidence, best first (§4.5). Mirrors ``SOURCE_AUTHORITY`` but names
#: the *documentation* sources rather than the value-label ones.
DOC_SOURCES: tuple[str, ...] = ("manual", "layout_doc", "def", "web", "inferred")

#: A source that asserts rather than reports has to say who is asserting.
_NEEDS_AUTHOR = {"manual", "inferred"}

_CODE_SYSTEMS = {"external", "internal", "none"}


class CurationError(ValueError):
    """A curation file cannot be loaded. Raised rather than partially applied.

    Loading half a file would leave the catalog in a state no file describes,
    which is the one thing version-controlled curation is supposed to rule out.
    """


@dataclass(slots=True)
class VariableDoc:
    system: str
    field_name: str
    official_name: str | None = None
    translated_name: str | None = None
    description: str | None = None
    code_system: str | None = None
    codelist: str | None = None
    #: Extra tables bound to the same field. A column whose classification
    #: changed under it needs both, and exact-width matching (§6.2) selects
    #: per row rather than per era.
    codelists: list[str] = field(default_factory=list)
    multi_valued: bool = False
    token_rule: dict[str, Any] | None = None
    depends_on: list[str] = field(default_factory=list)
    modifies: str | None = None
    derived: list[dict[str, Any]] = field(default_factory=list)
    notes: str | None = None
    #: Recorded when a column's *classification* changed rather than its data
    #: going bad — SIM ran on CID-9 before the CID-10 changeover, and both are
    #: bound because the vintages overlap on the tree.
    vintage_note: str | None = None
    source: str = "manual"
    source_ref: str | None = None
    asserted_by: str | None = None
    reasoning: str | None = None
    #: A code table written in the curation itself, for coded columns whose
    #: table exists only in a document (a SINAN data dictionary, an INCA form):
    #: ``{"1": "Sim", "2": "Não", "9": "Ignorado"}``. Served as the codelist
    #: ``CURATED.<SYSTEM>.<FIELD>`` (ADR-0079).
    codes: dict[str, str] | None = None
    #: ``codelists`` are ALTERNATIVES, one per form, not tables applied
    #: together: SINAN's CLASSI_FIN is CLASINTO on the poisoning form and
    #: CLASSHEPAT on the hepatitis form. Each family picks one by measurement
    #: after its own form's dictionary (ADR-0080).
    per_form: bool = False
    #: Columns whose concatenated values are this column's lookup key, in
    #: order, when its code only means something with another column's
    #: (CNES CLASS_SR: SERV_ESP + CLASS_SR, ADR-0088).
    key: list[str] = field(default_factory=list)
    #: A column of the same row that NAMES this code: CNES-EP files IDEQUIPE
    #: beside NOME_EQP, ID_AREA beside NOMEAREA (ADR-0090).
    label_from: str | None = None
    #: A label reached THROUGH another column of the row: SIH CNPJ_MANT is the
    #: maintainer of the row's establishment, named by the registry's
    #: ``maintainer`` for the row's CNES: {column: CNES, table: CADGERBR,
    #: field: maintainer} (ADR-0094).
    label_via: dict[str, str | list[str]] | None = None

    def as_row(self) -> tuple[object, ...]:
        return (
            self.system, self.field_name, self.official_name, self.translated_name,
            self.description, self.code_system,
            ",".join([self.codelist, *self.codelists]) if self.codelist else None,
            int(self.multi_valued),
            json.dumps(self.token_rule) if self.token_rule else None,
            json.dumps(self.depends_on) if self.depends_on else None,
            self.modifies,
            json.dumps(self.derived) if self.derived else None,
            self.notes, self.vintage_note, self.source, self.source_ref,
            self.asserted_by, utcnow(), self.reasoning, int(self.per_form),
            json.dumps(self.key) if self.key else None,
            self.label_from,
            json.dumps(self.label_via) if self.label_via else None,
        )


@dataclass(slots=True)
class DatasetDoc:
    dataset_id: str
    system: str | None = None
    series: str | None = None
    what_one_row_is: str | None = None
    unit_of_analysis: str | None = None
    known_biases: str | None = None
    gotchas: list[str] = field(default_factory=list)
    source: str = "manual"
    source_ref: str | None = None
    asserted_by: str | None = None

    def as_row(self) -> tuple[object, ...]:
        return (
            self.dataset_id, self.system, self.series, self.what_one_row_is,
            self.unit_of_analysis, self.known_biases,
            json.dumps(self.gotchas) if self.gotchas else None,
            self.source, self.source_ref, self.asserted_by, utcnow(),
        )


# ------------------------------------------------------------------- parsing


def _require_yaml() -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise CurationError(
            "curation files are YAML; install pyyaml (pip install pyyaml)"
        ) from exc
    return yaml


def _clean(value: object) -> str | None:
    """Collapse YAML block scalars to single-line prose."""
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _all_codelists(body: Mapping[str, Any]) -> list[str]:
    """``codelist:`` and/or ``codelists:``, normalised to one ordered list."""
    named: list[str] = []
    single = body.get("codelist")
    if single:
        named.append(str(single).upper())
    extra = body.get("codelists") or []
    if isinstance(extra, str):
        extra = [extra]
    for name in extra:
        upper = str(name).upper()
        if upper not in named:
            named.append(upper)
    return named


def _first_codelist(body: Mapping[str, Any]) -> str | None:
    names = _all_codelists(body)
    return names[0] if names else None


def _extra_codelists(body: Mapping[str, Any]) -> list[str]:
    return _all_codelists(body)[1:]


def parse_variable_file(path: Path, data: dict[str, Any]) -> list[VariableDoc]:
    """One file per (system, series): a ``system:`` key and a ``variables:`` map."""
    system = data.get("system")
    if not system:
        raise CurationError(f"{path.name}: missing top-level 'system:'")
    variables = data.get("variables") or {}
    if not isinstance(variables, dict):
        raise CurationError(f"{path.name}: 'variables:' must be a mapping of NAME -> fields")

    default_source = data.get("source", "manual")
    default_ref = data.get("source_ref")
    default_author = data.get("asserted_by")

    out: list[VariableDoc] = []
    for name, body in variables.items():
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise CurationError(f"{path.name}: {name}: expected a mapping, got {type(body).__name__}")
        source = body.get("source", default_source)
        if source not in DOC_SOURCES:
            raise CurationError(
                f"{path.name}: {name}: source '{source}' is not one of {list(DOC_SOURCES)}"
            )
        code_system = body.get("code_system")
        if code_system is not None and code_system not in _CODE_SYSTEMS:
            raise CurationError(
                f"{path.name}: {name}: code_system '{code_system}' is not one of "
                f"{sorted(_CODE_SYSTEMS)}"
            )
        author = body.get("asserted_by", default_author)
        reasoning = _clean(body.get("reasoning"))
        if source in _NEEDS_AUTHOR and not author:
            raise CurationError(
                f"{path.name}: {name}: source '{source}' asserts rather than reports, "
                "so it needs 'asserted_by'"
            )
        if source == "inferred" and not reasoning:
            raise CurationError(
                f"{path.name}: {name}: an inferred meaning must carry 'reasoning'. "
                "An inferred description presented as documented is the failure this "
                "module exists to prevent."
            )
        token_rule = body.get("token_rule")
        if body.get("multi_valued") and not token_rule:
            raise CurationError(
                f"{path.name}: {name}: multi_valued needs a token_rule saying how to split "
                "(e.g. {width: 4} or {delimiter: ';'})"
            )
        if token_rule is not None and (
            not isinstance(token_rule, dict) or not ({"width", "delimiter"} & set(token_rule))
        ):
            raise CurationError(
                f"{path.name}: {name}: token_rule must be a mapping with 'width' or 'delimiter'"
            )
        depends_on = body.get("depends_on") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        codes = _parse_codes(path, str(name), body.get("codes"))
        codelist = _first_codelist(body)
        extra_codelists = _extra_codelists(body)
        if codes:
            # Inline codes are the column's own table and come first; a table
            # it was also bound to stays as a fallback (ADR-0079).
            if codelist:
                extra_codelists = [codelist, *extra_codelists]
            codelist = curated_codelist_id(str(system), str(name))
        if codes and code_system in (None, "none"):
            code_system = "internal"
        out.append(
            VariableDoc(
                system=str(system).upper(),
                field_name=str(name).upper(),
                official_name=_clean(body.get("official_name")),
                translated_name=_clean(body.get("translated_name")),
                description=_clean(body.get("description")),
                code_system=code_system,
                codelist=codelist,
                codelists=extra_codelists,
                multi_valued=bool(body.get("multi_valued", False)),
                token_rule=token_rule,
                depends_on=[str(d).upper() for d in depends_on],
                modifies=(str(body["modifies"]).upper() if body.get("modifies") else None),
                derived=list(body.get("derived") or []),
                notes=_clean(body.get("notes")),
                vintage_note=_clean(body.get("vintage_note")),
                source=source,
                source_ref=body.get("source_ref", default_ref),
                asserted_by=author,
                reasoning=reasoning,
                codes=codes,
                per_form=bool(body.get("per_form", False)),
                key=[str(k).upper() for k in (body.get("key") or [])],
                label_from=(str(body["label_from"]).upper() if body.get("label_from") else None),
                label_via=(
                    {k: ([str(x) for x in v] if isinstance(v, list) else str(v)) for k, v in body["label_via"].items()}
                    if body.get("label_via") else None
                ),
            )
        )
    return out


#: The prefix of a codelist written inline in the curation (ADR-0079).
CURATED_PREFIX = "CURATED."


def curated_codelist_id(system: str, field_name: str) -> str:
    return f"{CURATED_PREFIX}{system.upper()}.{field_name.upper()}"


def _parse_codes(path: Path, name: str, raw: object) -> dict[str, str] | None:
    """``codes:`` as ``{code: label}``; codes are kept as written ("01" is not "1").

    A label is text, or a mapping ``{label, from, to}``: a code the records hold only in some years and no layout names
    (``from``/``to`` are ``AAAAMM``, either may be left out). It decodes in the files of those years only, and stays
    undecoded, visibly, in any other (`_code_windows`)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw:
        raise CurationError(f"{path.name}: {name}: codes must be a non-empty mapping of code to label")
    out: dict[str, str] = {}
    for code, label in raw.items():
        text = label.get("label") if isinstance(label, dict) else label
        if text is None or isinstance(text, (dict, list)) or not str(text).strip():
            raise CurationError(f"{path.name}: {name}: code {code!r} needs a text label")
        out[str(code).strip()] = str(text).strip()
    return out


def _code_windows(path: Path, name: str, raw: object) -> dict[str, tuple[str, str]]:
    """The years a ``codes:`` entry is windowed to: ``{code: (from, to)}`` as ``AAAAMM`` ('' = open), for the entries
    written ``{label, from, to}``; a code with no window decodes in every year."""
    out: dict[str, tuple[str, str]] = {}
    for code, label in (raw or {}).items() if isinstance(raw, dict) else ():
        if not isinstance(label, dict):
            continue
        unknown = set(label) - {"label", "from", "to"}
        if unknown:
            raise CurationError(f"{path.name}: {name}: code {code!r}: unknown keys {sorted(unknown)} "
                                "(a coded entry is {label, from, to})")
        lo, hi = (str(label.get(k) or "") for k in ("from", "to"))
        if not (lo or hi):
            raise CurationError(f"{path.name}: {name}: code {code!r} names no window: write its label as text")
        for bound in (lo, hi):
            if bound and not re.fullmatch(r"(1[89]|20)\d\d(0[1-9]|1[0-2])", bound):
                raise CurationError(f"{path.name}: {name}: code {code!r}: {bound!r} is no AAAAMM month")
        if lo and hi and lo > hi:
            raise CurationError(f"{path.name}: {name}: code {code!r}: the window ends before it begins")
        out[str(code).strip()] = (lo, hi)
    return out


def read_yaml(path: Path, *, shared: bool = False) -> dict[str, Any]:
    """One curation file, parsed once per process per version of the file.

    Every curation reader parsed all 157 files itself, with the pure-Python
    loader: 23 of a 43-second first query was YAML (profiled 2026-09-29,
    SIASUS-ACF 2023-01). libyaml's loader reads the same documents ~10x faster,
    and the cache is keyed on the file's mtime so an edited file is re-read.
    Callers get a fresh copy: the parsed mapping is not theirs to mutate. A loader that only reads it
    and keeps none of its mutable parts passes ``shared=True`` and gets the cached mapping itself, without
    the deep copy (17 ms for ``codes/sinan.yml``): it must not edit it, nor hand out its lists and mappings.
    """
    stat = path.stat()
    doc = _parsed_yaml(str(path), stat.st_mtime_ns, stat.st_size)
    return doc if shared else copy.deepcopy(doc)


def load_yaml_text(text: str) -> Any:
    """YAML text, parsed by libyaml's safe loader when it is installed (the pure-Python one is ~10x slower)."""
    yaml = _require_yaml()
    return yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))  # noqa: S506 - a safe loader


#: Set once a process has removed the pickles of the layout before one directory per file.
_YAML_CACHE_SWEPT = False


def _yaml_cache_dir() -> Path | None:
    """The directory of parsed-YAML pickles, or None when it cannot be trusted: a pickle is code, so a directory
    another user owns (a shared ``/tmp``) is not read."""
    import tempfile

    folder = Path(tempfile.gettempdir()) / "pegasus_data_yaml"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "getuid") and folder.stat().st_uid != os.getuid():
            return None
    except OSError:
        return None
    return folder


@lru_cache(maxsize=1024)
def _parsed_yaml(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    """The parsed file, from a pickle kept beside the system's temp files when this version of it (path, mtime, size)
    was parsed before by any process: libyaml parses, but builds every object in Python, and each fresh process (a
    CLI command, a study's lane) paid it again (a fifth of a first query, `event_types` 2.2 s, 2026-10-11).

    One directory per file holds its pickle, so writing a new version removes the old ones (the cache held 2,279
    versions of 365 files, 44 MB, and never shrank); a pickle that cannot be read for any reason is a miss."""
    import pickle

    global _YAML_CACHE_SWEPT
    yaml = _require_yaml()
    folder = _yaml_cache_dir()
    cached = None
    if folder is not None:
        tag = hashlib.sha1(f"{mtime_ns}|{size}|{yaml.__version__}".encode()).hexdigest()
        cached = folder / hashlib.sha1(path.encode()).hexdigest() / f"{tag}.pickle"
        try:
            with open(cached, "rb") as handle:
                return pickle.load(handle)  # noqa: S301 - written by this function from the project's own files
        except Exception:  # noqa: BLE001 - absent, truncated, or pickled by a version whose classes are gone: re-parse
            pass
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    with open(path, encoding="utf-8") as handle:
        doc = yaml.load(handle, Loader=loader) or {}  # noqa: S506 - a safe loader
    if cached is not None and folder is not None:
        try:
            if not _YAML_CACHE_SWEPT:         # the flat layout before one directory per file
                _YAML_CACHE_SWEPT = True
                for old in folder.glob("*.pickle"):
                    old.unlink(missing_ok=True)
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(f".{os.getpid()}.tmp")
            with open(tmp, "wb") as handle:
                pickle.dump(doc, handle, protocol=pickle.HIGHEST_PROTOCOL)
            tmp.replace(cached)
            for version in cached.parent.iterdir():     # another version of this file is out of date
                if version != cached and version.suffix == ".pickle":
                    version.unlink(missing_ok=True)
        except OSError:                   # a read-only or full temp directory, a file in use: parsed each time, never wrong
            pass
    return doc


@curated
def _inline_tables() -> dict[str, tuple[dict[str, str], dict[str, tuple[str, str]]]]:
    """Every inline code table in the package's own curation, by codelist id: its ``code -> label`` and the validity
    windows of the codes written with one (`_code_windows`).

    Read from the shipped YAML rather than the catalog, so a fresh install
    labels these columns with no catalog, lake or label-pack rebuild.
    """
    from ..config import curation_root

    root = curation_root()
    out: dict[str, tuple[dict[str, str], dict[str, tuple[str, str]]]] = {}
    for path in sorted(root.glob("variables/**/*.yml")):
        data = read_yaml(path, shared=True)
        system = str(data.get("system") or "")
        for name, body in (data.get("variables") or {}).items():
            if isinstance(body, dict) and body.get("codes"):
                codes = _parse_codes(path, str(name), body["codes"])
                if codes:
                    out[curated_codelist_id(system, str(name))] = (
                        codes, _code_windows(path, str(name), body["codes"]))
    # the code lists of the sources the intake mechanism reads (ADR-0162) are written in curation/intake.yml, and served the same way
    from ..intake import curation_docs

    for data in curation_docs(root)[0]:
        for name, body in (data.get("variables") or {}).items():
            if isinstance(body, dict) and body.get("codes"):
                codes = _parse_codes(root / "intake.yml", str(name), body["codes"])
                if codes:
                    out[curated_codelist_id(str(data["system"]), str(name))] = (
                        codes, _code_windows(root / "intake.yml", str(name), body["codes"]))
    return out


@curated
def _harvested_fields() -> dict[str, dict[str, Any]]:
    """Every field the official dictionaries document, per form: its layout (``type``: date, number or text;
    ``width``; the form's ``label``; a code ``table`` it names) and its ``codes``.

    ``curation/codes/<system>.yml`` is generated by ``scripts/harvest_codes.py``
    and keyed ``series -> field``, because the same column name carries
    different codes on different forms (ADR-0079). Keys are
    ``CURATED.<SYSTEM>.<SERIES>.<FIELD>``.
    """
    from ..config import curation_root

    root = curation_root() / "codes"
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.yml")):
        data = read_yaml(path)
        system = str(data.get("system") or "").upper()
        for series, fields in (data.get("series") or {}).items():
            for name, body in (fields or {}).items():
                out[f"{CURATED_PREFIX}{system}.{str(series).upper()}.{str(name).upper()}"] = dict(body or {})
    return out


@curated
def _harvested_codelists() -> dict[str, dict[str, str]]:
    """The harvested fields' code tables (`_harvested_fields`); ids ``CURATED.<SYSTEM>.<SERIES>.<FIELD>``."""
    out: dict[str, dict[str, str]] = {}
    for key, body in _harvested_fields().items():
        codes = {str(k): str(v) for k, v in (body.get("codes") or {}).items()}
        if codes:
            out[key] = codes
    return out


def harvested_field(system: str, series: str, field_name: str) -> dict[str, Any] | None:
    """The form's own documentation of a column (`_harvested_fields`), if its dictionary was harvested."""
    return _harvested_fields().get(f"{CURATED_PREFIX}{system.upper()}.{series.upper()}.{field_name.upper()}")


def form_types_a_date(system: str, series: str, field_name: str) -> bool:
    """The form's own dictionary types this column a date and prints it no code table: it is never decoded, whatever a
    system-wide curated doc says (SINAN's TRATAMENTO is the treatment's start date on visceral leishmaniasis and the type
    of entry on tuberculosis, and a doc is one per system and column, not per form)."""
    form = harvested_field(system, series, field_name) if series else None
    return bool(form) and form.get("type") == "date" and not form.get("codes")


def harvested_codelist(system: str, series: str, field_name: str) -> str | None:
    """The id of the form's own dictionary table for this column, if one was harvested."""
    key = f"{CURATED_PREFIX}{system.upper()}.{series.upper()}.{field_name.upper()}"
    return key if key in _harvested_codelists() else None


def inline_codelist(codelist: str) -> dict[str, str] | None:
    """The ``code -> label`` of a ``CURATED.`` codelist (inline or harvested), or None: every code of it, whichever
    years it is windowed to (`inline_windows`)."""
    key = codelist.upper()
    if not key.startswith(CURATED_PREFIX):
        return None
    inline = _inline_tables().get(key)
    return (inline[0] if inline else None) or _harvested_codelists().get(key)


def inline_windows(codelist: str) -> dict[str, tuple[str, str]]:
    """``code -> (from, to)`` (``AAAAMM``, '' open) of the codes of an inline codelist that decode only in some years;
    empty for a list whose codes all decode in every year."""
    inline = _inline_tables().get(codelist.upper())
    return dict(inline[1]) if inline else {}


def parse_datasets_file(path: Path, data: dict[str, Any]) -> list[DatasetDoc]:
    datasets = data.get("datasets") or {}
    out: list[DatasetDoc] = []
    for dataset_id, body in datasets.items():
        body = body or {}
        if not any(body.get(k) for k in ("what_one_row_is", "unit_of_analysis", "known_biases", "gotchas")):
            # A key that only declares event types (SIM-DO, SINASC-DN, ...) says nothing about what a row means; it
            # would be stored as a dataset with no system, series or prose, and listed by search as an empty context.
            continue
        gotchas = body.get("gotchas") or []
        if isinstance(gotchas, str):
            gotchas = [gotchas]
        out.append(
            DatasetDoc(
                dataset_id=str(dataset_id).upper(),
                system=body.get("system"),
                series=body.get("series"),
                what_one_row_is=_clean(body.get("what_one_row_is")),
                unit_of_analysis=_clean(body.get("unit_of_analysis")),
                known_biases=_clean(body.get("known_biases")),
                gotchas=[_clean(g) or "" for g in gotchas],
                source=body.get("source", "manual"),
                source_ref=body.get("source_ref"),
                asserted_by=body.get("asserted_by"),
            )
        )
    return out


#: Curation files this loader must not read.
#:
#: ``ontology.yml`` declares dataset *identity* — what SIH.RD IS — and is read
#: directly by :class:`~pegasus_data.ontology.Ontology`. It also happens to use a
#: top-level ``datasets:`` key, so without this guard the dataset-docs loader
#: swept it up and wrote 95 rows carrying nothing but an id: identity has no
#: ``what_one_row_is``, and the shapes do not match. Two stores for one concept
#: is how they drift.
#:
#: The division: ``ontology.yml`` says what a dataset is, ``datasets.yml`` says
#: what one of its rows means. They are keyed differently on purpose
#: (``SIH.RD`` against ``SIHSUS_RD``) and :func:`pegasus_data._info.info` joins
#: them on either.
_NOT_CURATION = frozenset({"ontology.yml", "joins.yml", "codelists.yml", "intake.yml"})


def iter_curation_files(root: Path) -> Iterator[Path]:
    """Every curation file, variables first.

    ``variables/`` is organised one folder per system and one file per dataset
    (``variables/sinan/botu.yml``), so the walk has to recurse. It used to glob
    one level, which was right when the folder was 128 flat files and would
    silently have loaded nothing once they moved.
    """
    seen: set[Path] = set()
    for pattern in (
        "variables/**/*.yml", "variables/**/*.yaml",
        "datasets/**/*.yml", "datasets/**/*.yaml",
        "*.yml", "*.yaml",
    ):
        for path in sorted(root.glob(pattern)):
            if path.name in _NOT_CURATION or path in seen:
                continue
            seen.add(path)
            yield path


# -------------------------------------------------------------------- loading


def curation_is_current(catalog: CatalogStore, root: Path) -> bool:
    """Has THIS curation already been loaded into THIS catalog?

    The check used to be ``variable_docs is empty``, which is true exactly once
    in a catalog's life. Every later change to the shipped YAML — a new column,
    a corrected codelist — then never reached anyone who had already run the
    package once.
    """
    try:
        rows = catalog.query("SELECT fingerprint FROM curation_state WHERE id = 1")
    except Exception:  # noqa: BLE001 - a catalog older than the table
        return False
    return bool(rows) and str(rows[0]["fingerprint"]) == curation_fingerprint(root)


def note_curation_loaded(catalog: CatalogStore, root: Path) -> None:
    catalog.execute(
        "INSERT INTO curation_state (id, fingerprint, applied_at) VALUES (1,?,?)"
        " ON CONFLICT(id) DO UPDATE SET fingerprint = excluded.fingerprint,"
        " applied_at = excluded.applied_at",
        (curation_fingerprint(root), utcnow()),
    )


def ensure_current(catalog: CatalogStore, root: Path) -> dict[str, object] | None:
    """Load the shipped curation when it changed since this catalog last loaded it.

    Returns what was loaded, or None when the catalog was already current. Every
    reader of curated text goes through here: ``fetch`` did, ``info`` did not,
    and printed a dataset's superseded gotchas until the next query (2026-09-30).
    """
    if curation_is_current(catalog, root):
        return None
    with catalog.write():
        # Every study lane calls this, and a YAML edit makes the catalog stale for all of them at once: the first to
        # get the write lock loads, the others find it current when they get theirs. One transaction, so no
        # reader sees a catalog between the deletion of the curated rows and their insertion.
        if curation_is_current(catalog, root):
            return None
        loaded = load_curation(catalog, root)
        note_curation_loaded(catalog, root)
    return loaded


def load_curation(catalog: CatalogStore, root: Path) -> dict[str, object]:
    """Seed the catalog from ``curation/``, in one transaction. Replaces what the files own."""
    with catalog.write():
        return _load_curation(catalog, root)


def _load_curation(catalog: CatalogStore, root: Path) -> dict[str, object]:
    """`load_curation`'s work: replaces what the files own.

    Curated rows are *replaced* rather than merged, for the same reason every
    other derived table is: an entry deleted from the YAML has to disappear from
    the catalog, or the file stops being the source of truth it is supposed to be.
    Only rows whose source is one of the curated rungs are touched — anything the
    harvesters wrote is left alone.
    """
    # The settled rulings and the named gaps are properties of this module, not
    # of whatever files happen to be on disk, so they are recorded even when the
    # curation directory is absent. A settled "no" that only appears when someone
    # remembers to ship a YAML file is not settled.
    _record_settled_rulings(catalog)
    _record_open_gaps(catalog)
    if not root.is_dir():
        return {"curation_root": str(root), "files": 0, "variables": 0, "datasets": 0}

    variables: list[VariableDoc] = []
    datasets: list[DatasetDoc] = []
    systems_map: dict[str, str] = {}
    files = 0
    for path in iter_curation_files(root):
        try:
            data = read_yaml(path)
        except Exception as exc:
            raise CurationError(f"{path}: {exc}") from exc
        if not isinstance(data, dict):
            raise CurationError(f"{path}: expected a mapping at the top level")
        files += 1
        if "variables" in data:
            variables.extend(parse_variable_file(path, data))
        if "datasets" in data:
            datasets.extend(parse_datasets_file(path, data))
        if "prefix_systems" in data:
            for prefix, system in (data.get("prefix_systems") or {}).items():
                systems_map[str(prefix).upper()] = str(system).upper()

    # The columns and datasets of the sources read by the intake mechanism (ADR-0162) are documented in curation/intake.yml.
    from ..intake import curation_docs

    intake_variables, intake_datasets = curation_docs(root)
    for data in intake_variables:
        variables.extend(parse_variable_file(root / "intake.yml", data))
    for data in intake_datasets:
        datasets.extend(parse_datasets_file(root / "intake.yml", data))

    _replace_variable_docs(catalog, variables)
    _replace_dataset_docs(catalog, datasets)
    bound = _seed_field_codelists(catalog, variables)
    overridden = _apply_prefix_overrides(catalog, systems_map)

    by_source: dict[str, int] = {}
    for v in variables:
        by_source[v.source] = by_source.get(v.source, 0) + 1
    return {
        "curation_root": str(root),
        "files": files,
        "variables": len(variables),
        "datasets": len(datasets),
        "codelists_bound": bound,
        "prefix_overrides": overridden,
        "by_source": by_source,
    }


#: Decisions that are FINISHED. They are recorded as resolved questions rather
#: than left in the open list, because a settled "no" that keeps appearing as
#: unfinished work is indistinguishable from a task nobody has got to.
SETTLED: tuple[tuple[str, str, str, str], ...] = (
    (
        "semantics.cep_decoding",
        "semantics",
        "Should CEP (Brazilian postal code) be decoded to a place name?",
        "Will not decode; use município instead. Three independent reasons, any one "
        "sufficient. No CEP table exists anywhere on the FTP tree, and there is no "
        "reason to expect one — CEP is Correios' property, not the Ministry's. The "
        "Correios data that would close it is licensed, so shipping it is not ours to "
        "do. And CEP is a re-identification vector: combined with sex and date of "
        "birth, both present in these files, it narrows a patient to a household. "
        "MUNIC_RES answers the geographic question at a granularity the data is "
        "actually licensed and safe to publish at.",
    ),
    (
        "semantics.sexo_contradictory_coding",
        "semantics",
        "Which SEXO coding applies to which SIH generation?",
        "One coding throughout. SIHSUS's own SEXO table (0 Ignorado, 1 Masculino, 2-3 "
        "Feminino, 4-9 Ignorado) is identical in all four vintages the kits ship: 1992-97, "
        "1998-2003, 2003-07 and current. The contradiction was between SYSTEMS (RESP codes "
        "1 as Feminino), and appeared only when every system's table was merged; codelists "
        "are keyed by system, so SIH's column is bound to SIH's table (2026-09-28).",
    ),
)


#: Gaps that are OPEN, recorded with exactly what would close them. §6.1's rule
#: is "do not guess", and a named gap is how not-guessing stays visible.
UNRESOLVED: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "discovery.uploads_directory",
        "discovery",
        "What is behind /dissemin/publicos/uploads, the one path the crawl cannot read?",
        "Nothing can be determined from outside, and this was probed rather than assumed: "
        "LIST, NLST, CWD, SIZE and MDTM all return '550 Access is denied'. Its type is not "
        "even knowable — the name appears in the parent listing, the SIZE probe that "
        "distinguishes a file from a directory is itself refused, and the crawler therefore "
        "treats it as an unreadable directory. The name suggests a staging area rather than "
        "published data, and no file anywhere else on the tree references it. It is recorded "
        "as the single unresolved coverage_gap rather than passed over. Closing it needs "
        "credentials or a question to the Ministry, not another crawl.",
        "nothing measurable: it is one path of 362, holding no content this project can see",
    ),
    (
        "semantics.cod_idade_units",
        "semantics",
        "What time unit does each COD_IDADE value stand for in SIH?",
        "Fetch a SIH .CNV or .DEF that decodes the age-unit column, or read the value "
        "list out of a record-layout document. The .DEF files bind COD_IDADE to "
        "IDADEPUB, IDADEBAS, IDADEDET and IDADE18, and all four are TabNet age-BAND "
        "axes (3-character codes labelled '< 1 ano', '1 a 4 anos'), not the unit code. "
        "No codelist of time units exists in the 4.0M rows ingested so far.",
        "decoding IDADE at all: an age distribution computed without the unit invents "
        "thousands of thirty-year-olds out of thirty-month-old infants",
    ),
)


def _record_open_gaps(catalog: CatalogStore) -> None:
    for key, area, question, procedure, blocking in UNRESOLVED:
        catalog.note_question(
            key, area=area, question=question,
            verification_procedure=procedure, blocking=blocking,
        )


def _record_settled_rulings(catalog: CatalogStore) -> None:
    """Write the settled decisions in, already resolved."""
    for key, area, question, resolution in SETTLED:
        catalog.note_question(
            key,
            area=area,
            question=question,
            verification_procedure="Settled by ruling; reopen only with new licensing facts.",
            blocking="nothing — this is a decision, not a gap",
        )
        catalog.resolve_question(key, resolution=resolution, evidence="curation: settled ruling")


def _replace_variable_docs(catalog: CatalogStore, docs: Sequence[VariableDoc]) -> None:
    forget_variable_docs(catalog)
    keep = {(d.system, d.field_name) for d in docs}
    stale = [
        (r["system"], r["field_name"])
        for r in catalog.query("SELECT system, field_name FROM variable_docs")
        if (r["system"], r["field_name"]) not in keep
    ]
    if stale:
        catalog.executemany(
            "DELETE FROM variable_docs WHERE system = ? AND field_name = ?", stale
        )
    catalog.executemany(
        """
        INSERT INTO variable_docs (system, field_name, official_name, translated_name,
            description, code_system, codelist, multi_valued, token_rule, depends_on,
            modifies, derived, notes, vintage_note, source, source_ref, asserted_by,
            asserted_at, reasoning, per_form, lookup_key, label_from, label_via)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(system, field_name) DO UPDATE SET
            official_name=excluded.official_name, translated_name=excluded.translated_name,
            description=excluded.description, code_system=excluded.code_system,
            codelist=excluded.codelist, multi_valued=excluded.multi_valued,
            token_rule=excluded.token_rule, depends_on=excluded.depends_on,
            modifies=excluded.modifies, derived=excluded.derived, notes=excluded.notes,
            vintage_note=excluded.vintage_note,
            source=excluded.source, source_ref=excluded.source_ref,
            asserted_by=excluded.asserted_by, asserted_at=excluded.asserted_at,
            reasoning=excluded.reasoning, per_form=excluded.per_form, lookup_key=excluded.lookup_key,
            label_from=excluded.label_from, label_via=excluded.label_via
        """,
        [d.as_row() for d in docs],
    )


def _replace_dataset_docs(catalog: CatalogStore, docs: Sequence[DatasetDoc]) -> None:
    keep = {d.dataset_id for d in docs}
    stale = [
        (r["dataset_id"],)
        for r in catalog.query("SELECT dataset_id FROM dataset_docs")
        if r["dataset_id"] not in keep
    ]
    if stale:
        catalog.executemany("DELETE FROM dataset_docs WHERE dataset_id = ?", stale)
    catalog.executemany(
        """
        INSERT INTO dataset_docs (dataset_id, system, series, what_one_row_is,
            unit_of_analysis, known_biases, gotchas, source, source_ref, asserted_by, asserted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_id) DO UPDATE SET
            system=excluded.system, series=excluded.series,
            what_one_row_is=excluded.what_one_row_is,
            unit_of_analysis=excluded.unit_of_analysis, known_biases=excluded.known_biases,
            gotchas=excluded.gotchas, source=excluded.source, source_ref=excluded.source_ref,
            asserted_by=excluded.asserted_by, asserted_at=excluded.asserted_at
        """,
        [d.as_row() for d in docs],
    )


def _seed_field_codelists(catalog: CatalogStore, docs: Sequence[VariableDoc]) -> int:
    """A curated ``codelist:`` is a binding at the highest authority.

    This is the point of ``SOURCE_AUTHORITY['manual'] = 0``: a person who has read
    the layout document and decided that ``SP_PF_CBO`` draws on CBO-2002 outranks
    every heuristic that guessed otherwise.
    """
    catalog.execute("DELETE FROM field_codelists WHERE source = 'manual'")
    rows = [
        (d.system, "", d.field_name, codelist, "manual",
         d.source_ref or f"curation:{d.asserted_by or 'unattributed'}", 1.0)
        for d in docs
        for codelist in ([d.codelist, *d.codelists] if d.codelist else [])
    ]
    return catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source,
                                     source_ref, confidence)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(system, family_id, field_name, codelist) DO UPDATE SET
            source=excluded.source, source_ref=excluded.source_ref,
            confidence=excluded.confidence
        """,
        rows,
    )


def _apply_prefix_overrides(catalog: CatalogStore, mapping: dict[str, str]) -> int:
    """Manual overrides for the learned prefix map, at full agreement.

    The learned map holds its answer on purpose. A file that names the answer is
    how a person overrides it durably — as opposed to ``prefix-adjudicate``, which
    settles one contradiction in place and leaves no record in version control.
    """
    if not mapping:
        return 0
    return catalog.executemany(
        """
        INSERT INTO prefix_systems (series_prefix, system, file_count, agreement, learned_at)
        VALUES (?,?,0,1.0,?)
        ON CONFLICT(series_prefix) DO UPDATE SET
            system=excluded.system, agreement=1.0, learned_at=excluded.learned_at
        """,
        [(prefix, system, utcnow()) for prefix, system in mapping.items()],
    )


# ------------------------------------------------------------------- coverage


def coverage_by_rung(catalog: CatalogStore) -> list[dict[str, Any]]:
    """Variables documented per system, by which rung of evidence supplied them.

    The denominator is fields the catalog has actually observed, not fields some
    document mentions — a layout PDF describing columns nobody has seen is not
    coverage of anything.
    """
    observed = {
        (str(r["system"]), str(r["field_name"]))
        for r in catalog.query(
            """
            SELECT DISTINCT f.system, vp.field_name
              FROM variable_profiles vp
              JOIN families f ON f.family_id = vp.family_id
            """
        )
    }
    curated: dict[tuple[str, str], str] = {
        (str(r["system"]), str(r["field_name"])): str(r["source"])
        for r in catalog.query("SELECT system, field_name, source FROM variable_docs")
    }
    harvested: dict[tuple[str, str], str] = {}
    for r in catalog.query(
        "SELECT system, field_name, source FROM field_documentation WHERE system IS NOT NULL"
    ):
        harvested.setdefault((str(r["system"]), str(r["field_name"])), str(r["source"]))
    # Rung 2: a .DEF display name is a weaker answer than a record layout — it
    # names a TabNet tabulation axis rather than the column — but it is a name,
    # and counting it as nothing overstates how much is undocumented.
    for r in catalog.query(
        "SELECT DISTINCT system, field_name FROM def_variables WHERE system IS NOT NULL"
    ):
        harvested.setdefault((str(r["system"]), str(r["field_name"])), "def")

    systems = sorted({s for s, _ in observed})
    out: list[dict[str, Any]] = []
    for system in systems:
        fields = {f for s, f in observed if s == system}
        counts: dict[str, int] = {}
        documented = 0
        for f in fields:
            rung = curated.get((system, f)) or harvested.get((system, f))
            if rung:
                documented += 1
                counts[rung] = counts.get(rung, 0) + 1
        out.append(
            {
                "system": system,
                "observed_fields": len(fields),
                "documented": documented,
                "coverage": round(documented / len(fields), 3) if fields else 0.0,
                # Every rung, always, zero-filled. A table whose columns depend on
                # which rungs the first row happened to use hides the rest.
                **{f"via_{rung}": counts.get(rung, 0) for rung in DOC_SOURCES},
            }
        )
    return sorted(out, key=lambda r: -int(r["observed_fields"]))


def system_spellings(system: str) -> list[str]:
    """Every name this system may be filed under, from the declaration.

    Curation files carry the CRAWLED name — `sihsus/_shared.yml` declares
    `system: SIHSUS` — so `variable_docs` is keyed on SIHSUS while the API and
    the ontology speak SIH. Matching one spelling against the other silently
    returned no docs: `describe("SIH", "RD", field="ANO_CMPT")` answered with
    every statistic and a null `official_name`, which reads as "nothing is known
    about this column" rather than "you spelled the system the other way".
    """
    asked = str(system or "").strip().upper()
    if not asked:
        return []
    from ..ontology import Ontology

    try:
        onto = Ontology.load()
    except Exception:  # noqa: BLE001 - an unreadable declaration must not block a lookup
        return [asked]
    node = onto.system_of(asked)
    if node is None:
        return [asked]
    return sorted({asked, str(node.code).upper(), *(str(a).upper() for a in node.crawled_as)})


#: A system whose files republish another system's fields inherits that
#: system's curation; its own entries win. DATASUS's open-data DuckDB exports
#: of the APACs (Dados_Abertos/APAC_SIA) carry SIA's own AB_*, AP_*, ACF_*
#: columns (ADR-0095).
INHERITS: dict[str, tuple[str, ...]] = {"DADOS_ABERTOS": ("SIASUS",)}


def _docs_epoch(catalog: CatalogStore) -> tuple[object, ...] | None:
    """What the docs depend on, cheaply (0.1 ms): the curation fingerprint the catalog last loaded, the number of docs
    and ``PRAGMA data_version`` (any other connection's commit). None: this catalog cannot say, so nothing is cached."""
    conn = getattr(catalog, "conn", None)
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT fingerprint FROM curation_state WHERE id = 1").fetchone()
    except Exception:  # noqa: BLE001 - a catalog older than the table
        row = None
    try:
        return (row[0] if row else "", conn.execute("PRAGMA data_version").fetchone()[0],
                conn.execute("SELECT count(*) FROM variable_docs").fetchone()[0])
    except Exception:  # noqa: BLE001 - no variable_docs table: nothing to cache
        return None


def forget_variable_docs(catalog: CatalogStore) -> None:
    """Drop what `load_variable_docs` holds for this catalog: call after writing ``variable_docs`` through it."""
    catalog.__dict__.pop("_variable_docs_cache", None)


def load_variable_docs(catalog: CatalogStore, system: str | None = None) -> dict[str, VariableDoc]:
    """Curated docs keyed by field name, for the renderer and the doc generator.

    Inherited systems (``INHERITS``) fill in fields the system does not curate.

    Held per catalog connection and keyed on what the docs depend on (`_docs_epoch`): a render asks once per file
    group (1,776 groups, 21 s of an SIH state-year) and the docs of a system cannot change between them. The dict is
    a copy; the docs in it are shared and must not be edited.
    """
    epoch = _docs_epoch(catalog)
    cache: dict[tuple[object, ...], dict[str, VariableDoc]] = catalog.__dict__.setdefault("_variable_docs_cache", {})
    key = None if epoch is None else (*epoch, str(system).upper() if system else None)
    if key is not None and key in cache:
        return dict(cache[key])
    if system and str(system).upper() in INHERITS:
        docs: dict[str, VariableDoc] = {}
        for parent in INHERITS[str(system).upper()]:
            docs.update(_load_variable_docs(catalog, parent))
        docs.update(_load_variable_docs(catalog, system))
    else:
        docs = _load_variable_docs(catalog, system)
    if key is not None:
        if len(cache) >= 32:
            cache.clear()
        cache[key] = docs
    return dict(docs)


def derived_inputs(docs: Mapping[str, VariableDoc]) -> dict[str, tuple[str, ...]]:
    """``DERIVED NAME (upper) -> input columns`` for every curated recipe. A name may have a recipe per layout (SIA's
    IDADE_anos: AP_NUIDADE and AP_COIDADE in the APACs, IDADEPAC and TPIDADEPAC elsewhere): its inputs are every
    recipe's, so a narrow projection reads whichever the layout carries (keeping only the last recipe's lost the
    APAC age, 2026-10-10)."""
    out: dict[str, tuple[str, ...]] = {}
    for doc in docs.values():
        for recipe in getattr(doc, "derived", None) or []:
            name = str(recipe.get("name") or "").upper()
            if name:
                inputs = tuple(str(c).upper() for c in (recipe.get("from") or []))
                out[name] = tuple(dict.fromkeys((*out.get(name, ()), *inputs)))
    return out


def required_columns(docs: Mapping[str, VariableDoc], columns: Sequence[str]) -> frozenset[str]:
    """The columns (upper case) a read has to bring so that ``columns`` can be rendered, derived and labelled.

    THE one rule of a projection, for the lake and the fetch path alike: what ``select=`` names, the inputs of a
    derived column asked for (IDADE_anos is made from IDADE and COD_IDADE, ADR-0092), whatever a column's meaning
    depends on (``depends_on``, ``modifies``), the columns its LABEL is made from (a composite key's parts, ADR-0088;
    a sibling that names it, ADR-0090; the establishment a ``label_via`` reads, ADR-0094) and what modifies it (a
    unit beside a duration). A projection that dropped one of them turned an explicit request into a label that is
    silently null: the lake did (CNES CLASS_SR was keyed by SERV_ESP + CLASS_SR and came back undecoded), the fetch
    path did not, so one column was labelled for fetched years and not for lake years. The caller drops what it did
    not ask for after rendering (``view.drop_helper_columns``).
    """
    keep = {str(c).upper() for c in columns}
    inputs_of = derived_inputs(docs)
    for name in list(keep):
        keep.update(inputs_of.get(name, ()))
    for name in list(keep):
        doc = docs.get(name)
        if doc is None:
            continue
        keep.update(str(dependency).upper() for dependency in (doc.depends_on or []))
        for recipe in (doc.derived or []):
            keep.update(str(source).upper() for source in (recipe.get("from") or []))
        if doc.modifies:
            keep.add(str(doc.modifies).upper())
        for part in (doc.key or []):
            if not str(part).startswith("@"):  # @UF is the file's state, not a column
                keep.add(str(part).partition(":")[0].strip().upper())
        if doc.label_from:
            keep.add(str(doc.label_from).upper())
        via = doc.label_via
        if via and via.get("column"):
            via_columns = via["column"] if isinstance(via["column"], list) else [via["column"]]
            keep.update(str(c).upper() for c in via_columns)
    # And anything that MODIFIES a requested column (a unit beside a duration).
    for name, doc in docs.items():
        if doc.modifies and str(doc.modifies).upper() in keep:
            keep.add(str(name).upper())
    return frozenset(keep)


def _load_variable_docs(catalog: CatalogStore, system: str | None = None) -> dict[str, VariableDoc]:
    """The docs curated for exactly this system."""
    clause, params = "", []
    if system:
        names = system_spellings(system)
        clause = f" WHERE system IN ({','.join('?' * len(names))})"
        params = list(names)
    out: dict[str, VariableDoc] = {}
    for r in catalog.query(f"SELECT * FROM variable_docs{clause}", params):
        out[str(r["field_name"])] = VariableDoc(
            system=str(r["system"]),
            field_name=str(r["field_name"]),
            official_name=r["official_name"],
            translated_name=r["translated_name"],
            description=r["description"],
            code_system=r["code_system"],
            codelist=(str(r["codelist"]).split(",")[0] if r["codelist"] else None),
            codelists=(str(r["codelist"]).split(",")[1:] if r["codelist"] else []),
            multi_valued=bool(r["multi_valued"]),
            token_rule=json.loads(r["token_rule"]) if r["token_rule"] else None,
            depends_on=json.loads(r["depends_on"]) if r["depends_on"] else [],
            modifies=r["modifies"],
            derived=json.loads(r["derived"]) if r["derived"] else [],
            notes=r["notes"],
            vintage_note=r["vintage_note"],
            source=str(r["source"]),
            source_ref=r["source_ref"],
            asserted_by=r["asserted_by"],
            reasoning=r["reasoning"],
            per_form=bool(r["per_form"]),
            key=json.loads(r["lookup_key"]) if r["lookup_key"] else [],
            label_from=r["label_from"],
            label_via=json.loads(r["label_via"]) if r["label_via"] else None,
        )
        doc = out[str(r["field_name"])]
        if doc.codelist and doc.codelist.upper().startswith(CURATED_PREFIX):
            doc.codes = inline_codelist(doc.codelist)
    return out


# ------------------------------------------------- dataset semantics (§14.15)
#
# `semantic_axes` and `unit_of_analysis` have lived in `curation/datasets/*.yml`
# with no code consumer since the query switches that used them were removed;
# FINDINGS §3l records that they were kept "for future opt-in analytical
# helpers". The aggregate layer is that helper, and this is the one reader — it
# reuses `iter_curation_files`, so nothing here re-discovers curation files.

#: A grain component naming a period rather than an entity. `establishment-month`
#: is establishment-months, so COUNT(*) over a quarter counts three per
#: establishment and calling that "establishments" is the mistake.
_PERIOD_WORDS = frozenset({"month", "year", "period", "mes", "mês", "ano", "competence"})

#: Grain prose that names no analysable unit, so nothing is derived from it.
_NOT_A_GRAIN = ("none (not a dataset)", "varies by block")


@dataclass(frozen=True, slots=True)
class Grain:
    """What one row of a dataset IS, in machine-readable form.

    Derived from the `unit_of_analysis` prose rather than restated, because the
    prose already names the components: `establishment-bed type-month` is
    literally `[establishment, bed type, month]`. Of 39 distinct grains across
    132 datasets, splitting on the hyphen is correct for all but a handful, and
    those carry an explicit `grain:` block instead.
    """

    prose: str
    components: tuple[str, ...] = ()
    period_component: str | None = None
    declared: bool = False

    @property
    def is_period_bearing(self) -> bool:
        """True when a row is an entity-PERIOD, so COUNT(*) counts those."""
        return self.period_component is not None

    @property
    def entity_components(self) -> tuple[str, ...]:
        return tuple(c for c in self.components if c != self.period_component)

    @property
    def analysable(self) -> bool:
        return bool(self.components)

    def counts(self) -> str:
        """What COUNT(*) counts, named honestly."""
        return "-".join(self.components) if self.components else "row"


def parse_grain(unit_of_analysis: str | None, declared: Mapping[str, Any] | None = None) -> Grain:
    """Structure a dataset's grain, preferring an explicit declaration."""
    prose = str(unit_of_analysis or "").strip()
    if declared:
        components = tuple(str(c).strip() for c in (declared.get("components") or ()) if str(c).strip())
        period = declared.get("period_component")
        return Grain(
            prose=prose or "-".join(components),
            components=components,
            period_component=str(period) if period else None,
            declared=True,
        )
    if not prose or any(prose.lower().startswith(x) for x in _NOT_A_GRAIN):
        return Grain(prose=prose)
    parts = tuple(p.strip() for p in prose.replace("–", "-").split("-") if p.strip())
    period = next((p for p in parts if p.lower() in _PERIOD_WORDS), None)
    return Grain(prose=prose, components=parts, period_component=period)


@dataclass(frozen=True, slots=True)
class DatasetSemantics:
    """The analytical facts curation states about one dataset.

    `axes` is `semantic_axes` unchanged: named geography and time bindings with
    their fields and declared defaults. The aggregate layer reads bindings from
    here rather than introducing a vocabulary of its own.
    """

    dataset_id: str
    system: str | None
    series: str | None
    grain: Grain
    axes: dict[str, Any] = field(default_factory=dict)

    def geography_bindings(self) -> dict[str, Any]:
        return dict(self.axes.get("geography") or {})

    def time_bindings(self) -> dict[str, Any]:
        return dict(self.axes.get("time") or {})

    def default_geography(self) -> str | None:
        return self.axes.get("default_geography")

    def default_time(self) -> str | None:
        return self.axes.get("default_time")


@curated(rooted=True)
def _dataset_semantics(root: str) -> dict[str, DatasetSemantics]:
    """Read grain and axes for every curated dataset, honouring inheritance.

    Axes are inherited because DATASUS datasets are not independent: SINAN's 58
    agravos all carry the same notification block, so `ID_MN_RESI` is the
    municipality of residence in every one of them. Restating that 58 times is
    the duplication this project keeps being bitten by — one edit that misses
    one file is a dataset that silently answers differently.

    Three levels, most specific first:

    * the dataset's own ``semantic_axes``;
    * ``shared_by_system:`` in the same file, keyed by system — `declared.yml`
      holds SIA, CNES, SIM, SIH and more, and they do NOT share axes;
    * ``shared:`` in the same file, for a file that is one system's agravos.

    Grain is never inherited. CNES's datasets share a geography column and have
    different grains — establishment-month, professional-establishment-month,
    establishment-bed type-month — and inheriting that would be exactly the
    "COUNT(*) means one thing everywhere" assumption the algebra refuses.
    """
    out: dict[str, DatasetSemantics] = {}
    for path in iter_curation_files(Path(root)):
        data = read_yaml(path)
        if not isinstance(data, dict) or "datasets" not in data:
            continue
        file_shared = dict((data.get("shared") or {}).get("semantic_axes") or {})
        by_system = {
            str(name).upper(): dict((body or {}).get("semantic_axes") or {})
            for name, body in (data.get("shared_by_system") or {}).items()
        }
        for dataset_id, body in (data.get("datasets") or {}).items():
            if not isinstance(body, dict):
                continue
            system = body.get("system")
            # PRESENCE, not truthiness. `semantic_axes: {}` on a dataset is an
            # explicit statement that it has none -- IBGE.PROJUF is keyed on a
            # state, not a municipality, and must not inherit its family's
            # municipality axis -- which is a different claim from saying
            # nothing at all.
            if "semantic_axes" in body:
                axes = dict(body.get("semantic_axes") or {})
            else:
                axes = dict(by_system.get(str(system or "").upper()) or file_shared)
            out[str(dataset_id)] = DatasetSemantics(
                dataset_id=str(dataset_id),
                system=system,
                series=body.get("series"),
                grain=parse_grain(body.get("unit_of_analysis"), body.get("grain")),
                axes=axes,
            )
    return out


def dataset_semantics(root: Path | None = None) -> dict[str, DatasetSemantics]:
    """Grain and semantic axes for every curated dataset, keyed by dataset_id."""
    from ..config import curation_root

    return dict(_dataset_semantics(str(root or curation_root())))


def semantics_for(dataset: str, root: Path | None = None) -> DatasetSemantics | None:
    """Resolve `SIH-RD`, `SIH.RD` or `SIHSUS_RD` to its curated semantics."""
    table = dataset_semantics(root)
    wanted = str(dataset).upper().replace("-", "_").replace(".", "_")
    for key, value in table.items():
        if key.upper() == wanted:
            return value
    # `SIH-RD` is the ontology spelling; curation keys on the crawled system
    # name, so `SIHSUS_RD` and `SIH_RD` are the same dataset.
    tail = wanted.rsplit("_", 1)[-1]
    head = wanted.rsplit("_", 1)[0] if "_" in wanted else ""
    for value in table.values():
        if str(value.series or "").upper() != tail:
            continue
        system = str(value.system or "").upper()
        if system == head or system.startswith(head) or head.startswith(system):
            return value
    return semantics_from_roles(dataset, root)


def semantics_from_roles(dataset: str, root: Path | None = None) -> DatasetSemantics | None:
    """A dataset's place and time bindings read from its roles (``curation/roles/<dataset>.yml``), for a dataset whose
    curation declares no ``semantic_axes``: the roles already say which column is whose place and which date is when, so
    a second declaration of the same fact is not asked for (ADR-0217).

    * geography: every ``place`` role a model places events by, ``stratum`` (the subject's own place: residence) and
      ``where`` (the event's place), each a binding named by its role; the default is the residence, else the first.
    * time: every ``date`` role whose model is ``when``; an entity's ``<x>.year`` and ``<x>.month`` together are one
      binding (``year_month``), a date one of its own (``date``). The default is the binding of the column the dataset's
      lake is dated by (the intake's ``period``), else the first.
    """
    from ..config import curation_root

    base = Path(root or curation_root())
    wanted = str(dataset).upper().replace(".", "-", 1)
    path = base / "roles" / f"{wanted}.yml"
    landed = _landed_axes(wanted)
    if not path.is_file() and not landed:
        return None
    doc = (read_yaml(path) or {}) if path.is_file() else {}
    columns = {str(c): b for c, b in (doc.get("columns") or {}).items() if isinstance(b, dict)}
    geography: dict[str, Any] = {}
    default_geography = None
    for column, body in columns.items():
        role_name = str(body.get("role") or "")
        if role_name.endswith("_name") or role_name.endswith(".name"):
            continue                    # a place written as a name is no code: placed by the intake's name match, not here
        if body.get("kind") == "place" and body.get("model") in ("stratum", "where"):
            geography[str(body.get("role") or column)] = {"fields": [column], "code_system": "ibge_municipality"}
            if body.get("model") == "stratum" and default_geography is None:
                default_geography = str(body.get("role") or column)
    time: dict[str, Any] = {}
    parts: dict[str, dict[str, str]] = {}
    for column, body in columns.items():
        if body.get("kind") != "date" or body.get("model") != "when":
            continue
        role = str(body.get("role") or column)
        entity, _, prop = role.rpartition(".")
        if prop in ("year", "month") and entity:
            parts.setdefault(entity, {})[prop] = column
        else:
            time[role] = {"fields": [column], "encoding": "date"}
    for entity, pair in parts.items():
        if "year" in pair and "month" in pair:
            time[f"{entity}.year_month"] = {"fields": [pair["year"], pair["month"]], "encoding": "year_month"}
        elif "year" in pair:
            time[f"{entity}.year"] = {"fields": [pair["year"]], "encoding": "year"}
    dated = _lake_period_columns(wanted)
    default_time = next((name for name, b in time.items() if dated and set(b["fields"]) & dated), None) if time else None
    if landed:
        # the place and period the intake landed each record by: a default only where the roles give none (a place
        # written as a name, SNGPC's; a dataset with no roles file)
        geography.setdefault("landed", landed["geography"])
        time.setdefault("landed", landed["time"])
        default_geography = default_geography or (next((n for n in geography if n != "landed"), "landed"))
        default_time = default_time or (next((n for n in time if n != "landed"), "landed"))
    if not geography or not time:
        return None
    default_time = default_time or next(iter(time))
    system, _, series = wanted.partition("-")
    return DatasetSemantics(
        dataset_id=wanted.replace("-", "_"), system=system, series=series,
        grain=parse_grain(doc.get("record")),
        axes={"geography": geography, "default_geography": default_geography or next(iter(geography)),
              "time": time, "default_time": default_time},
    )


def _landed_axes(dataset: str) -> dict[str, Any] | None:
    """The bindings an intake source's records were landed by: ``_MUNICIPALITY`` (its declared place resolved to the
    IBGE code, a name matched within its state, the sole-municipality rule for Brasília's administrative regions) and
    ``year`` with ``_MONTH`` (its declared period). Written by `intake._records_sql` beside the raw columns, so a source
    placed by a name, or with no roles file, has a place and a time without a second declaration."""
    from ..intake import declared_sources

    system, _, series = dataset.partition("-")
    for spec in declared_sources().values():
        if str(spec.get("system") or "").upper() == system and str(spec.get("series") or "").upper() == series:
            if (spec.get("place") or {}).get("type") not in ("municipality", "municipality_name"):
                return None
            return {"geography": {"fields": ["_MUNICIPALITY"], "code_system": "ibge_municipality"},
                    "time": {"fields": ["year", "_MONTH"], "encoding": "year_month"}}
    return None


def _lake_period_columns(dataset: str) -> set[str]:
    """The columns an intake source's lake is dated by (its declared ``period``), upper-cased as they land."""
    from ..intake import declared_sources

    system, _, series = dataset.partition("-")
    for spec in declared_sources().values():
        if str(spec.get("system") or "").upper() == system and str(spec.get("series") or "").upper() == series:
            period = spec.get("period") or {}
            return {str(period[k]).upper() for k in ("column", "year", "month") if period.get(k)}
    return set()
