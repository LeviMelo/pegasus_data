"""One home per job, declared and checked: where each recurring job is done, and who still does it beside.

    python scripts/homes.py              # the report; exit 1 on a new second implementation, or on a debt no longer owed
    python scripts/homes.py archive      # the jobs whose name holds the word: its home, to read before writing

"Replace, never build beside" (CLAUDE.md §4) failed by forgetting, not by choice: a session that needs to open a zip
writes `zipfile.ZipFile`, and nothing tells it `decode/archives.py` exists. On 2026-11-27 one change added a fifth
archive reader, a sixth spreadsheet reader and a hand list beside IBGE's own names; on 2026-11-28 the package opened
DuckDB connections in 38 places, 28 without a memory limit (ADR-0245).

Each job below names the call that does it (a regex over the package's source), its **home** (the modules that may
make that call) and its **debts** (the modules that still make it beside the home, each to be moved; ARCHITECTURE §5
holds the story of each). The check fails when:
- a module that is neither home nor debt makes the call: a new parallel implementation. Use the home, or extend it.
- a debt no longer makes the call: it was paid; remove it from the list, so the list is only what is owed.

A debt is never added to make the check pass. A job that is not a call pattern (how a municipality written by name is
placed, how a field is declared) cannot be checked here: ARCHITECTURE §5 and §6 are where those are found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "pegasus_data"

JOBS: list[dict[str, object]] = [
    {"job": "open a DuckDB connection (memory limit, spill directory)",
     "call": r"duckdb\.connect\(|memory_limit",
     "home": ["duckdb_session.py"],
     "debts": []},
    {"job": "open an archive (zip, RAR, 7z, tar, LHA)",
     "call": r"zipfile\.ZipFile\(|tarfile\.open\(|\bpy7zr\b|\brarfile\b",
     "home": ["decode/archives.py", "decode/lha.py"],
     "debts": ["_holdings.py", "concepts.py", "geography.py", "inventory/schemas.py", "pipeline.py", "sources/anac_air.py",
               "sources/census_codes.py", "sources/census_commuting.py", "sources/ibge_arranjos.py", "sources/ibge_cnefe.py",
               "sources/ibge_tracts.py", "sources/sigtap.py", "sources/tuss.py"]},
    {"job": "read a spreadsheet (xls, xlsx, ods) as a table",
     "call": r"read_excel\(|\bxlrd\.|openpyxl\.load_workbook",
     "home": ["decode/spreadsheet.py"],
     "debts": ["decode/text_.py", "proximity.py", "sources/anac_air.py", "sources/census_commuting.py", "sources/ibge_links.py",
               "sources/ibge_tracts.py", "sources/tuss.py"]},
    {"job": "make an HTTP request (retries, pacing, resume, the browser agent)",
     "call": r"\bhttpx\.(get|post|stream|Client)\(|urllib\.request\.urlopen\(|\brequests\.(get|post)\(",
     "home": ["transport.py"],
     "debts": ["discovery/https_client.py"]},
    {"job": "open an FTP connection",
     "call": r"ftplib\.FTP\(",
     "home": ["discovery/ftp_client.py"],
     "debts": []},
    {"job": "fold a name for comparison (accents, case, hyphens)",
     "call": r"unicodedata\.normalize\(",
     "home": ["textenc.py"],
     "debts": ["labelpack.py"]},
    {"job": "read a curation YAML",
     "call": r"\byaml\.(safe_)?load\(",
     "home": ["semantics/curation.py"],
     "debts": []},
    {"job": "ask the machine how much memory is free (admission, floors)",
     "call": r"psutil\.virtual_memory\(",
     "home": ["decode/admission.py", "duckdb_session.py"],
     "debts": ["concurrency.py", "intake.py", "persist/lake.py", "sidra/session.py", "snapshot.py"]},
    {"job": "put a finished file in place of another (a reader may hold the old one: Windows refuses)",
     "call": r"os\.replace\(",
     "home": ["persist/staging.py"],
     "debts": ["_compendium.py", "acquire/cache.py", "catalog/seed.py", "decode/_native/__init__.py", "persist/lake.py"]},
]


def users(call: str, pkg: Path = PKG) -> list[str]:
    """The package's modules whose source makes ``call``."""
    pattern = re.compile(call)
    return sorted(p.relative_to(pkg).as_posix() for p in pkg.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8")))


def report(jobs: list[dict[str, object]] = JOBS, pkg: Path = PKG) -> tuple[list[str], list[str]]:
    """``(lines, failures)``: every job with its home and what is owed, and what breaks the rule."""
    lines: list[str] = []
    failures: list[str] = []
    for job in jobs:
        home, debts = list(job["home"]), list(job["debts"])  # type: ignore[call-overload]
        found = users(str(job["call"]), pkg)
        new = [m for m in found if m not in home and m not in debts]
        paid = [m for m in debts if m not in found]
        lines.append(f"{job['job']}\n    home: {', '.join(home)}\n    owed: {len(debts) - len(paid)}"
                     + (f" ({', '.join(m for m in debts if m not in paid)})" if len(debts) > len(paid) else ""))
        failures += [f"{m} does '{job['job']}' beside its home ({', '.join(home)}): call the home, or extend it" for m in new]
        failures += [f"{m} no longer does '{job['job']}' itself: remove it from the job's debts in scripts/homes.py" for m in paid]
    return lines, failures


def main() -> int:
    words = [w.lower() for w in sys.argv[1:]]
    jobs = [j for j in JOBS if all(w in str(j["job"]).lower() for w in words)]
    lines, failures = report(jobs)
    print("\n".join(lines))
    owed = sum(len(j["debts"]) for j in jobs)  # type: ignore[arg-type]
    print(f"\n{len(jobs)} jobs, {owed} second implementations still owed")
    for failure in failures:
        print("FAIL", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
