"""The package's layers, and the imports that go against them.

    python scripts/layers.py            # the report; exit 1 on a module-level upward import or an unplaced module
    python scripts/layers.py --lazy     # also list the function-level upward imports (the known two-way relations)

A module may import, at module level, only from its own layer or a lower one. An upward import inside a function is a
two-way relation that was kept on purpose (a declaration module that offers a reader built on the query engine): it
is counted and listed, and each one is a debt named here rather than a cycle found at import time.

The order, lowest first (`ARCHITECTURE.md` section 1a). A module is placed by the longest prefix that names it.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "pegasus_data"

LAYERS: list[tuple[str, str]] = [
    # settings, text, time arithmetic, the HTTP client: no knowledge of DATASUS
    ("base", "config locate textenc identifiers _lazy transport _vintage _geometry normalize.time normalize.types "
             "persist.staging persist.kept"),
    # what is on the server and how a file becomes a table
    ("ingest", "catalog discovery acquire decode inventory profile persist progress"),
    # what a column and a code mean: declarations, codelists, geography, the reference tables
    ("meaning", "semantics ontology registry labelpack lookups geography sidra sources _age _request _resources "
                "persist.reference persist.decisions normalize"),
    # one dataset's records, from the lake or the published files, labelled
    ("read", "representations view render_groups presentation conditions crosswalk providers retrieve api "
             "_query_engine extract snapshot pipeline build intake sources.bnafar sources.demas_api "
             "_explore _availability _dictionary"),
    # tables made from records: cubes, aggregates, graphs, links
    ("derive", "cubes fields measures _aggregate rates quality proximity careflow concepts linkage capabilities "
               "workbook suggest modelled sources.anac_air"),
    # the map of everything held
    ("describe", "_info _translate _unknowns _compendium _search verify adopt"),
    # modelled products built on all of it
    ("studies", "studies"),
    # the doors
    ("entry", "cli serve __init__"),
]

_RANK = {name: i for i, (_, names) in enumerate(LAYERS) for name in names.split()}


def layer_of(module: str) -> int | None:
    """The rank of ``module`` (dotted, relative to the package), by the longest prefix placed in `LAYERS`."""
    parts = module.split(".")
    for n in range(len(parts), 0, -1):
        rank = _RANK.get(".".join(parts[:n]))
        if rank is not None:
            return rank
    return None


def edges(pkg: Path = PKG) -> list[tuple[str, str, bool]]:
    """Every internal import as ``(importer, imported, inside_a_function)``; typing-only imports left out."""
    modules = {".".join(p.relative_to(pkg).with_suffix("").parts): p for p in pkg.rglob("*.py")}
    names = {m.removesuffix(".__init__") for m in modules}
    out: list[tuple[str, str, bool]] = []
    for module, path in modules.items():
        package = module.removesuffix(".__init__") if path.name == "__init__.py" else module.rpartition(".")[0]

        def visit(node: ast.AST, lazy: bool, importer: str = module, base: str = package) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.If) and isinstance(child.test, ast.Name) and child.test.id == "TYPE_CHECKING":
                    continue
                if isinstance(child, ast.ImportFrom):
                    if child.level:
                        up = base.split(".") if base else []
                        up = up[: len(up) - (child.level - 1)] if child.level > 1 else up
                        target = ".".join([*up, *([child.module] if child.module else [])])
                    elif child.module and child.module.split(".")[0] == "pegasus_data":
                        target = child.module.partition(".")[2]
                    else:
                        continue
                    for alias in child.names:
                        full = f"{target}.{alias.name}" if target else alias.name
                        out.append((importer, full if full in names else target, lazy))
                elif isinstance(child, ast.Import):
                    for alias in child.names:
                        if alias.name.split(".")[0] == "pegasus_data":
                            out.append((importer, alias.name.partition(".")[2], lazy))
                visit(child, lazy or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)))

        visit(ast.parse(path.read_text(encoding="utf-8")), False)
    return out


def main() -> int:
    found = edges()
    modules = sorted({m for m, _, _ in found} | {t for _, t, _ in found if t})
    unplaced = sorted(m for m in modules if layer_of(m.removesuffix(".__init__") or "__init__") is None)
    upward: list[tuple[str, str, bool]] = []
    for importer, target, lazy in found:
        a = layer_of(importer.removesuffix(".__init__") or "__init__")
        b = layer_of(target or "__init__")
        if a is not None and b is not None and b > a:
            upward.append((importer, target, lazy))
    top = sorted({(i, t) for i, t, lazy in upward if not lazy})
    lazy = Counter((i, t) for i, t, lz in upward if lz)
    total, inside = len(found), sum(1 for *_, lz in found if lz)
    print(f"{total} internal imports, {inside} inside functions; {len(top)} module-level upward, "
          f"{sum(lazy.values())} function-level upward ({len(lazy)} module pairs)")
    for name in unplaced:
        print(f"   UNPLACED {name}: add it to LAYERS")
    for importer, target in top:
        print(f"   UPWARD   {importer} -> {target}")
    if "--lazy" in sys.argv:
        for (importer, target), n in sorted(lazy.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"   lazy {n:>2}  {importer} -> {target}")
    # a cube's version leaves out the source of the layers above it (`cubes.ABOVE_CUBES`): that holds only while
    # nothing at or below the cube's layer imports them, even inside a function
    above = _above_cubes()
    derive = next(i for i, (name, _) in enumerate(LAYERS) if name == "derive")
    misplaced = sorted(m for m in above if (layer_of(m) or 0) <= derive)
    reached = sorted({(i, t) for i, t, _ in upward
                      if (layer_of(i.removesuffix(".__init__") or "__init__") or 0) <= derive and t.split(".")[0] in above})
    for name in misplaced:
        print(f"   CUBES    {name} is left out of a cube's version but is not above the cube's layer")
    for importer, target in reached:
        print(f"   CUBES    {importer} -> {target}: a module a cube may run imports a layer left out of its version")
    return 1 if top or unplaced or misplaced or reached else 0


def _above_cubes() -> tuple[str, ...]:
    """`cubes.ABOVE_CUBES`, read from the source (the script imports nothing of the package)."""
    tree = ast.parse((PKG / "cubes.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ABOVE_CUBES" for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise SystemExit("cubes.py no longer declares ABOVE_CUBES")


if __name__ == "__main__":
    sys.exit(main())
