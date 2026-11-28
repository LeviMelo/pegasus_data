"""The declared shape of every curation file: which keys a declaration may hold, checked when the file is parsed.

``curation/`` is read as raw mappings by dozens of modules, each with ``.get("key")``, so a misspelt key (``staus:
retired``, ``shift_dayz: 3``) was silently ignored and the default applied. Here each kind of file has ONE schema, as
plain data, and :func:`check` refuses a file with an unknown key, a missing required key or a value outside an enum,
naming the file, the path to the key and the closest allowed key. ``semantics/curation.py`` calls it at the one parse
point (``_parsed_yaml``), so it runs once per file version and costs nothing when the parse is cached.

The language (every node is a plain ``dict`` built by the helpers below, or :data:`ANY`):

* ``ANY``: a free-form subtree, not checked (labels by code, per-source origin blocks);
* ``obj(names, sub=..., required=...)``: a mapping with a fixed vocabulary of keys; ``sub`` gives a child schema
  to the keys that are not free-form;
* ``free(child)``: a mapping whose keys are data (a dataset code, a column name) and whose values all follow ``child``;
* ``seq(child)``: a list of items that all follow ``child``;
* ``enum(*values)``: a scalar that is one of the values.

A file that matches no kind in :data:`KINDS` is an error: a new file declares its kind here.
"""

from __future__ import annotations

import difflib
from fnmatch import fnmatchcase
from functools import lru_cache
from typing import Any

ANY: Any = None


class DeclarationError(ValueError):
    """A curation file holds a key or value its kind does not declare (every violation of the file is listed)."""


def obj(names: str, sub: dict[str, Any] | None = None, required: str = "") -> dict[str, Any]:
    """A mapping with these keys (space separated); ``sub`` maps some of them to a child schema, the rest are ANY."""
    return {"keys": {name: (sub or {}).get(name, ANY) for name in names.split()}, "required": tuple(required.split())}


def free(child: Any = ANY) -> dict[str, Any]:
    return {"free": child}


def seq(child: Any = ANY) -> dict[str, Any]:
    return {"seq": child}


def enum(*values: str) -> dict[str, Any]:
    return {"enum": values}


def _walk(node: Any, schema: Any, path: str, out: list[str]) -> None:
    if schema is ANY or node is None:
        return
    here = path or "<top>"
    if "enum" in schema:
        if node not in schema["enum"]:
            out.append(f"{here}: value {node!r} is not one of {list(schema['enum'])}")
    elif "seq" in schema:
        if not isinstance(node, list):
            out.append(f"{here}: expected a list, found {type(node).__name__}")
            return
        for i, item in enumerate(node):
            _walk(item, schema["seq"], f"{path}[{i}]", out)
    elif not isinstance(node, dict):
        out.append(f"{here}: expected a mapping, found {type(node).__name__}")
    elif "free" in schema:
        for key, value in node.items():
            _walk(value, schema["free"], f"{path}.{key}" if path else str(key), out)
    else:
        allowed = schema["keys"]
        for key, value in node.items():
            where = f"{path}.{key}" if path else str(key)
            if key not in allowed:
                near = difflib.get_close_matches(str(key), list(allowed), n=1, cutoff=0.6)
                hint = f" (did you mean {near[0]!r}?)" if near else ""
                out.append(f"{where}: unknown key {str(key)!r}{hint}")
            else:
                _walk(value, allowed[key], where, out)
        out.extend(f"{path + '.' if path else ''}{name}: missing required key" for name in schema["required"]
                   if name not in node)


def check(path: str, data: Any) -> None:
    """Raise one :class:`DeclarationError` listing every violation of the curation file ``path`` (relative to the
    curation root, ``/``-separated), or return when it holds only declared keys."""
    schema = next((s for pattern, s in KINDS if fnmatchcase(path, pattern)), "no kind")
    if schema == "no kind":
        raise DeclarationError(f"{path}: matches no declared kind of curation file: add it to schema.KINDS")
    problems: list[str] = []
    _walk(data, schema() if callable(schema) else schema, "", problems)
    if problems:
        raise DeclarationError("\n".join(f"{path}: {p}" for p in problems))


def _digest() -> str:
    import hashlib
    from pathlib import Path

    digest = hashlib.blake2b(digest_size=8)
    for name in (__file__, str(Path(__file__).with_name("column_roles.py"))):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()


