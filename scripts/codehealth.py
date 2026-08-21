"""An AST scan of the package: what is dead, duplicated, tangled or silent.

This is a *diagnostic*, not a linter. Ruff already catches style; what it does
not catch is the shape of the codebase — a function no caller reaches, two
functions that are the same function, an ``except Exception: pass`` that turns
a bug into a shrug.

Every check here earned its place by having produced a real defect in this
repository at least once:

``shadowed``
    ``from pegasus_data import explore`` returned the *module*, not the
    function, because a submodule binds over a same-named attribute.
``swallowed``
    A broad ``except Exception: return`` hid a locked catalog, presenting
    missing data as absent data.
``duplicate``
    Two accumulators for partition axes drifted into disagreeing about whether
    a dataset was filterable.

Run::

    python scripts/codehealth.py            # the report
    python scripts/codehealth.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "pegasus_data"

#: Names that look unreferenced because the reference is not a plain name:
#: dunders, entry points, dataclass and context-manager hooks.
_ALWAYS_LIVE = {
    "main", "__init__", "__repr__", "__str__", "__len__", "__iter__",
    "__getattr__", "__enter__", "__exit__", "__post_init__", "__eq__",
    "__hash__", "__contains__", "__call__", "__lt__", "__bool__",
    "__dir__", "__getitem__", "__reduce__",
}

#: A decision point, for cyclomatic complexity.
_BRANCH = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.Assert, ast.IfExp, ast.comprehension,
)

#: Any identifier-shaped token, for names that appear only inside string
#: annotations such as ``"Iterable[Mapping[str, Any]]"``.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_NESTING = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)


@dataclass
class Func:
    module: str
    qualname: str
    line: int
    end: int
    params: int
    complexity: int
    depth: int
    body_hash: str
    statements: int
    has_doc: bool
    is_public: bool

    @property
    def length(self) -> int:
        return self.end - self.line + 1


@dataclass
class Report:
    modules: int = 0
    functions: list[Func] = field(default_factory=list)
    findings: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, kind: str, **fields: Any) -> None:
        self.findings[kind].append(fields)


def _depth(node: ast.AST, level: int = 0) -> int:
    """Deepest nesting of control flow inside a body."""
    best = level
    for child in ast.iter_child_nodes(node):
        step = 1 if isinstance(child, _NESTING) else 0
        best = max(best, _depth(child, level + step))
    return best


def _complexity(node: ast.AST) -> int:
    total = 1
    for child in ast.walk(node):
        if isinstance(child, _BRANCH):
            total += 1
        elif isinstance(child, ast.BoolOp):
            total += len(child.values) - 1
    return total


class _Blank(ast.NodeTransformer):
    """Erase identifiers so copy-paste survives a rename."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(ast.arg(arg="_", annotation=None), node)


def _normalized(body: list[ast.stmt]) -> str:
    module = ast.Module(body=body, type_ignores=[])
    try:
        reparsed = ast.parse(ast.unparse(module))
    except (SyntaxError, ValueError, RecursionError):
        return ""
    return ast.dump(_Blank().visit(reparsed), annotate_fields=False)


def _real(body: list[ast.stmt]) -> list[ast.stmt]:
    """Statements minus the docstring."""
    return [
        s for s in body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]


def _is_silent(handler: ast.ExceptHandler) -> bool:
    inner = _real(handler.body)
    if not inner:
        return False
    for stmt in inner:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Return) and (
            stmt.value is None
            or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
        ):
            continue
        return False
    return True


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id in {
        "Exception", "BaseException"
    }


