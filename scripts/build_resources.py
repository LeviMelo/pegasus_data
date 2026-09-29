"""Freeze what the maintainer's catalog knows into the package: the seed.

A fresh install's catalog starts as a copy of the seed (ADR-0067), so the seed
decides what a new user can ask on day one: every file on the tree with its
system, series, state, date and schema family, and every binding, curated
variable and dataset description. The label pack (`labelpack`) and the geography
packs are built by their own commands; this writes the seed and refreshes the
manifest entry for everything in `resources/`.

Run it on a catalog that is current: `crawl`, `inventory`, `schemas`,
`families`, then `curate` (RUNBOOK §5).

    python scripts/build_resources.py pegasus_data_home/_catalog/catalog.sqlite
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pegasus_data.catalog.seed import SEED_NAME, export_seed  # noqa: E402

RESOURCES = ROOT / "src" / "pegasus_data" / "resources"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(catalog_path: Path) -> dict[str, object]:
    seed = RESOURCES / SEED_NAME
    rows = export_seed(catalog_path, seed)

    conn = sqlite3.connect(f"file:{catalog_path.as_posix()}?mode=ro", uri=True)
    try:
        crawled = conn.execute(
            "SELECT MAX(finished_at) FROM crawl_runs WHERE finished_at IS NOT NULL"
        ).fetchone()[0]
        counts = {
            "files": conn.execute("SELECT COUNT(*) FROM files WHERE gone_at IS NULL").fetchone()[0],
            "systems": conn.execute(
                "SELECT COUNT(DISTINCT system) FROM file_facts WHERE role='data'"
            ).fetchone()[0],
            "families": rows.get("families", 0),
            "columns": conn.execute(
                "SELECT COUNT(DISTINCT field_name) FROM schema_presence"
            ).fetchone()[0],
            "variables_described": rows.get("variable_docs", 0),
            "bindings": rows.get("field_codelists", 0),
        }
    finally:
        conn.close()

    manifest_path = RESOURCES / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    entries = dict(manifest.get("resources") or {})
    # The seed replaced the tree, family, schema-presence and binding parquets.
    for gone in ("tree", "families", "schema_presence", "bindings"):
        entries.pop(gone, None)
    entries["catalog_seed"] = {
        "file": SEED_NAME,
        "tier": "A",
        "bytes": seed.stat().st_size,
        "rows": sum(rows.values()),
        "sha256": _sha256(seed),
    }
    for entry in entries.values():  # every checksum current, whichever command wrote the file
        path = RESOURCES / str(entry["file"])
        if path.is_file():
            entry["bytes"] = path.stat().st_size
            entry["sha256"] = _sha256(path)
    now = datetime.now(UTC)
    manifest.update(
        {
            "resource_content_version": now.date().isoformat(),
            "built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_build_id": crawled,
            "crawled_at": crawled,
            "counts": counts,
            "resources": entries,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"seed_rows": rows, "manifest": manifest}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    result = build(args.catalog)
    manifest = result["manifest"]
    total = sum(int(item.get("bytes", 0)) for item in manifest["resources"].values())  # type: ignore[index]
    print(json.dumps(result, indent=2))
    print(f"\ntotal shipped: {total / 2**20:.2f} MB")


if __name__ == "__main__":
    main()