#: the schemas this process imported: the files on disk can be newer (a commit while a job runs)
LOADED = _digest()


def fingerprint() -> str:
    """A digest of the declared schemas this process checks with (this module and the roles' key vocabulary, as
    imported): a parsed-file cache written under another schema must be checked again."""
    return LOADED


def newer_on_disk() -> bool:
    """Whether the schema files on disk differ from the ones this process imported: curation written for a schema this
    process does not have (a key added with its validator) is then not an error of the curation, but of the process's
    age (`curation.read_yaml` keeps its last valid copy)."""
    try:
        return _digest() != LOADED
    except OSError:
        return False


# --- the kinds ---------------------------------------------------------------------------------------------------

_DIM_LABELS = free(ANY)
_AGGREGATE = obj(
    "age_dimension band_dimensions dataset description dimension_labels dimension_structures dimensions event_type "
    "geography_binding label level_labels measures name time_binding time_grain",
    sub={"age_dimension": obj("bands fields form label name of"), "band_dimensions": free(obj("bands field label unit")),
         "measures": free(obj("additive_over field kind label time_reducer unit"))})
_AXIS = free(obj("roles encoding fields"))
_AXES = obj("default_geography default_time geography time", sub={"geography": _AXIS, "time": _AXIS})
_EVENT = obj(
    "classifiers consolidation duplicates evidence exposure grain kind marks name note persons present source_notes "
    "status weight",
    sub={"classifiers": seq(obj("column recodes role structure")), "consolidation": obj("chain key state_local", sub={"chain": obj("continues end evidence facility gap gap_days person reason record start transfer")}),
         "duplicates": obj("evidence except flag"), "exposure": obj("events evidence per"),
         "source_notes": obj("definition final_after_years form known_errors limitations source valid_from valid_to"),
         "status": obj("column evidence exclude values"),
         "weight": obj("age column evidence grid margin sex total",
                       sub={"age": obj("axis unknown"), "sex": obj("axis female male")})},
    required="name kind")
_DATASET = obj(
    "asserted_by event_types gotchas implied_sex implied_sex_evidence known_biases label official_name semantic_axes "
    "series shared_event_types source source_publication source_ref system translated_name unit_of_analysis use "
    "what_one_row_is why_no_event_type",
    sub={"event_types": seq(_EVENT), "semantic_axes": _AXES,
         "source_publication": obj("dataset observed_series observed_systems physical_geography temporal_resolution")})
_DATASETS = obj("datasets shared shared_by_system", sub={
    "datasets": free(_DATASET),
    "shared": obj("aggregate duplicates event_types semantic_axes unit_of_analysis",
                  sub={"aggregate": _AGGREGATE, "event_types": seq(_EVENT), "semantic_axes": _AXES}),
    "shared_by_system": free(obj("semantic_axes", sub={"semantic_axes": _AXES}))})
_CODED_FIELD = obj("annex codes label source_ref table type width", sub={"codes": free(ANY)})
_DERIVED = obj("age bridge date digits from hierarchy lookup municipalities_only name ranges remap rule to valid",
               required="name from rule")
_VARIABLE = obj(
    "asserted_by code_system codelist codelists codes depends_on derived description key label_from label_via modifies "
    "multi_valued notes official_name per_form reasoning source source_ref token_rule translated_name vintage_note",
    sub={"codes": free(ANY), "derived": seq(_DERIVED), "token_rule": obj("delimiter width")})
_FIELD_DECL = obj("by declares grain label law measure outcome over population_label rows unit unpivot what where years")
_SOURCE = obj(
    "citation columns compare dictionary dictionary_columns fields gotchas known_biases official_name one_row origin period place series "
    "snapshot system system_name translated_name unit_of_analysis use what why_no_event_type",
    sub={"columns": free(obj("aliases codelist codes decimal derived description format from implied_decimals key label_from optional positions take type zero_tokens")),
         "fields": free(_FIELD_DECL), "place": obj("aliases as column states truncated type uf", sub={"aliases": free(free())}),
         "period": obj("column format grain month type valid year"),
         "system_name": obj("authority official_name translated_name what_it_is")})
