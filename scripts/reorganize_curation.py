"""Regroup ``curation/variables/`` by system and dataset.

The folder grew by accident of how the work was done: 128 flat files named after
hashes (``sinan_36e08ceb``), waves (``cnes_b``), agent batches (``sinan_w2c_04``)
and whatever was left (``last_22``, ``misc_fill_03``). None of those names means
anything to a reader, and a SINAN batch file typically spans three unrelated
agravos, so there is no file you can open to see one form.

The ontology already says what the organising principle is:

    variables/<system>/<dataset>.yml     one file per dataset
    variables/<system>/_shared.yml       columns several datasets carry

That matches the unit the work is actually done in — a form, not an alphabet —
so the file you open to describe SINAN.BOTU is the file that holds SINAN.BOTU.

**This moves content without changing it.** Every entry is copied verbatim under
its own key; only the file it lives in changes. The run verifies that by
comparing the complete ``{(system, column): body}`` mapping before and after and
refusing to finish if they differ.

It also settles duplicates. 83 columns were defined in two files at once, and
because the loader replaces by ``(system, field_name)``, one silently won with
no record of the contest. The richer entry is kept — more described fields, then
longer description — and every choice is printed.

Usage::

    python scripts/reorganize_curation.py CATALOG --dry-run
    python scripts/reorganize_curation.py CATALOG --apply
"""

from __future__ import annotations

import argparse
import collections
import io
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pegasus_data.ontology import Ontology  # noqa: E402

ROOT = Path("src/pegasus_data/curation/variables")

#: Fields that carry meaning, used to rank two competing definitions.
_RICHNESS = (
    "description", "reasoning", "official_name", "translated_name",
    "codelist", "codelists", "notes", "source_ref", "derived", "depends_on",
)


def richness(body: dict[str, Any]) -> tuple[int, int]:
    filled = sum(1 for k in _RICHNESS if body.get(k))
    return filled, len(str(body.get("description") or ""))


def owners(conn: sqlite3.Connection, onto: Ontology) -> dict[tuple[str, str], set[str]]:
    """Which declared datasets carry each ``(system, column)``."""
    out: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for system, series, field in conn.execute(
        "SELECT s.system, s.series, sp.field_name FROM schema_presence sp "
        "JOIN strata s ON s.schema_signature = sp.schema_signature "
        "WHERE s.system IS NOT NULL"
    ):
        bound = onto.bind(str(system), str(series))
        if bound.dataset:
            out[(str(system), str(field))].add(bound.dataset)
    return out


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry-run")
    args = ap.parse_args()

    import yaml

    onto = Ontology.load()
    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    owner = owners(conn, onto)
    conn.close()

    # ---- read everything, settling duplicates as we go --------------------
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    provenance: dict[tuple[str, str], str] = {}
    file_defaults: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: list[str] = []

    for path in sorted(ROOT.rglob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        system = str(doc.get("system", "")).upper()
        if not system:
            print(f"  SKIP {path.name}: no system: key")
            continue
        defaults = {
            k: doc[k] for k in ("asserted_by", "source", "source_ref") if k in doc
        }
        for name, body in (doc.get("variables") or {}).items():
            key = (system, str(name))
            body = dict(body or {})
            if key in entries:
                keep_new = richness(body) > richness(entries[key])
                duplicates.append(
                    f"{system}.{name}: {provenance[key]} vs {path.name} -> kept "
                    f"{path.name if keep_new else provenance[key]}"
                )
                if not keep_new:
                    continue
            entries[key] = body
            provenance[key] = path.name
            file_defaults[key] = defaults

    print(f"read {len(entries)} entries from {len(list(ROOT.rglob('*.yml')))} files")
    if duplicates:
        print(f"\nduplicate definitions settled: {len(duplicates)}")
        for line in duplicates[:12]:
            print(f"  {line}")
        if len(duplicates) > 12:
            print(f"  ... and {len(duplicates) - 12} more")

    # ---- assign each entry to a file --------------------------------------
    buckets: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
    for (system, name), body in entries.items():
        datasets = owner.get((system, name), set())
        if len(datasets) == 1:
            slug = next(iter(datasets)).split(".", 1)[-1].lower()
        elif datasets:
            slug = "_shared"
        else:
            # Described but never observed in a stratum — keep it rather than
            # lose it, and name the bucket so it is obviously a residue.
            slug = "_unobserved"
        buckets[(system, slug)].append((name, body))

    print(f"\nwould write {len(buckets)} files across "
          f"{len({s for s, _ in buckets})} systems")
    by_system: collections.Counter = collections.Counter()
    for (system, slug), items in sorted(buckets.items()):
        by_system[system] += len(items)
    for system, n in by_system.most_common():
        files = sorted(slug for s, slug in buckets if s == system)
        print(f"  {system:<18} {n:5d} columns in {len(files):3d} files: "
              f"{', '.join(files[:6])}{' …' if len(files) > 6 else ''}")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return

    # ---- write ------------------------------------------------------------
    staging = ROOT.parent / "_variables_new"
    if staging.exists():
        shutil.rmtree(staging)
    for (system, slug), items in sorted(buckets.items()):
        node = onto.resolve(f"{system}.{slug}") if not slug.startswith("_") else None
        folder = staging / system.lower()
        folder.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if node and node[0] == "dataset":
            dataset = node[1]
            lines.append(f"# {dataset.code} — {dataset.translated_name or ''}".rstrip())
            if dataset.official_name:
                lines.append(f"# {dataset.official_name}")
            if dataset.what_it_is:
                lines.append("#")
                for line in _wrap(dataset.what_it_is, 76):
                    lines.append(f"# {line}")
        elif slug == "_shared":
            lines.append(f"# {system} — columns carried by more than one dataset.")
            lines.append("#")
            lines.append("# The notification header and other cross-dataset fields. Described once")
            lines.append("# against the system, because that is the scope on which they are the")
            lines.append("# same column.")
        else:
            lines.append(f"# {system} — described columns not observed in any stratum.")
            lines.append("#")
            lines.append("# Kept rather than dropped: a description whose column the crawl has not")
            lines.append("# seen is a lead, not a mistake. It may belong to a generation that was")
            lines.append("# never sampled, or to a dataset published since the last crawl.")
        lines.append(f"system: {system}")
        defaults = file_defaults.get((system, items[0][0]), {})
        if defaults.get("asserted_by"):
            lines.append(f"asserted_by: {defaults['asserted_by']}")
        lines.append("")
        lines.append("variables:")
        body_doc = {name: body for name, body in sorted(items)}
        dumped = yaml.safe_dump(
            body_doc, allow_unicode=True, sort_keys=False, width=79, default_flow_style=False
        )
        lines.extend("  " + ln if ln.strip() else "" for ln in dumped.split("\n"))
        (folder / f"{slug}.yml").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # ---- verify, then swap ------------------------------------------------
    after: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(staging.rglob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        system = str(doc.get("system", "")).upper()
        for name, body in (doc.get("variables") or {}).items():
            after[(system, str(name))] = dict(body or {})

    missing = set(entries) - set(after)
    added = set(after) - set(entries)
    changed = [k for k in set(entries) & set(after) if entries[k] != after[k]]
    if missing or added or changed:
        print(f"\nREFUSING TO SWAP — content would change: "
              f"{len(missing)} lost, {len(added)} invented, {len(changed)} altered")
        for k in list(missing)[:5]:
            print(f"  lost: {k}")
        for k in changed[:5]:
            print(f"  altered: {k}")
        return

    shutil.rmtree(ROOT)
    staging.rename(ROOT)
    print(f"\nverified {len(after)} entries identical; swapped into place")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    main()
