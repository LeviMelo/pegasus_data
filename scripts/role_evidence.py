"""The evidence a column's role is read from, for any dataset: what DATASUS documents and what the files hold.

    python scripts/role_evidence.py DATASET [--period P] [--geo G]

For every column of DATASET's families (the catalog's schemas): its curated variable doc (`load_variable_docs`, the
system's inheritance included: name, meaning, code system, codelists), the form's harvested layout where one exists
(`harvested_field`: type, width, codes, a table it names), and a profile of one real file: its Arrow type as decoded,
how many records carry it, distinct values, the commonest values and the share that read as dates or numbers. The file
read is the dataset's cheapest of its latest year with records, unless --period/--geo name one. Written to
`data/probes/review/<DATASET>.sheet.md`, one block a column, for the role review (`draft_column_roles.py` drafts,
a person decides).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import warnings
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

ROOT = Path(__file__).resolve().parent.parent


def _columns(conn: sqlite3.Connection, system: str, series: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for sig, lo, hi in conn.execute("SELECT schema_signature, time_min, time_max FROM families WHERE system=? AND series=?",
                                    (system, series)):
        for (name,) in conn.execute("SELECT field_name FROM schema_presence WHERE schema_signature=?", (sig,)):
            y = out.setdefault(str(name).upper(), [lo, hi])
            y[0] = min(x for x in (y[0], lo) if x is not None) if (y[0] or lo) else None
            y[1] = max(x for x in (y[1], hi) if x is not None) if (y[1] or hi) else None
    return out


def _sample(conn: sqlite3.Connection, system: str, series: str, year: int | None = None,
            skip: int = 0) -> tuple[str | None, int | None, int | None]:
    """The cheapest file of the latest year that has one (or of ``year``), past the ``skip`` cheapest:
    (geography, year, month)."""
    rows = conn.execute(
        f"""SELECT fa.geo_code, fa.year, fa.normalized_date, f.size FROM family_files ff
           JOIN families fam ON fam.family_id = ff.family_id
           JOIN files f ON f.path = ff.path AND f.gone_at IS NULL
           JOIN file_facts fa ON fa.path = ff.path
           WHERE fam.system = ? AND fam.series = ? AND fa.year IS NOT NULL AND f.size > 2000
           {"AND fa.year = ?" if year else ""}
           ORDER BY fa.year DESC, f.size ASC LIMIT 1 OFFSET ?""",
        (system, series, *([year] if year else []), skip)).fetchall()
    if not rows:
        return None, None, None
    geo, year, nd, _ = rows[0]
    month = int(nd) % 100 if nd else None
    return (str(geo) if geo else None), int(year), (month or None)


def _profile(col: pa.ChunkedArray) -> str:
    vals = [v for v in pc.cast(col, pa.string()).to_pylist() if v not in (None, "")]
    if not vals:
        return f"{col.type}: empty"
    cnt = Counter(vals)
    date = sum(1 for v in vals if re.fullmatch(r"(19|20)\d{6}|(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d\d"
                                               r"|\d{4}-\d\d-\d\d.*|\d{2}/\d{2}/\d{4}.*", v)) / len(vals)
    num = sum(1 for v in vals if re.fullmatch(r"-?\d+([.,]\d+)?", v)) / len(vals)
    top = ", ".join(f"{k[:24]}:{n}" for k, n in cnt.most_common(8))
    return f"{col.type}: n={len(vals)}/{len(col)} distinct={len(cnt)} date={date:.2f} num={num:.2f} top={top}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dataset")
    ap.add_argument("--period")
    ap.add_argument("--geo")
    args = ap.parse_args()

    import pegasus_data as pg
    from pegasus_data._request import parse_dataset
    from pegasus_data.catalog.store import CatalogStore
    from pegasus_data.config import load_settings
    from pegasus_data.semantics.curation import harvested_field, load_variable_docs

    system, series = parse_dataset(args.dataset)
    settings = load_settings()
    conn = sqlite3.connect(settings.catalog_path)
    cols = _columns(conn, system, series)
    geo, year, month = _sample(conn, system, series)
    period = args.period or (f"{year}-{month:02d}" if month else (str(year) if year else None))
    geo = args.geo or geo or "BR"
    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        docs = {k.upper(): v for k, v in load_variable_docs(store, system).items()}
    finally:
        store.close()
    table, why = None, ""
    # a latest file that will not read (published empty, undecodable) gives way to the next file of its year, then to
    # the year before: six tries at most
    tried_in_year = 0
    for _ in range(6):
        if not period:
            break
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                table = pg.query(args.dataset, period=period, geography=geo, present="codes", allow_partial=True)
            break
        except Exception as exc:  # noqa: BLE001 - a dataset that will not read is said, not skipped
            why = f"{why}; " * bool(why) + f"{period} {geo}: {type(exc).__name__}: {str(exc)[:160]}"
            if args.period or year is None:
                break
            tried_in_year += 1
            g, y2, m2 = _sample(conn, system, series, year, skip=tried_in_year) if tried_in_year < 3 else (None, None, None)
            if y2 is None:
                tried_in_year = 0
                g, y2, m2 = _sample(conn, system, series, year - 1)
            if y2 is None:
                break
            year, month = y2, m2
            period, geo = (f"{year}-{month:02d}" if month else str(year)), (args.geo or g or "BR")
    names = {c.upper(): c for c in (table.column_names if table is not None else [])}
    profiles = {n: f"{_profile(table.column(c))} [{period} {geo}]" for n, c in names.items()} if table is not None else {}
    # a column the sample does not carry (an older layout's) is read from a file of the last year it exists
    for last in sorted({y[1] for n, y in cols.items() if n not in profiles and y[1]}, reverse=True)[:6]:
        want = [n for n, y in cols.items() if n not in profiles and y[1] == last]
        g, yr, mo = _sample(conn, system, series, last)
        if yr is None:
            continue
        per = f"{yr}-{mo:02d}" if mo else str(yr)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                older = pg.query(args.dataset, period=per, geography=g or "BR", present="codes", allow_partial=True)
        except Exception:  # noqa: BLE001 - an older layout that will not read stays without values, said
            continue
        for c in older.column_names:
            if c.upper() in want:
                profiles[c.upper()] = f"{_profile(older.column(c))} [{per} {g or 'BR'}]"
    out = [f"# {args.dataset}: {len(cols)} columns; sample {period} {geo}"
           + (f", {table.num_rows} records" if table is not None else f" (not read: {why})")]
    for name, years in sorted(cols.items()):
        d = docs.get(name)
        f = harvested_field(system, series, name) or {}
        out.append(f"## {name}  years={years}")
        if d is not None:
            desc = re.sub(r"\s+", " ", str(getattr(d, "description", "") or ""))[:260]
            lists = getattr(d, "codelists", None) or ([d.codelist] if getattr(d, "codelist", None) else [])
            out.append(f"   doc: {getattr(d, 'official_name', None)!r} / {getattr(d, 'translated_name', None)!r} "
                       f"[{getattr(d, 'code_system', None)}] codelists={list(lists)} {desc!r}")
        if f:
            out.append(f"   form: {f.get('type')} w={f.get('width')} label={f.get('label')!r} table={f.get('table')!r} "
                       f"codes={f.get('codes')}")
        out.append(f"   values: {profiles.get(name, 'not in any sample read')}")
    path = ROOT / "data" / "probes" / "review" / f"{args.dataset.upper().replace('.', '-')}.sheet.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(out[0], "->", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