_LINK_SIDE = obj("dataset where group latest earliest explode_days explode_values pad_years")
_LINK = obj(
    "control description left outcome params passes person probabilistic right same_event sensitivity validate",
    sub={"control": obj("role shift_days"), "left": _LINK_SIDE, "right": _LINK_SIDE, "outcome": obj("differ event first known origin", sub={"known": obj("date role value", required="date role value")}),
         "passes": seq(obj("keys known_only name")), "validate": seq(obj("among left name right sql tolerance")),
         "probabilistic": obj("blocks compare inherit target_fdr", sub={
             "inherit": obj("right", sub={"right": seq(obj("as role via"))})})})
_STATUS = enum("active", "tooling", "retired")
_RESTRICTED = obj("verified what authority codelist partial_coverage attribute")


@lru_cache(maxsize=1)
def _roles() -> dict[str, Any]:
    from .column_roles import KEYS

    # one definition of a column's keys (`column_roles.KEYS`; its loader enforces it too)
    column = obj(" ".join(sorted(KEYS)), sub={"compare": free(obj("type format also categories")),
                                              "through": obj("dataset key")})
    return obj("columns dataset exclusive_persons grids persons record setting",
               sub={"columns": free(column), "grids": free(obj("axes cells evidence value"))},
               required="columns dataset record")


