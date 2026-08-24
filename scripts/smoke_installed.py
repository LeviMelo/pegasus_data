"""Exercise an installed Pegasus wheel without using repository imports or data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from importlib import metadata, resources
from pathlib import Path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--forbid-root",
        type=Path,
        help="fail if pegasus_data imports from this source checkout",
    )
    args = parser.parse_args()

    import pegasus_data as pg
    from pegasus_data.catalog.store import _schema_sql
    from pegasus_data.config import Settings

    package_path = Path(pg.__file__).resolve()
    if args.forbid_root and _is_relative_to(package_path, args.forbid_root.resolve()):
        raise RuntimeError(f"import escaped the wheel environment: {package_path}")

    installed_version = metadata.version("pegasus-data")
    if pg.__version__ != installed_version:
        raise RuntimeError(
            f"runtime version {pg.__version__!r} disagrees with metadata {installed_version!r}"
        )

    resource_root = resources.files("pegasus_data.resources")
    manifest = json.loads(resource_root.joinpath("manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="pegasus-wheel-smoke-") as data_home:
        settings = Settings(root=Path(data_home))
        manager = pg.resource_manager(settings=settings)
        for name, body in sorted((manifest.get("resources") or {}).items()):
            record = manager.ensure(name)
            payload = Path(record.path).read_bytes()
            if len(payload) != int(body["bytes"]):
                raise RuntimeError(f"resource {name!r} has the wrong size")
            if hashlib.sha256(payload).hexdigest() != body["sha256"]:
                raise RuntimeError(f"resource {name!r} has the wrong digest")

        curation_files = list(settings.curation_dir.rglob("*.yml"))
        if not curation_files:
            raise RuntimeError("the installed wheel contains no curated YAML")
        if "CREATE TABLE" not in _schema_sql():
            raise RuntimeError("the installed wheel cannot load catalog/schema.sql")

        query_plan = pg.plan(
            "SIH-RD",
            period=2024,
            geography="AL",
            settings=settings,
        )
        if query_plan.retrieval.source_strategy != "fetch":
            raise RuntimeError("fresh-install planning did not use the shipped source map")

    print(
        json.dumps(
            {
                "distribution": f"pegasus-data {installed_version}",
                "import": str(package_path),
                "resources": len(manifest["resources"]),
                "curation_files": len(curation_files),
                "plan": str(query_plan),
                "python": sys.version.split()[0],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
