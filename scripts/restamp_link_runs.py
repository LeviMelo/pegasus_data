"""Re-stamp stored link runs whose inputs are proven unchanged, after the role-table key's file list changed (2026-11-23).

`roles.partition_files` keyed a role table on every partition the catalog lists for a year; it now keys on the files a
national read opens (one reading of the year). The new key changes every stored run's fingerprint although no record
moved. A run is re-stamped only when its stored fingerprint equals the one the OLD definition gives NOW over the
partitions that existed when the run was written (catalog `written_at` before the run's file time): then roles, labels,
lake files and engine version are all as the run saw them, and the role tables, built through `query()`'s one reading,
are the same. Any other run stays stale and is recomputed on its next call.

    python scripts/restamp_link_runs.py            # report
    python scripts/restamp_link_runs.py --apply    # re-stamp
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from pegasus_data.config import load_settings
from pegasus_data.linkage import roles, store
from pegasus_data.persist.lake import published_files
from pegasus_data.retrieve import parse_dataset


def main(apply: bool) -> None:
    settings = load_settings()
    from pegasus_data.catalog.store import CatalogStore

    cat = CatalogStore.shared(settings.catalog_path)
    written = {str(r["relative_path"]).replace("\\", "/"): str(r["written_at"])
               for r in cat.query("SELECT relative_path, written_at FROM lake_partitions")}
    cat.close()
    new_files = roles.partition_files
    lake_root = Path(settings.lake_dir)
    counts = {"restamped": 0, "current": 0, "stale": 0}
    for folder in sorted(store.links_dir(settings).iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        for report_path in sorted(folder.glob("*.json")):
            body = json.loads(report_path.read_text(encoding="utf-8"))
            run = body.get("run") or {}
            if not run.get("fingerprint"):
                continue
            key = store.RunKey(run["spec"], run["method"], run["period"], run["geography"], run["spec_digest"],
                               run.get("params") or "")
            try:
                now = store.fingerprint(settings, key)
            except Exception:  # noqa: BLE001 - a spec no longer declared: left as it is
                continue
            if run["fingerprint"] == now:
                counts["current"] += 1
                continue
            when = datetime.fromtimestamp(report_path.stat().st_mtime, UTC).isoformat(timespec="seconds")

            def old_files(dataset, year, settings_, when=when):
                system, series = parse_dataset(dataset)
                lake, files = published_files(settings_.lake_dir, system, series, year)
                keep = [f for f in files
                        if (w := written.get(f.relative_to(lake_root).as_posix())) is not None and w[:19] <= when[:19]]
                return lake, keep

            roles.partition_files = old_files
            try:
                then = store.fingerprint(settings, key)
            finally:
                roles.partition_files = new_files
            if then != run["fingerprint"]:
                counts["stale"] += 1
                continue
            counts["restamped"] += 1
            if apply:
                run["fingerprint"] = now
                body["run"] = run
                tmp = report_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, report_path)
    print(json.dumps(counts))


if __name__ == "__main__":
    main("--apply" in sys.argv)
