"""Are the documents internally consistent, and do they describe the code?

The `.md` files are the interface to this project (CLAUDE.md §9): `CLAUDE.md`
routes by pointer, `DECISIONS.md` and `EVALUATION.md` index one file per entry
under `docs/`, `OPEN_QUESTIONS.md` is a live table, and `ARCHITECTURE.md` is
the map of the code. They are read by people and models who cannot check a
claim against the code, so a dangling `ADR-0031` or a module missing from the
map is a false statement about the project, not a typo.

Checks, all mechanical, none of them opinions about the prose:

    1  every ADR-NNNN referenced anywhere exists under docs/decisions/
    2  every OQ-N referenced anywhere is an open row, a resolved row, or named
       in a decision
    3  ADR numbers are unique and contiguous, and each is in the index
    4  every evaluation entry is in the index, and every docs/ link resolves
    5  every script named in a current document exists in scripts/
    6  every module under src/pegasus_data is named in ARCHITECTURE.md, and
       every module ARCHITECTURE.md names exists
    7  every public name exported by pegasus_data is mentioned in
       ARCHITECTURE.md or README.md
    8  CLAUDE.md and AGENTS.md are byte-for-byte copies

`docs/history/` is frozen: it is scanned for nothing.

Exits non-zero when anything fails.

    python scripts/check_docs.py
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
EVALUATION = ROOT / "docs" / "evaluation"
RESOLVED = ROOT / "docs" / "history" / "open_questions_resolved.md"
PACKAGE = ROOT / "src" / "pegasus_data"

ADR_REF = re.compile(r"ADR-(\d{4})")
OQ_REF = re.compile(r"\bOQ-(\d{1,3})\b")
SCRIPT_REF = re.compile(r"scripts/([A-Za-z0-9_/]+\.py)")
LINK = re.compile(r"\]\((docs/[^)#\s]+\.md)\)")
ROW = re.compile(r"^\|\s*(\d{1,3})\s*\|", re.MULTILINE)
MODULE_REF = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*(?:\.py|/))`")


def current_documents() -> dict[str, str]:
    """Every document that describes the project as it is: the top level and
    the decision and evaluation entries. Not `docs/history/`."""
    out = {p.name: p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("*.md"))}
    for folder in (DECISIONS, EVALUATION):
        for p in sorted(folder.glob("*.md")):
            out[f"{folder.name}/{p.name}"] = p.read_text(encoding="utf-8")
    return out


def package_modules() -> set[str]:
    """Modules as ARCHITECTURE.md names them: `api.py`, `decode/dbf.py`, and a
    subpackage as `decode/`. Private C sources and caches are not modules."""
    out: set[str] = set()
    for p in PACKAGE.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(PACKAGE).as_posix()
        if rel.endswith("__init__.py"):
            parent = rel[: -len("__init__.py")]
            if parent:
                out.add(parent)
            continue
        out.add(rel)
    return out


def public_names() -> list[str]:
    """The names `pegasus_data.__init__` exports lazily or directly."""
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if not (isinstance(target, ast.Name) and isinstance(getattr(node, "value", None), (ast.Dict, ast.List))):
            continue
        if target.id == "_EXPORTS" and isinstance(node.value, ast.Dict):
            names += [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
        elif target.id == "__all__" and isinstance(node.value, ast.List):
            names += [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    return sorted(set(names) - {"__version__"})


def main() -> int:
    docs = current_documents()
    print(f"{len(docs)} current documents, {sum(len(v.splitlines()) for v in docs.values()):,} lines")
    failures: list[str] = []

    # 1 + 3. ADRs: one file each, contiguous, all indexed.
    files = {
        int(m.group(1)): p.name for p in DECISIONS.glob("ADR-*.md") if (m := re.match(r"ADR-(\d{4})", p.name))
    }
    defined = sorted(files)
    gaps = [n for n in range(defined[0], defined[-1] + 1) if n not in files] if defined else []
    if gaps:
        failures.append(f"missing ADR numbers: {gaps}")
    index = docs.get("DECISIONS.md", "")
    for n, name in files.items():
        if f"docs/decisions/{name}" not in index:
            failures.append(f"ADR-{n:04d} ({name}) is not in the DECISIONS.md index")
    if defined:
        print(f"  ADR-{defined[0]:04d} to ADR-{defined[-1]:04d}, {len(defined)} files, {len(gaps)} gaps")
    for name, text in docs.items():
        for num in sorted({int(m) for m in ADR_REF.findall(text)}):
            if num not in files:
                failures.append(f"{name} references ADR-{num:04d}, which does not exist")

    # 2. Open questions.
    open_rows = {int(m) for m in ROW.findall(docs.get("OPEN_QUESTIONS.md", ""))}
    resolved_rows = (
        {int(m) for m in ROW.findall(RESOLVED.read_text(encoding="utf-8"))} if RESOLVED.exists() else set()
    )
    in_decisions = {
        int(m) for name, text in docs.items() if name.startswith("decisions/") for m in OQ_REF.findall(text)
    }
    known = open_rows | resolved_rows | in_decisions
    print(f"  {len(open_rows)} open questions, {len(resolved_rows)} resolved rows")
    for name, text in docs.items():
        for num in sorted({int(m) for m in OQ_REF.findall(text)}):
            if num not in known:
                failures.append(f"{name} references OQ-{num}, which is neither a row nor named in a decision")

    # 4. Evaluation entries all indexed; every docs/ link resolves.
    ev_index = docs.get("EVALUATION.md", "")
    for p in EVALUATION.glob("*.md"):
        if p.name != "methods.md" and f"docs/evaluation/{p.name}" not in ev_index:
            failures.append(f"docs/evaluation/{p.name} is not in the EVALUATION.md index")
    for name, text in docs.items():
        for link in sorted(set(LINK.findall(text))):
            if not (ROOT / link).exists():
                failures.append(f"{name} links {link}, which does not exist")

    # 5. Scripts.
    have = {p.relative_to(ROOT / "scripts").as_posix() for p in (ROOT / "scripts").rglob("*.py")}
    for name, text in docs.items():
        for script in sorted(set(SCRIPT_REF.findall(text))):
            if script not in have:
                failures.append(f"{name} names scripts/{script}, which does not exist")
    print(f"  {len(have)} scripts on disk")

    # 6. The module map is complete and names nothing that is gone.
    arch = docs.get("ARCHITECTURE.md", "")
    modules = package_modules()
    named = set(MODULE_REF.findall(arch))
    for module in sorted(modules):
        if f"`{module}`" not in arch:
            failures.append(f"ARCHITECTURE.md does not name the module `{module}`")
    for module in sorted(named):
        # Only names that look like package paths are checked; `scripts/x.py`
        # and `tools/x.py` are checked by rule 5 or are not modules.
        if module.startswith(("scripts/", "tools/", "tests/", "docs/")):
            continue
        if module not in modules and (module.endswith(".py") or module.endswith("/")):
            if (PACKAGE / module).exists():
                continue
            failures.append(f"ARCHITECTURE.md names `{module}`, which is not a module")
    print(f"  {len(modules)} modules")

    # 7. Every public name is documented somewhere a reader looks.
    readme = docs.get("README.md", "")
    names = public_names()
    for public in names:
        if not re.search(rf"\b{re.escape(public)}\b", arch + readme):
            failures.append(f"the public name `{public}` is in neither ARCHITECTURE.md nor README.md")
    print(f"  {len(names)} public names")

    # 8. CLAUDE.md and AGENTS.md are the same file under two names.
    claude, agents = ROOT / "CLAUDE.md", ROOT / "AGENTS.md"
    if not agents.is_file():
        failures.append("AGENTS.md does not exist; it must be a copy of CLAUDE.md")
    elif claude.read_bytes() != agents.read_bytes():
        failures.append("CLAUDE.md and AGENTS.md differ; they must be byte-for-byte copies")
    else:
        print(f"  CLAUDE.md and AGENTS.md agree ({len(claude.read_text(encoding='utf-8').splitlines())} lines)")

    print()
    if failures:
        print(f"{len(failures)} problems:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("consistent: every ADR, open question, evaluation entry, script, module and public name checks out.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
