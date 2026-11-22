"""What ``curation/intake.yml`` declares: the sources that are not on the FTP tree, and what their declarations say
to the rest of the curation (fields, ontology nodes, variable and dataset docs). Reading a declaration is meaning;
landing its records is `pegasus_data.intake`, which reads these and is read by nothing here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["REWRITTEN", "TYPED", "curation_docs", "declared_sources", "intake_fields", "ontology_nodes", "strata"]

#: Declared types that get a typed column beside the raw one.
TYPED = ("date", "number", "integer", "year", "result")
#: A declared type that rewrites the column in place and keeps the value as filed beside it (`<NAME>__RAW`): ``int_code``, a
#: code filed as a float's text ('5.0' or '5.'; SRAG's CLASSI_FIN is '5.0' in the 2019 and 2020 files and '5' in the others), read as '5'.
#: A condition on it (`where`) reads the rewritten code.
REWRITTEN = ("int_code",)


def declared_sources(root: Path | None = None) -> dict[str, dict[str, Any]]:
    from ..config import curation_root
    from .curation import read_yaml

    doc = read_yaml((root or curation_root()) / "intake.yml", missing_ok=True) or {}
    dictionaries = doc.get("dictionaries") or {}
    out = {}
    for name, spec in (doc.get("sources") or {}).items():
        shared = dictionaries.get(spec.get("dictionary_columns")) if spec.get("dictionary_columns") else None
        if spec.get("dictionary_columns") and shared is None:
            raise KeyError(f"intake.yml: {name} names the dictionary {spec['dictionary_columns']!r}, which is not declared")
        if shared:
            # a shared dictionary's columns are optional (a file holds those it holds); the source's own stay required
            spec = {**spec, "columns": {**{c: {**(d or {}), "optional": True} for c, d in shared.items()}, **(spec.get("columns") or {})}}
        out[name] = {**spec, "fields": _with_populations(spec.get("fields") or {})}
    return out


def _with_populations(fields: dict[str, Any]) -> dict[str, Any]:
    """A field that declares an ``outcome`` beside its ``where`` counts the records of its population (``where``) with
    the outcome; its population is a field of its own, ``<name>_assessed``, named as its denominator (``over``): samples
    with E. coli present over the samples assessed for E. coli, never over every analysis. The field keeps its ``outcome``
    and the records cube counts it over the population's own groups, so it has a row (0 where none had the outcome) wherever its
    population has one: a place-month with samples and no positive is a true zero, one without samples is missing."""
    out: dict[str, Any] = {}
    for name, fs in fields.items():
        if not fs.get("outcome"):
            out[name] = fs
            continue
        # the population is a field of its own and names itself (`population_label`): it must not inherit its outcome's label
        population = {k: v for k, v in fs.items() if k not in ("outcome", "what", "label", "population_label")}
        out[f"{name}_assessed"] = {**population, "what": f"The population of {name}: {fs.get('what', '')}".strip(),
                                   **({"label": fs["population_label"]} if fs.get("population_label") else {})}
        out[name] = {**{k: v for k, v in fs.items() if k != "population_label"}, "over": f"{name}_assessed"}
    return out


def intake_fields(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """The fields the declarations define, in the shape of ``fields.yml`` entries (``source: intake``)."""
    out: dict[str, dict[str, Any]] = {}
    for name, spec in declared_sources(root).items():
        for field, fs in (spec.get("fields") or {}).items():
            # a field's years are its own, else its source's span (the period's valid years): a context is read on them
            years = fs.get("years") or spec.get("years") or (spec.get("period") or {}).get("valid") or ""
            # what the field says about itself to its readers (fields.yml's keys: `where`, the rows that make it one value
            # per place; `icd10`, `harm`...) is `declares`; the rest is derived from the declaration
            # a time-varying field says so: `grain: month` rows carry a `month`; its measures are sums and counts, so `law: sum`
            # is exact at every coarser grain (a year is the sum of its months, a numerator and its denominator alike)
            out[field] = {**({"grain": spec["period"]["grain"]} if (spec.get("period") or {}).get("grain") else {}),
                          **({"law": "sum"} if fs.get("measure") or fs.get("unpivot") else {}),
                          **(fs.get("declares") or {}),
                          "source": "intake", "intake": name, "unit": fs.get("unit", ""), "what": fs.get("what", spec.get("what", "")),
                          **({"label": fs["label"]} if fs.get("label") else {}),
                          "years": str(years), **({"over": fs["over"]} if fs.get("over") else {}),
                          # its strata as `load_field` names them (`cubes`)
                          **({"by": [alias for _, alias in strata(fs)]} if fs.get("by") or fs.get("unpivot") else {})}
    return out


def ontology_nodes(root: Path | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """(systems, datasets) in the shape of ``ontology.yml``: each source with a ``system`` is a dataset ``<SYSTEM>.<series>``;
    the system's own names come from the sources that carry ``system_name``."""
    systems: dict[str, dict[str, Any]] = {}
    datasets: dict[str, dict[str, Any]] = {}
    for spec in declared_sources(root).values():
        if not spec.get("system"):
            continue
        code, series = str(spec["system"]).upper(), str(spec["series"]).upper()
        systems.setdefault(code, {"kind": "data", "crawled_as": [code]}).update(spec.get("system_name") or {})
        datasets[f"{code}.{series}"] = {"system": code, "official_name": spec.get("official_name"), "translated_name": spec.get("translated_name"),
                                        "what_it_is": spec.get("what"), "observed_as": [series]}
    return systems, datasets


