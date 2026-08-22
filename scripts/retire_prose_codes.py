"""Retire dictionary rows whose 'code' is prose, left by a fixed parser.

Three `.CNV` header defects made the parser read title lines and overrun labels
as data. The parser is fixed and pinned by tests, but a catalog built before the
fix keeps the bad rows: re-ingesting is the clean repair and it takes over an
hour, which is not a reasonable cost for four rows.

A match expression is a code, a range or a comma list. It never contains
internal whitespace. That makes these identifiable rather than a judgement, and
it is the same rule verify step 16 asserts.

Deleted, not superseded. Superseding records a source that changed its mind;
this is a reading that was never in the source at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pegasus_data.catalog.store import Catalog  # noqa: E402
from pegasus_data.config import load_settings  # noqa: E402

WHERE = "LENGTH(value_raw) > 12 AND value_raw GLOB '*[A-Za-z]*[ ]*'"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--apply", action="store_true", help="delete, rather than report")
    args = parser.parse_args()

    settings = load_settings(root=Path(args.root) if args.root else None)
    store = Catalog(settings.catalog_path)
    try:
        doomed = store.query(
            f"SELECT system, value_group, value_raw FROM dictionary WHERE {WHERE}"
        )
        if not doomed:
            print("nothing to retire")
            return 0
        for row in doomed:
            print(f"  {row['system']}.{row['value_group']}: {str(row['value_raw'])[:44]!r}")
        if not args.apply:
            print(f"\n{len(doomed)} rows; re-run with --apply to delete")
            return 0
        store.execute(f"DELETE FROM dictionary WHERE {WHERE}")
        store.log_event(
            "dictionary",
            "retired prose codes left by a fixed .CNV parser",
            detail=f"{len(doomed)} rows whose code contained internal whitespace",
        )
        print(f"\nretired {len(doomed)} rows")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
