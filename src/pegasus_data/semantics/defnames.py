"""What DATASUS already told us, in the `.DEF` files, and nobody read.

A TabNet `.DEF` declares every column it can tabulate, and it declares them *with
a name*: ``IAdenocarc.invasor,ADENCARCIN`` says that column counts invasive
adenocarcinomas. The parser has been reading those lines since the beginning —
42,045 of them are in ``def_variables`` — and almost none of it reached the
documentation, because the ledger only picked up an official name where a
codelist binding happened to carry one. 169 columns had a name; **1,101
undescribed columns had one waiting in a file already parsed**.

So this is not new evidence. It is evidence already in the catalog, moved to the
rung where consumers look for it.

**What is extracted and what is not.** The display name is DATASUS's own words
and is recorded verbatim as ``official_name`` — no expansion, no cleanup, because
"Alt.Ben.Atrofia" abbreviated by the Ministry is a fact and my guess at what it
stands for is not. The *description* says only what the `.DEF` itself
establishes: whether the column is a measure to be summed (`I`, Incremento) or an
axis to group by, and under which name. That is genuinely less than a human
writing about the column, and it is genuinely more than nothing — and it is
honestly labelled `source='def'` so a reader can see which they are getting.

**One name per column is a simplification the data does not always allow.**
``ADENCARCIN`` is "Adenocarc.In Situ" in the cytology `.DEF` and
"Adenocarc.invasor" in the histopathology one — the same column name meaning
different things in two files of the same system. Where the `.DEF`s disagree the
disagreement is written into the description rather than resolved, because
picking one would be inventing agreement that DATASUS did not express.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..catalog.store import Catalog, utcnow

#: `.DEF` usage markers. `I` is *Incremento* — a quantity TabNet sums. Everything
#: else is a tabulation axis: something to group or filter by.
_MEASURE = "I"

#: Below this a "name" is an artefact rather than a name.
_MIN_NAME = 2


@dataclass(slots=True)
class DefNameReport:
    columns: int = 0
    measures: int = 0
    axes: int = 0
    disputed: int = 0
    systems: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "columns_named": self.columns,
            "measures": self.measures,
            "tabulation_axes": self.axes,
            "names_that_disagree": self.disputed,
            "per_system": self.systems,
        }


def _describe(name: str, usage: str, others: list[str]) -> str:
    """Say what the `.DEF` establishes, and no more than that."""
    if usage == _MEASURE:
        body = (
            f'A quantity DATASUS tabulates under the name "{name}". The .DEF marks '
            "it Incremento, meaning TabNet sums it, so it is a measure to be added "
            "up across whatever you group by rather than a code to be decoded."
        )
    else:
        body = (
            f'A column DATASUS tabulates under the name "{name}", offered as an axis '
            "to group or filter by rather than as a quantity to sum."
        )
    if others:
        listed = ", ".join(f'"{o}"' for o in sorted(others)[:3])
        body += (
            f" Named differently in other .DEF files of the same system ({listed}), "
            "so what it holds depends on which file the row came from."
        )
    return body


def document_from_def(
    catalog: Catalog, *, systems: list[str] | None = None, overwrite: bool = False
) -> DefNameReport:
    """Fill ``field_documentation`` from the names ``.DEF`` files already gave.

    Only columns with no description are touched, unless ``overwrite``. A
    hand-written description outranks this and must not be replaced by it:
    ``manual`` is authority 0 and this is one of the weaker documentary rungs.
    """
    clause = ""
    params: list[object] = []
    if systems:
        slots = ",".join("?" * len(systems))
        clause = f" AND dv.system IN ({slots})"
        params = [s.upper() for s in systems]

    rows = catalog.query(
        f"""
        SELECT dv.system AS system, dv.field_name AS field_name,
               dv.display_name AS display_name, dv.usage AS usage,
               dv.def_path AS def_path, dv.line_no AS line_no
          FROM def_variables dv
         WHERE dv.field_name IS NOT NULL AND TRIM(dv.field_name) <> ''
           AND dv.display_name IS NOT NULL AND LENGTH(TRIM(dv.display_name)) >= ?
           {clause}
        """,
        [_MIN_NAME, *params],
    )

    # Gather every name each column is given, so a disagreement between two .DEF
    # files can be reported instead of silently resolved.
    seen: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (str(row["system"]), str(row["field_name"]).upper())
        name = str(row["display_name"]).strip()
        entry = seen.setdefault(
            key,
            {"names": {}, "usage": str(row["usage"] or ""), "ref": "", "line": 0},
        )
        names: dict[str, int] = entry["names"]  # type: ignore[assignment]
        names[name] = names.get(name, 0) + 1
        if not entry["ref"]:
            entry["ref"] = str(row["def_path"] or "")
            entry["line"] = int(row["line_no"] or 0)
        if str(row["usage"] or "") == _MEASURE:
            entry["usage"] = _MEASURE

    already = set()
    if not overwrite:
        already = {
            (str(r["system"]), str(r["field_name"]).upper())
            for r in catalog.query(
                """
                SELECT system, field_name FROM field_documentation
                 WHERE description IS NOT NULL AND TRIM(description) <> ''
                UNION
                SELECT system, field_name FROM variable_docs
                 WHERE description IS NOT NULL AND TRIM(description) <> ''
                """
            )
        }

    report = DefNameReport()
    payload: list[tuple[object, ...]] = []
    stamp = utcnow()
    for (system, name_key), entry in seen.items():
        if (system, name_key) in already:
            continue
        names: dict[str, int] = entry["names"]  # type: ignore[assignment]
        # The name used most often is the primary; the rest are the dispute.
        primary = max(names, key=lambda n: (names[n], len(n)))
        others = [n for n in names if n != primary]
        usage = str(entry["usage"])
        payload.append(
            (
                system,
                name_key,
                _describe(primary, usage, others),
                primary,
                None,
                None,
                None,
                "def",
                f"{entry['ref']}:{entry['line']}",
                0.55 if others else 0.65,
            )
        )
        report.columns += 1
        report.systems[system] = report.systems.get(system, 0) + 1
        if usage == _MEASURE:
            report.measures += 1
        else:
            report.axes += 1
        if others:
            report.disputed += 1

    if payload:
        catalog.executemany(
            """
            INSERT INTO field_documentation
                (system, field_name, description, official_name, declared_type,
                 declared_width, declared_decimals, source, source_ref, confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(system, field_name, source_ref) DO UPDATE SET
                description=excluded.description,
                official_name=excluded.official_name,
                confidence=excluded.confidence
            """,
            payload,
        )
    catalog.log_event(
        "defnames",
        "documented columns from the names .DEF files already carried",
        detail=(
            f"{report.columns} columns named ({report.measures} measures, "
            f"{report.axes} axes, {report.disputed} where .DEF files disagree) at {stamp}"
        ),
    )
    return report
