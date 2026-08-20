"""List the documentation and dictionary files the crawl found for a system.

DATASUS ships layout / Instrução Técnica PDFs for most of its systems, and they
are the difference between a description that quotes the record layout and one
inferred from a column name. There are only 56 of them across the whole tree, so
knowing which apply to a system is worth one command.

Usage::

    python scripts/doc_files.py CATALOG SINASC
"""

from __future__ import annotations

import io
import sqlite3
import sys

FTP = "ftp://ftp.datasus.gov.br"


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) < 3:
        raise SystemExit("usage: doc_files.py CATALOG SYSTEM")
    catalog, system = sys.argv[1], sys.argv[2].upper()
    conn = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT fa.path, fa.role, f.size
              FROM file_facts fa
              JOIN files f ON f.path = fa.path
             WHERE fa.system = ?
               AND fa.role IN ('documentation', 'dictionary')
               AND f.gone_at IS NULL
             ORDER BY f.size DESC
            """,
            (system,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        print(f"no documentation or dictionary files catalogued for {system}")
        return
    for path, role, size in rows:
        megabytes = (size or 0) / 2**20
        print(f"{role:14s} {megabytes:7.2f} MB  {FTP}{path}")


if __name__ == "__main__":
    main()