def scan(pkg: Path = PKG) -> Report:
    report = Report()
    defined: dict[str, list[tuple[str, int]]] = defaultdict(list)
    referenced: set[str] = set()
    imports: dict[str, set[str]] = {}
    by_hash: dict[str, list[Func]] = defaultdict(list)

    for path in sorted(pkg.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        module = ".".join(path.relative_to(pkg).with_suffix("").parts)
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - a broken file is its own finding
            report.add("syntax", module=module, line=exc.lineno or 0, detail=str(exc))
            continue
        report.modules += 1

        lines = source.splitlines()
        if len(lines) > 900:
            report.add("long_module", module=module, lines=len(lines))

        imports[module] = set()
        bound: dict[str, int] = {}
        used: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bound[(alias.asname or alias.name).split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    imports[module].add(node.module or "")
                for alias in node.names:
                    bound[alias.asname or alias.name] = node.lineno
                    referenced.add(alias.name)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # a name used only inside a string annotation still counts
                used.update(_IDENT.findall(node.value))

        for name, line in sorted(bound.items(), key=lambda kv: kv[1]):
            if name not in used and name != "annotations":
                report.add("unused_import", module=module, line=line, name=name)

        def walk(node: ast.AST, prefix: str = "") -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qual = prefix + child.name
                    a = child.args
                    params = (
                        len(a.args) + len(a.posonlyargs) + len(a.kwonlyargs)
                        + bool(a.vararg) + bool(a.kwarg)
                    )
                    body = _real(child.body)
                    func = Func(
                        module=module,
                        qualname=qual,
                        line=child.lineno,
                        end=child.end_lineno or child.lineno,
                        params=params,
                        complexity=_complexity(child),
                        depth=_depth(child),
                        statements=len(body),
                        body_hash=_normalized(body) if len(body) >= 4 else "",
                        has_doc=ast.get_docstring(child) is not None,
                        is_public=not child.name.startswith("_"),
                    )
                    report.functions.append(func)
                    defined[child.name].append((module, child.lineno))
                    if func.body_hash:
                        by_hash[func.body_hash].append(func)

                    for handler in ast.walk(child):
                        if not isinstance(handler, ast.ExceptHandler):
                            continue
                        if _is_silent(handler) and _is_broad(handler):
                            # A silent handler is defensible; an UNEXPLAINED one
                            # is not. Anything with a comment in it has had the
                            # decision made on purpose, and the report should
                            # separate the two rather than crying wolf 18 times.
                            span = lines[handler.lineno - 1:(handler.end_lineno
                                                             or handler.lineno)]
                            report.add(
                                "swallowed", module=module, line=handler.lineno,
                                func=qual,
                                excused=any("#" in ln for ln in span),
                            )
                    kw = [d for d in a.kw_defaults if d is not None]
                    for default in list(a.defaults) + kw:
                        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                            report.add("mutable_default", module=module,
                                       line=child.lineno, func=qual)
                    walk(child, prefix=qual + ".")
                elif isinstance(child, ast.ClassDef):
                    defined[child.name].append((module, child.lineno))
                    walk(child, prefix=prefix + child.name + ".")
                else:
                    walk(child, prefix=prefix)

        walk(tree)

    # A submodule only shadows something if the package it lives in also binds
    # that name — ``pegasus_data.explore`` the module over ``explore`` the
    # function. Two unrelated modules sharing a leaf name collide with nothing.
    for module in imports:
        leaf = module.split(".")[-1]
        if leaf.startswith("__"):
            continue
        parent = module.rsplit(".", 1)[0] if "." in module else ""
        owner = f"{parent}.__init__" if parent else "__init__"
        holders = [m for m, _ in defined.get(leaf, ()) if m == owner]
        if holders:
            report.add("shadowed", module=module, name=leaf, bound_in=owner)

    for func in report.functions:
        if "." in func.qualname:
            continue
        name = func.qualname
        if name in _ALWAYS_LIVE:
            continue
        if name.startswith("_") and name not in referenced:
            report.add("dead", module=func.module, line=func.line, name=name)

    for group in by_hash.values():
        if len(group) > 1:
            report.add(
                "duplicate", statements=group[0].statements,
                where=[f"{f.module}:{f.line} {f.qualname}" for f in group],
            )

    graph = {m: {i for i in deps if i in imports} for m, deps in imports.items()}
    seen: set[str] = set()

    def find_cycle(node: str, path: list[str]) -> list[str] | None:
        if node in path:
            return path[path.index(node):] + [node]
        if node in seen:
            return None
        seen.add(node)
        for nxt in sorted(graph.get(node, ())):
            found = find_cycle(nxt, path + [node])
            if found:
                return found
        return None

    for module in sorted(graph):
        cycle = find_cycle(module, [])
        if cycle:
            report.add("cycle", chain=" -> ".join(cycle))

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="AST health scan of pegasus_data")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = scan()
    funcs = report.functions

    if args.json:
        print(json.dumps({
            "modules": report.modules,
            "functions": len(funcs),
            "findings": dict(report.findings),
        }, indent=2))
        return 0

    print(f"{report.modules} modules, {len(funcs)} functions")
    print()

    def show(kind: str, title: str, fmt, limit: int = 12) -> None:
        rows = report.findings.get(kind) or []
        if not rows:
            return
        print(f"{title} ({len(rows)})")
        for row in rows[:limit]:
            print("   " + fmt(row))
        if len(rows) > limit:
            print(f"   ... and {len(rows) - limit} more")
        print()

    show("syntax", "UNPARSEABLE", lambda r: f"{r['module']}:{r['line']} {r['detail']}")
    show("shadowed", "SHADOWED - submodule collides with a function name",
         lambda r: f"{r['module']} — {r['name']} also bound in {r['bound_in']}")
    show("cycle", "IMPORT CYCLE", lambda r: r["chain"])
    bare = [r for r in report.findings.get("swallowed", []) if not r["excused"]]
    if bare:
        print(f"SWALLOWED EXCEPTION - broad except, silent, no comment ({len(bare)})")
        for row in bare[:25]:
            print(f"   {row['module']}:{row['line']} in {row['func']}")
        print()
    explained = len(report.findings.get("swallowed", [])) - len(bare)
    if explained:
        print(f"   ({explained} further silent handlers carry a comment "
              f"explaining the choice)")
        print()
    show("mutable_default", "MUTABLE DEFAULT ARGUMENT",
         lambda r: f"{r['module']}:{r['line']} {r['func']}")
    show("duplicate", "DUPLICATE BODY - identical after renaming",
         lambda r: f"{r['statements']} stmts: " + " == ".join(r["where"]))
    show("dead", "UNREFERENCED PRIVATE FUNCTION",
         lambda r: f"{r['module']}:{r['line']} {r['name']}", limit=25)
    show("unused_import", "UNUSED IMPORT",
         lambda r: f"{r['module']}:{r['line']} {r['name']}", limit=25)
    show("long_module", "LONG MODULE", lambda r: f"{r['module']}  {r['lines']} lines")

    print("MOST BRANCHING")
    for f in sorted(funcs, key=lambda f: -f.complexity)[:12]:
        print(f"   {f.complexity:>3} cx  {f.length:>4} lines  depth {f.depth}  "
              f"{f.module}:{f.line} {f.qualname}")
    print()

    print("LONGEST")
    for f in sorted(funcs, key=lambda f: -f.length)[:10]:
        print(f"   {f.length:>4} lines  {f.statements:>3} stmts  "
              f"{f.module}:{f.line} {f.qualname}")
    print()

    wide = [f for f in funcs if f.params > 10]
    if wide:
        print("WIDE SIGNATURES (>10 parameters)")
        for f in sorted(wide, key=lambda f: -f.params):
            print(f"   {f.params:>3} params  {f.module}:{f.line} {f.qualname}")
        print()

    public = [f for f in funcs if f.is_public and "." not in f.qualname]
    undocumented = [f for f in public if not f.has_doc]
    print(f"DOCSTRINGS: {len(public) - len(undocumented)}/{len(public)} public "
          f"module-level functions documented")
    for f in undocumented[:10]:
        print(f"   missing: {f.module}:{f.line} {f.qualname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
