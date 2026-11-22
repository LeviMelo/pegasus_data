"""The manual: the home's map written as plain text files an agent greps and reads (docs/plans/agent-interface.md).

``<home>/manual/`` holds ``INDEX.md`` (under 2,000 tokens: what kinds of things exist, how many, where to read on),
one page per dataset (``datasets/<CODE>.md``, what ``info <CODE>`` prints), one per dataset's columns and roles
(``columns/<CODE>.md``, a grep for a column finds its meaning), one per link (``links/<name>.md``), and one page each for
the context fields, the products, the operations and the SIDRA tables. Every page is generated from the map
(`_compendium`), so it says what a call would find, and is written whole beside the old manual and swapped in, so a
reader never sees half of one.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from .config import Settings, load_settings


def manual_dir(cfg: Settings) -> Path:
    return cfg.catalog_dir.parent / "manual"


def _cell(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).replace("|", "/")


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header),
            *("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows)]


def _write_code_windows(staged: Path, cfg: Settings) -> int:
    """One page per classification whose codes carry their validity windows (``codelists.yml`` ``code_windows``): each
    code, its latest name where the declaration names a source of names, the first and last month it is valid, and the
    months missing between them. Returns the codes written."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from .view import _declared_code_windows

    written = 0
    for classification, decl in _declared_code_windows().items():
        home = Path(cfg.registry_dir(decl["registry"], decl["file"]))
        if not home.is_file():
            continue
        windows = pq.read_table(home).to_pylist()
        names: dict[str, str] = {}
        if decl.get("names") and (source := home.with_name(decl["names"])).is_file():
            history = pq.read_table(source, columns=[decl["code"], decl["name"], "valid_from"])
            history = history.sort_by([(decl["code"], "ascending"), ("valid_from", "ascending")])
            names = dict(zip(pc.cast(history.column(decl["code"]), "string").to_pylist(),
                             history.column(decl["name"]).to_pylist(), strict=True))   # the latest run wins
        newest = max(str(r["last"]) for r in windows)
        rows = [[r[decl["code"]], names.get(str(r[decl["code"]]), ""), r["first"],
                 "still valid" if str(r["last"]) == newest else r["last"], ", ".join(r.get("gaps") or [])]
                for r in sorted(windows, key=lambda r: str(r[decl["code"]]))]
        (staged / "codes").mkdir(exist_ok=True)
        (staged / "codes" / f"{classification}.md").write_text(chr(10).join(
            [f"# {classification}: codes and the months each is valid", "",
             f"From `{decl['registry']}/{decl['file']}` (the newest export is {newest}). Labels are joined only inside a "
             "code's window; a record coded outside it stays undecoded, visibly.", "",
             *_table(["code", "name", "first month", "last month", "months missing"], rows)]) + chr(10), encoding="utf-8")
        written += len(rows)
    return written