def curation_docs(root: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The documentation the declarations carry, as ``variables:`` and ``datasets:`` files of the curation loader: a column's
    ``description`` is its description, its ``codes`` the inline code list (served as ``CURATED.<SYSTEM>.<FIELD>``)."""
    variable_files, dataset_files = [], []
    for spec in declared_sources(root).values():
        if not spec.get("system"):
            continue
        system, series = str(spec["system"]).upper(), str(spec["series"]).upper()
        reference = spec.get("dictionary") or spec.get("citation")
        variables: dict[str, Any] = {}
        for column, decl in (spec.get("columns") or {}).items():
            body: dict[str, Any] = {"description": str((decl or {}).get("description") or column)}
            if (decl or {}).get("codes"):
                body["codes"] = decl["codes"]
            if (decl or {}).get("codelist"):
                # a standard or a DATASUS table the package ships (ICD10, CBO2002): the column's code system is external
                body["codelist"] = decl["codelist"]
                body["code_system"] = "external"
            if (decl or {}).get("key"):
                # the code means something only with other columns of the record (ADR-0088): the lookup key is their
                # concatenation, `COLUMN:width` padding a part with zeros (TISS's item: its table's two digits and its code)
                body["key"] = list(decl["key"])
            if (decl or {}).get("label_from"):
                # the record names its own code in a sibling column (ADR-0090): no table to choose
                body["label_from"] = str(decl["label_from"]).upper()   # columns land upper-cased: the sibling's name too
                body["code_system"] = "internal"
            if (decl or {}).get("derived"):
                body["derived"] = decl["derived"]       # a column made from this one (SRAG's IDADE_anos from the age and its unit)
            if (decl or {}).get("type") in TYPED:
                body["notes"] = f"typed as {decl['type']}; the value as filed is {column.upper()}__RAW"
            elif (decl or {}).get("type") in REWRITTEN:
                body["notes"] = f"a code filed as a float's text is read as its integer ('5.0' as '5'); the value as filed is {column.upper()}__RAW"
            variables[column.upper()] = body
        variable_files.append({"system": system, "source": "layout_doc", "source_ref": reference, "variables": variables})
        dataset_files.append({"datasets": {f"{system}_{series}": {
            "system": system, "series": series, "what_one_row_is": spec.get("one_row") or spec.get("what"),
            "unit_of_analysis": spec.get("unit_of_analysis"), "known_biases": spec.get("known_biases"),
            "gotchas": spec.get("gotchas") or [], "use": spec.get("use"), "why_no_event_type": spec.get("why_no_event_type"),
            "source": "web", "source_ref": reference, "asserted_by": "pegasus_data"}}})
    return variable_files, dataset_files


def strata(fs: dict[str, Any]) -> list[tuple[str | None, str]]:
    """The extra keys of a field as (column, name in the field): ``by: [COL]`` names the key as the column in lower case,
    ``by: [{COL: name}]`` as ``name``; an ``unpivot`` field has the two keys it declares (``as``), taken from no column."""
    if fs.get("unpivot"):
        return [(None, str(k)) for k in fs["unpivot"]["as"]]
    out: list[tuple[str | None, str]] = []
    for entry in fs.get("by") or []:
        column, alias = next(iter(entry.items())) if isinstance(entry, dict) else (entry, str(entry).lower())
        out.append((str(column), str(alias)))
    return out