#: ``(file pattern relative to the curation root, schema)``, first match wins.
KINDS: tuple[tuple[str, Any], ...] = (
        ("ontology.yml", obj("asserted_by datasets systems version", sub={
            "systems": free(obj("authority crawled_as inherits kind official_name republishes status translated_name "
                                "what_it_is", sub={"status": _STATUS, "kind": enum("data", "reference", "tooling")})),
            "datasets": free(obj("confidence kind observed_as official_name status system translated_name "
                                 "what_it_is", sub={"status": _STATUS, "kind": enum("data", "reference", "tooling"),
                                                    "confidence": enum("high", "medium", "low")}))})),
        ("variables/*/*.yml", obj("asserted_by system variables", sub={"variables": free(_VARIABLE)},
                                  required="system variables")),
        ("roles/*.yml", _roles),            # built on first use: it imports the roles module
        ("datasets/*.yml", _DATASETS),
        ("aggregates/*.yml", _AGGREGATE),
        ("codes/supplements.yml", obj("SINAN", sub={"SINAN": free(free(obj("codes drop source_ref")))})),
        ("codes/*.yml", obj("series system", sub={"series": free(free(_CODED_FIELD))})),
        ("sidra/axes.yml", obj("axes", sub={"axes": free(obj("classifications names rule"))})),
        ("sidra/topics.yml", obj("researches topics", sub={"topics": free(obj("weight words"))})),
        ("sidra/series.yml", obj("series", sub={"series": free(obj("comparability gaps sources what", sub={
            "comparability": obj("level note"),
            "sources": seq(obj("dims drop_totals id level measure periods picks priority role sum table variable"))}))})),
        ("sidra/compendium.yml", obj("tables", sub={"tables": free(obj("categories group tier variables", sub={
            "variables": seq(obj("id keep kind", required="id kind"))}))})),
        ("sidra/notes.yml", obj("tables", sub={"tables": free(obj("basis by_period categories evidence read updated "
                                                                 "why group tier"))})),
        ("joins.yml", obj("enrichments keys not_established relations", sub={
            "enrichments": free(obj("column compares output reads requires route")),
            "keys": free(obj("as_of caveats members what", sub={
                "members": seq(obj("column dataset measured note principal rows_per_key"))})),
            "not_established": seq(obj("finding proposed_key want")),
            "relations": seq(obj("artifact dataset evidence field relation system target_name target_type"))})),
        ("links.yml", obj("held_out links thresholds verdict", sub={
            "links": free(_LINK),
            "thresholds": obj("discover engine placebo", sub={
                "discover": obj("max_interval_days shift_days top_date_sets top_keys_for_attributes"),
                "engine": obj("chance_drop_pct horizons min_compared"),
                "placebo": obj("block_min_expected block_reach days key_reach")}),
            "verdict": obj("caution viable")})),
        ("fields.yml", obj("cnes fields", sub={
            "cnes": obj("accreditation_groups equipment facility_groups families icu_bed_codes neonatal_icu_bed_codes neurology_bed_codes neurosurgery_bed_codes professional_groups specialised_service_groups "
                        "register_month support team_groups team_not_deactivated", sub={
                "families": free(obj("dataset fixed group measure measure_by sector"))}),
            "fields": free(obj("classification dataset equipment event family gaps group interval kind label law level measure over sector series "
                               "source table unit variable verified what where years", required="label unit what"))})),
        ("intake.yml", obj("dictionaries sources", sub={
            "dictionaries": free(free(obj("aliases decimal description format formats take tokens type"))),
            "sources": free(_SOURCE)})),
        ("resources.yml", obj("resources", sub={"resources": free(obj(
            "authority local namespace temporal", required="authority namespace temporal",
            sub={"local": obj("builder estimate file schema years", required="builder file",
                              sub={"estimate": obj("bytes_per_row groups", required="bytes_per_row groups")})}))})),
        ("products.yml", obj("products", sub={"products": free(obj(
            "build call grain inputs kind label parameters period source stores systems what",
            required="call grain kind label period source stores what"))})),
        ("codelists.yml", obj("bridges code_windows codebook kit_tables label_bindings mentions roles semantic_types structures", sub={
            "bridges": obj("names targets unique", sub={"targets": free(obj("classification width"))}),
            "codebook": obj("max_codes max_width"),
            "kit_tables": free(obj("code label reference")),
            "structures": free(obj("item kind levels segment width", required="kind",
                                   sub={"kind": enum("icd", "levels", "path")})),
            "label_bindings": obj("form_dictionary_rows min_evidence rollup share_tie too_weak"),
            "roles": obj("classification geography registry", sub={
                "classification": obj("patterns what"), "geography": obj("patterns what"),
                "registry": obj("columns establishments owners patterns reach_it_instead_by what",
                                sub={"columns": free(obj("code label"))})})})),
        ("geography.yml", obj(
            "classifications excluded ibge_classifications ipea_classifications legacy_places municipality_fields municipalities_by_year "
            "state_only_codes tabnet_classifications", sub={
                "classifications": free(_RESTRICTED),
                "ibge_classifications": free(obj("source status verified what")),
                "tabnet_classifications": free(obj("authority state_table table verified what")),
                "ipea_classifications": free(obj("authority start_year verified what")),
                "excluded": free(obj("measured reason wanted_as"))})),
        ("categories.yml", free(ANY)),
        ("quality.yml", obj("ill_defined_causes race_reliability thresholds", sub={
            "ill_defined_causes": free(obj("cause chapter except")),
            "race_reliability": obj("asian brown dataset facility min_admissions month race suspect_asian_share "
                                    "swapped_brown_share unreliable_asian_share"),
            "thresholds": obj("coverage icd prefix_systems reference", sub={
                "coverage": obj("decoded_share"), "icd": obj("suspect_binding_share"),
                "prefix_systems": obj("min_agreement min_observations"), "reference": obj("blank_label_share")})})),
        ("questions.yml", obj("open resolutions seed settled", sub={
            "open": free(obj("area blocking procedure question", required="area blocking procedure question")),
            "resolutions": free(),
            "seed": free(obj("area blocking question verification_procedure",
                             required="area blocking question verification_procedure")),
            "settled": free(obj("area question resolution", required="area question resolution"))})),
        ("snapshots.yml", obj("snapshots", sub={"snapshots": free(obj("directories months pattern ufs what"))})),
        ("populations.yml", obj("populations series", sub={
            "populations": free(obj("documents limitations method producer reference_date state_totals title vintage "
                                    "years")),
            "series": free(obj("age_codes authority axes builder kind notes source"))})),
        ("treatments.yml", obj("treatments", sub={"treatments": free(obj("conditions note source substances", sub={
            "substances": seq(obj("catmat name reads use", required="name"))}))})),
        ("captures.yml", obj("captures", sub={"captures": free(obj("conditions description lists", sub={
            "lists": free(obj("death group where"))}))})),
        ("published_tables.yml", free(ANY)),
        ("garbage_codes.yml", obj("editions levels reading", sub={"editions": free(obj(
            "amendments amendments_note as_of as_of_basis cite declarations licence membership packages packages_note "
            "source study use", sub={"amendments": seq(obj("level ranges")), "declarations": seq(obj("level ranges")),
                                     "packages": seq(obj("class package ranges")),
                                     "membership": obj("figure ranges")}))})),
        ("prefix_systems.yml", obj("prefix_systems", sub={"prefix_systems": free(ANY)})),
        ("sources.yml", obj("open_questions sources", sub={"sources": free(obj(
            "citations kind local local_note publisher systems title url"))})),
)
