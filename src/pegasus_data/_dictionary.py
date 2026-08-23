"""The dictionary for a fetched table: what each column is, in English.

`fetch()` returns a table whose columns are named the way DATASUS names them —
``CODMUNRES``, ``IDADEMAE``, ``TPNASCASSI``. A caller who did not write the
curation layer cannot read that, and the answer to "what is this column" lived
in three places none of which travelled with the data: `describe()` one field at
a time, `compendium()` as a separate document, and the curation YAML in the
package.

So this assembles the same answer FOR THE TABLE IN HAND, and only for the
columns actually in it. It reads the curation layer in one query rather than
calling `describe()` per column, which matters at 74 columns.

Each row states the column's English name, its Portuguese official name, the
prose describing it, the reference table its labels came from, and the evidence
rung behind all of that (§6.3) — because "the description says X" is worth less
than "the description says X, and it came from the Ministry layout document".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from .catalog.store import Catalog

__all__ = ["DataDictionary", "build_dictionary", "described_names"]

#: Columns the normaliser attaches to every row. Provenance, not data.
from .normalize.engine import PROVENANCE_COLUMNS

#: The order a reader wants them in: what it is, then what it means, then where
#: that came from. Not alphabetical — `column` first is the whole point.
COLUMNS = (
    "column",
    #: Present only when `names="described"` renamed the table: the DATASUS
    #: name this column had, which is the only way back to the source layout.
    "original_column",
    "kind",
    "translated_name",
    "official_name",
    "description",
    "code_system",
    "codelist",
    "label_column",
    "labelled",
    "source",
    "source_ref",
    "notes",
    "vintage_note",
)


@dataclass
class DataDictionary:
    """One row per column of the table it describes."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    system: str = ""
    dataset: str = ""

    @property
    def table(self) -> pa.Table:
        """The same rows as Arrow, so it exports through `export()`."""
        import pyarrow as pa

        if not self.rows:
            return pa.table({c: pa.array([], pa.string()) for c in COLUMNS})
        return pa.table(
            {c: pa.array([_text(r.get(c)) for r in self.rows], pa.string()) for c in COLUMNS}
        )

    def as_dict(self) -> dict[str, Any]:
        return {"system": self.system, "dataset": self.dataset, "columns": self.rows}

    def write(self, path: str | Path) -> Path:
        """Write to ``.csv``, ``.json``, ``.parquet`` or ``.md``, by suffix."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()
        if suffix == ".json":
            out.write_text(json.dumps(self.as_dict(), indent=2, ensure_ascii=False),
                           encoding="utf-8")
        elif suffix in (".md", ".markdown"):
            out.write_text(self.to_markdown(), encoding="utf-8")
        else:
            from .api import export

            return export(self.table, out)
        return out

    def to_markdown(self) -> str:
        """A readable dictionary, for someone who is not going to open Arrow."""
        head = f"# {self.dataset or self.system} — data dictionary\n"
        lines = [head, f"{len(self.rows)} columns.\n"]
        for r in self.rows:
            shown = str(r["column"])
            english = r.get("translated_name")
            # Under a profile that translated the headers, the column IS its
            # English name, and "`Mother's age` — Mother's age" is noise. The
            # DATASUS name is the useful second half there, because it is what
            # the layout document and every other tool call it.
            if english and english != shown:
                lines.append(f"## `{shown}` — {english}")
            elif r.get("original_column"):
                lines.append(f"## {shown} — `{r['original_column']}`")
            else:
                lines.append(f"## `{shown}`")
            if r.get("official_name"):
                lines.append(f"*{r['official_name']}*  ")
            if r.get("description"):
                lines.append(f"\n{r['description']}\n")
            facts = [
                ("Reference table", r.get("codelist")),
                ("Label column", r.get("label_column")),
                ("Code system", r.get("code_system")),
                ("Evidence", r.get("source")),
                ("Source", r.get("source_ref")),
                ("Notes", r.get("notes")),
                ("Vintage", r.get("vintage_note")),
            ]
            for label, value in facts:
                if value:
                    lines.append(f"- **{label}:** {value}")
            lines.append("")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.rows)

    def __repr__(self) -> str:  # pragma: no cover - display
        described = sum(1 for r in self.rows if r.get("description"))
        return (
            f"<DataDictionary {self.dataset or self.system}: {len(self.rows)} columns, "
            f"{described} described>"
        )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


#: What the renderer adds beside a column, and what each addition means. These
#: are not in curation because curation describes what DATASUS publishes, and
#: these are ours — but a column with no entry in the dictionary reads as an
#: undocumented column, which is exactly the complaint the dictionary answers.
DERIVED_SUFFIXES: dict[str, tuple[str, str]] = {
    "_codes": ("codes", "The individual codes parsed out of `{base}`, before labelling."),
    "_unmatched": ("unmatched codes",
                   "How many codes in `{base}` no reference table could decode."),
    "_ibge7": ("IBGE 7-digit code", "`{base}` widened to the full IBGE code, with check digit."),
    "_ibge6": ("IBGE 6-digit code", "`{base}` as the 6-digit IBGE code, without check digit."),
    "_uf": ("state (UF)", "The state read off `{base}`."),
    "_region": ("region", "The macro-region read off `{base}`."),
    "_epi_week": ("epidemiological week", "The epidemiological week `{base}` falls in."),
    "_epi_year": ("epidemiological year", "The epidemiological year `{base}` falls in."),
    "_iso": ("ISO date", "`{base}` as an ISO-8601 date."),
    "_raw": ("as filed", "`{base}` exactly as DATASUS filed it, before normalisation."),
    "_valid": ("valid?", "Whether `{base}` passes its format check."),
    "_checkdigit_ok": ("check digit valid?", "Whether `{base}`'s check digit verifies."),
}


def _kind(name: str, label_suffix: str, raw_names: set[str]) -> str:
    if name in PROVENANCE_COLUMNS:
        return "provenance"
    if name.endswith(label_suffix) and name[: -len(label_suffix)] in raw_names:
        return "label"
    for suffix in DERIVED_SUFFIXES:
        if name.endswith(suffix) and name[: -len(suffix)] in raw_names:
            return "derived"
    return "data"


def build_dictionary(
    catalog: Catalog,
    system: str,
    column_names: list[str],
    *,
    dataset: str = "",
    render_report: Any | None = None,
) -> DataDictionary:
    """Describe every column of a fetched table, in the table's own order.

    Curation is read once for the whole system rather than per column: at 74
    columns the per-field path is 74 round trips to answer one question.
    """
    from .semantics.curation import load_variable_docs
    from .view import LABEL_SUFFIX

    docs = load_variable_docs(catalog, system)
    upper = {k.upper(): v for k, v in docs.items()}
    # A profile may already have translated the headers — `report` does, and it
    # is the CLI's default — so the column in hand can be "Mother's age" while
    # curation is keyed on IDADEMAE. Without this the dictionary describes
    # nothing on exactly the path most likely to be read by a person.
    source_name = dict(getattr(render_report, "renamed_headers", {}) or {})
    labelled = set(getattr(render_report, "labelled", []) or [])
    # What ACTUALLY decoded the column, which is not always what curation names:
    # a column with no curated table can still be labelled from a measured
    # binding, and reporting only the curated name shows `None` beside a
    # perfectly good label column.
    used = dict(getattr(render_report, "codelist_used", {}) or {})
    originals = [source_name.get(n, n) for n in column_names]
    present = set(originals)
    raw = {n for n in originals if not n.endswith(LABEL_SUFFIX)}

    rows: list[dict[str, Any]] = []
    for shown in column_names:
        name = source_name.get(shown, shown)
        kind = _kind(name, LABEL_SUFFIX, raw)
        if kind == "label":
            base = name[: -len(LABEL_SUFFIX)]
            doc = upper.get(base.upper())
            rows.append({
                "column": shown,
                "original_column": name if name != shown else None,
                "kind": "label",
                "translated_name": (
                    f"{doc.translated_name} (label)" if doc and doc.translated_name
                    else f"{base} decoded"
                ),
                "official_name": None,
                "description": f"The decoded text for `{base}`.",
                "code_system": None,
                "codelist": used.get(base) or (doc.codelist if doc else None),
                "label_column": None,
                "labelled": None,
                "source": (doc.source if doc else None),
                "source_ref": None,
                "notes": None,
                "vintage_note": None,
            })
            continue
        if kind == "derived":
            suffix = next(x for x in DERIVED_SUFFIXES
                          if name.endswith(x) and name[: -len(x)] in raw)
            base = name[: -len(suffix)]
            what, prose = DERIVED_SUFFIXES[suffix]
            doc = upper.get(base.upper())
            stem = (doc.translated_name if doc and doc.translated_name else base)
            rows.append({
                "column": shown,
                "original_column": name if name != shown else None,
                "kind": "derived",
                "translated_name": f"{stem} — {what}",
                "official_name": None,
                "description": prose.format(base=base),
                "code_system": None,
                "codelist": used.get(base) if suffix == "_codes" else None,
                "label_column": None, "labelled": None,
                "source": "pegasus_data", "source_ref": None,
                "notes": None, "vintage_note": None,
            })
            continue
        if kind == "provenance":
            rows.append({
                "column": shown,
                "original_column": name if name != shown else None,
                "kind": "provenance",
                "translated_name": _PROVENANCE_NAMES.get(name, name),
                "official_name": None,
                "description": _PROVENANCE_PROSE.get(name),
                "code_system": None, "codelist": None, "label_column": None,
                "labelled": None, "source": "pegasus_data", "source_ref": None,
                "notes": None, "vintage_note": None,
            })
            continue

        doc = upper.get(name.upper())
        companion = name + LABEL_SUFFIX
        rows.append({
            "column": shown,
            "original_column": name if name != shown else None,
            "kind": "data",
            "translated_name": (doc.translated_name if doc else None),
            "official_name": (doc.official_name if doc else None),
            "description": (doc.description if doc else None),
            "code_system": (doc.code_system if doc else None),
            "codelist": used.get(name) or (doc.codelist if doc else None),
            "label_column": companion if companion in present else None,
            "labelled": (name in labelled) if render_report is not None else None,
            "source": (doc.source if doc else None),
            "source_ref": (doc.source_ref if doc else None),
            "notes": (doc.notes if doc else None),
            "vintage_note": (doc.vintage_note if doc else None),
        })
    return DataDictionary(rows=rows, system=system, dataset=dataset or system)


_PROVENANCE_NAMES = {
    "_source_path": "Source file path",
    "_blob_sha256": "Source file checksum",
    "_ingested_at": "Ingestion timestamp",
    "_schema_signature": "Schema signature",
}

_PROVENANCE_PROSE = {
    "_source_path": "The published DATASUS path this row was read from.",
    "_blob_sha256": "SHA-256 of the downloaded file, so the row can be traced to an exact byte sequence.",
    "_ingested_at": "When this package decoded the file.",
    "_schema_signature": "Identifies which schema generation the row was decoded under.",
}


def described_names(dictionary: DataDictionary) -> dict[str, str]:
    """``old name -> English name``, for renaming a fetched table's columns.

    Only columns that HAVE an English name are renamed. A column with no
    curated name keeps the name DATASUS gave it, because inventing one would
    make the table harder to trace back, not easier.

    Collisions are resolved by keeping the original name in parentheses. Two
    SINAN columns really are both "Municipality of residence" — one current, one
    historical — and silently merging them into one name would produce a table
    with two identically-named columns, which Arrow allows and no caller wants.
    """
    from .view import LABEL_SUFFIX

    proposed: dict[str, str] = {}
    for row in dictionary.rows:
        name = str(row["column"])
        english = row.get("translated_name")
        if not english or row.get("kind") == "provenance":
            continue
        proposed[name] = str(english)

    seen: dict[str, list[str]] = {}
    for old, new in proposed.items():
        seen.setdefault(new, []).append(old)
    out: dict[str, str] = {}
    for old, new in proposed.items():
        if len(seen[new]) > 1:
            base = old[: -len(LABEL_SUFFIX)] if old.endswith(LABEL_SUFFIX) else old
            new = f"{new} ({base})"
        out[old] = new
    return out