def write_manual(*, settings: Settings | None = None, root: str | Path | None = None) -> dict[str, int]:
    """Write the manual from the home's current map (built here when stale). Returns the pages written by kind."""
    from ._compendium import current
    from ._info import info

    cfg = settings or load_settings(root=Path(root) if root else None)
    path = current(settings=cfg, wait=True)
    target = manual_dir(cfg)
    staged = target.with_name(".manual.staging")
    shutil.rmtree(staged, ignore_errors=True)
    for sub in ("datasets", "columns", "links"):
        (staged / sub).mkdir(parents=True)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    try:
        q = con.execute
        built = (q("SELECT value FROM meta WHERE key = 'generated_at'").fetchone() or ["?"])[0]
        datasets = q("SELECT * FROM datasets ORDER BY code").fetchall()
        for d in datasets:
            code = str(d["code"])
            (staged / "datasets" / f"{code}.md").write_text(f"# {code}\n\n```text\n{info(code, settings=cfg)}\n```\n",
                                                            encoding="utf-8")
            columns = q("SELECT dv.name, v.translated_name, v.description, dv.codelists, dv.filled, dv.label_share "
                        "FROM dataset_variables dv LEFT JOIN variables v ON v.system = dv.system AND v.name = dv.name "
                        "WHERE dv.dataset = ? ORDER BY dv.name", (code,)).fetchall()
            roles = q("SELECT column_name, role, entity, property, kind, first_year, last_year FROM roles "
                      "WHERE dataset = ? ORDER BY column_name", (code,)).fetchall()
            lines = [f"# {code}: columns and roles", "", f"{d['translated_name'] or ''}. `info {code}.<COLUMN>` describes "
                     "one column; `datasets/" + code + ".md` the dataset.", ""]
            lines += _table(["column", "name", "meaning", "codelist", "filled", "labelled"],
                            [[r["name"], r["translated_name"], (r["description"] or "")[:300], r["codelists"], r["filled"],
                              r["label_share"]] for r in columns])
            if roles:
                lines += ["", "## Roles (what each column states)", ""]
                lines += _table(["column", "role", "entity.property", "kind", "years"],
                                [[r["column_name"], r["role"], f"{r['entity']}.{r['property']}", r["kind"],
                                  f"{r['first_year'] or ''}-{r['last_year'] or ''}"] for r in roles])
            (staged / "columns" / f"{code}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts["datasets"] = len(datasets)
        links = q("SELECT * FROM links ORDER BY name").fetchall()
        for link in links:
            (staged / "links" / f"{link['name']}.md").write_text(
                f"# {link['name']}\n\n```text\n{info(str(link['name']), settings=cfg)}\n```\n", encoding="utf-8")
        counts["links"] = len(links)
        fields = q("SELECT name, label, what, unit, source, years, years_held FROM fields ORDER BY name").fetchall()
        (staged / "fields.md").write_text("\n".join(
            ["# Context fields: `load_field(<name>, years=...)`, one value per municipality and year", "",
             *_table(["field", "label", "what", "unit", "source", "years declared", "years held"],
                     [[f["name"], f["label"], f["what"], f["unit"], f["source"], f["years"], f["years_held"]] for f in fields])]
        ) + "\n", encoding="utf-8")
        products = q("SELECT id, label, kind, what, grain, period, call, held FROM products ORDER BY id").fetchall()
        (staged / "products.md").write_text("\n".join(
            ["# Products: what the package serves besides datasets and fields", "",
             *_table(["product", "label", "kind", "what", "grain", "period", "call", "held"],
                     [list(p) for p in products])]) + "\n", encoding="utf-8")
        operations = q("SELECT name, kind, area, summary, usage FROM operations ORDER BY area, name").fetchall()
        (staged / "operations.md").write_text("\n".join(
            ["# Operations: every function and command", "",
             *_table(["name", "kind", "area", "what", "usage"], [list(o) for o in operations])]) + "\n", encoding="utf-8")
        sidra = q("SELECT id, name, research, subject, frequency, first_period, last_period, levels, curated "
                  "FROM sidra_tables ORDER BY id").fetchall()
        (staged / "sidra.md").write_text("\n".join(
            ["# IBGE SIDRA tables: `cube('sidra:<table>/<variable>')`; `pegasus-data sidra show <table>` describes one; `pegasus-data sidra fetch <table> -v <variables> --level <N1..N6>` lands its values", "",
             *_table(["table", "name", "research", "subject", "frequency", "first", "last", "levels", "curated"],
                     [list(s) for s in sidra])]) + "\n", encoding="utf-8")
        counts.update(fields=len(fields), products=len(products), operations=len(operations), sidra_tables=len(sidra))
        counts["code_windows"] = _write_code_windows(staged, cfg)
        systems = q("SELECT code, translated_name, kind, datasets, year_min, year_max FROM systems ORDER BY kind, code").fetchall()
        held = [d for d in datasets if d["rows_held"]]
        index = [
            f"# pegasus_data manual (map of {built})", "",
            "What this install holds and can do, as files to grep and read. Descend from here; nothing else needs reading "
            "first. Every page is generated from the map, so it is what a call finds.", "",
            "- `grep -ril <word> manual/` finds a dataset, column, code system, field, link, product or SIDRA table.",
            "- `pegasus-data search <words>` also finds codes (a procedure, a diagnosis, an occupation) and what each is "
            "called in every system; `pegasus-data info <CODE>` and `info <CODE>.<COLUMN>` describe one dataset or column.",
            f"- `datasets/<CODE>.md`: one per dataset ({len(datasets)}; {len(held)} with records in this install's lake): "
            "what one row is, its years, biases, gotchas, how to query it.",
            "- `columns/<CODE>.md`: its columns with their meaning, codelist and fill, and the roles they state.",
            f"- `links/<name>.md`: record linkages ({len(links)}) with their stored runs and verdicts.",
            f"- `fields.md` ({len(fields)} municipal context fields), `products.md` ({len(products)}), `operations.md` "
            f"({len(operations)} functions and commands), `sidra.md` ({len(sidra)} IBGE tables).",
            "- `codes/<CLASSIFICATION>.md`: every code of a classification that dates its codes (SIGTAP's procedures), with "
            "its name and the months it is valid; a code is labelled only inside them.", "",
            "Read data through the library (`pegasus_data.query`, `load_field`, `cube`, `link`), never by opening its "
            "files: the library applies the labels by validity window, the one reading of each year and the gaps.", "",
            "## Systems", "",
            *(f"- {s['code']} ({s['kind']}): {s['translated_name'] or ''}; {s['datasets']} datasets, "
              f"{s['year_min'] or '?'}-{s['year_max'] or '?'}" for s in systems),
        ]
        (staged / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    finally:
        con.close()
    old = target.with_name(".manual.old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    staged.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    return counts


__all__ = ["manual_dir", "write_manual"]
