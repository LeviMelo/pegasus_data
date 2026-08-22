"""Where the data goes, and who decided.

Placement was already overridable — ``PEGASUS_DATA_HOME``, ``--root``, ``root=``
— but only in ways you had to remember every time, and only as one directory.
Three things were missing, and all three show up as "where did my data go?":

**It followed the working directory.** ``default_root()`` was
``Path.cwd() / "pegasus_data_home"``, so running a command from a subdirectory
of your own project silently used a *different*, empty root. The catalog looked
wiped and the blobs looked lost; they were fine, one level up. Resolution now
walks up from the working directory for a data home that already exists, and
only falls back to creating one beside you.

**It could not be written down.** An environment variable lives in one shell.
A config file — project-local or per-user — is how you say "the lake lives on
D:" once.

**It was one directory for everything.** The blob cache is large, rebuildable,
and write-heavy; the lake is what you actually query; the catalog is small and
wants to be on something fast. Forcing them onto one volume is a real
constraint on a machine with a small SSD and a large spinning disk, and there
was no way to split them.

Precedence, highest first, with every layer able to set every key:

1. an explicit argument (``root=``, ``--root``)
2. an environment variable
3. the nearest project config file, walking up from the working directory
4. the per-user config file
5. the built-in default

Every resolved path carries the layer that decided it, because "which of the
five is winning?" is the only question anyone asks when a path is not what they
expected — and answering it by elimination is miserable.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CONFIG_FILENAMES",
    "PLACEMENT_KEYS",
    "Resolved",
    "config_search_path",
    "find_project_config",
    "read_config_file",
    "resolve_placement",
    "user_config_path",
    "write_config_file",
]

#: Looked for in each directory from the working directory upwards. The dotted
#: form is for people who would rather not see it; both are read, the undotted
#: one is what `config set` writes.
CONFIG_FILENAMES: tuple[str, ...] = ("pegasus-data.toml", ".pegasus-data.toml")

#: The TOML table. Nested under a table rather than at top level so the same
#: file can hold other tools' settings without collision.
CONFIG_TABLE = "pegasus-data"

#: key -> (environment variable, what it holds). `root` is the only one most
#: people need; the rest exist because a blob cache and a queryable lake do not
#: want the same disk.
PLACEMENT_KEYS: dict[str, tuple[str, str]] = {
    "root": ("PEGASUS_DATA_HOME", "everything, unless overridden below"),
    "blobs": ("PEGASUS_BLOBS_DIR", "the content-addressed download cache (large, rebuildable)"),
    "lake": ("PEGASUS_LAKE_DIR", "the Parquet lake you query"),
    "work": ("PEGASUS_WORK_DIR", "scratch space for decoding"),
    "catalog": ("PEGASUS_CATALOG_DIR", "the SQLite catalog (small, wants to be fast)"),
    "curation": ("PEGASUS_CURATION_DIR", "curated YAML; defaults to the packaged copy"),
}


@dataclass(frozen=True, slots=True)
class Resolved:
    """One path and the layer that decided it."""

    key: str
    value: Path | None
    source: str
    origin: str = ""

    def describe(self) -> str:
        return f"{self.source}{f' ({self.origin})' if self.origin else ''}"


# --------------------------------------------------------------- config files


def user_config_path() -> Path:
    """The per-user config file, at the place each platform expects.

    ``PEGASUS_CONFIG`` overrides it outright, which is what makes this testable
    without writing to a real user's home directory.
    """
    override = os.environ.get("PEGASUS_CONFIG")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "pegasus-data" / "config.toml"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "pegasus-data" / "config.toml"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base_dir / "pegasus-data" / "config.toml"


def find_project_config(start: Path | None = None) -> Path | None:
    """The nearest config file at or above ``start``.

    Walking up, like git and every build tool, so a command run from deep inside
    a project still finds the project's answer.
    """
    here = Path(start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        for name in CONFIG_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def config_search_path(start: Path | None = None) -> list[tuple[str, Path, bool]]:
    """Every file consulted, in precedence order, and whether it exists.

    Returned even when absent: "I edited the config and nothing changed" is
    almost always a file in a place nothing reads.
    """
    found: list[tuple[str, Path, bool]] = []
    project = find_project_config(start)
    if project is not None:
        found.append(("project", project, True))
    else:
        here = Path(start or Path.cwd()).resolve()
        found.append(("project", here / CONFIG_FILENAMES[0], False))
    user = user_config_path()
    found.append(("user", user, user.is_file()))
    return found


def read_config_file(path: Path) -> dict[str, object]:
    """Parse one config file. A malformed file is an error, not a shrug.

    Silently ignoring a file the user wrote on purpose is how "my setting does
    nothing" happens; the parse error names the file and the position.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return {}
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path}: not valid TOML — {exc}") from exc
    table = parsed.get(CONFIG_TABLE)
    if table is None and "tool" in parsed:
        # A pyproject.toml-style nesting, so the settings can live in a file the
        # project already has.
        table = (parsed.get("tool") or {}).get(CONFIG_TABLE)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ValueError(f"{path}: [{CONFIG_TABLE}] must be a table, not {type(table).__name__}")
    return dict(table)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_config_file(path: Path, values: dict[str, object]) -> Path:
    """Write ``values`` into ``path``'s ``[pegasus-data]`` table, preserving the rest.

    Hand-rolled rather than pulled from a dependency: the table is flat strings
    and numbers, and adding a TOML writer to a package that already reads TOML
    from the standard library would be a dependency bought for one function.

    Anything already in the file outside our table is kept verbatim. A config
    file is usually not only ours.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    kept: list[str] = []
    if path.is_file():
        in_our_table = False
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_our_table = stripped in (f"[{CONFIG_TABLE}]", f"[tool.{CONFIG_TABLE}]")
            if not in_our_table:
                kept.append(line)
        while kept and not kept[-1].strip():
            kept.pop()

    body = [f"[{CONFIG_TABLE}]"]
    for key, value in sorted(values.items()):
        if value is None:
            continue
        if isinstance(value, bool):
            body.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            body.append(f"{key} = {value}")
        else:
            body.append(f'{key} = "{_toml_escape(str(value))}"')

    text = "\n".join([*kept, "", *body]) if kept else "\n".join(body)
    from .persist.staging import staged_file

    # The same durability rule as every other write in this package: a config
    # file truncated by an interrupted write is worse than one not written.
    with staged_file(path) as staged:
        staged.write_text(text.strip() + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- resolution


def _existing_data_home(start: Path | None = None) -> Path | None:
    """A data home at or above ``start`` that has actually been used.

    Only a directory carrying a catalog or a blob store counts. An empty
    directory that happens to be named `pegasus_data_home` is not evidence of
    anything, and hijacking a command with it would be worse than the problem
    this solves.
    """
    here = Path(start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "pegasus_data_home"
        if (candidate / "_catalog").is_dir() or (candidate / "blobs").is_dir():
            return candidate
    return None


def default_data_home(start: Path | None = None) -> Resolved:
    """Where data goes when nothing said otherwise."""
    found = _existing_data_home(start)
    if found is not None:
        return Resolved("root", found, "default", "an existing data home at or above the working directory")
    here = Path(start or Path.cwd()).resolve()
    return Resolved("root", here / "pegasus_data_home", "default", "beside the working directory")


def resolve_placement(
    explicit: dict[str, Path | str | None] | None = None,
    *,
    start: Path | None = None,
) -> dict[str, Resolved]:
    """Resolve every placement key through the five layers, keeping the reason.

    ``explicit`` is what the caller passed on this call — ``root=`` or
    ``--root``. It wins, because a person naming a path in the command they are
    running has said what they mean more recently than any file.
    """
    explicit = {k: v for k, v in (explicit or {}).items() if v is not None}

    file_values: dict[str, object] = {}
    file_origin: dict[str, str] = {}
    for scope, path, exists in reversed(config_search_path(start)):
        if not exists:
            continue
        for key, value in read_config_file(path).items():
            if key in PLACEMENT_KEYS:
                file_values[key] = value
                file_origin[key] = f"{scope}: {path}"

    out: dict[str, Resolved] = {}
    for key, (env_name, _what) in PLACEMENT_KEYS.items():
        if key in explicit:
            out[key] = Resolved(key, Path(str(explicit[key])).expanduser(), "argument")
            continue
        env_value = os.environ.get(env_name)
        if env_value:
            out[key] = Resolved(key, Path(env_value).expanduser(), "environment", env_name)
            continue
        if key in file_values:
            out[key] = Resolved(
                key, Path(str(file_values[key])).expanduser(), "config file", file_origin[key]
            )
            continue
        if key == "root":
            out[key] = default_data_home(start)
        else:
            # Derived from the root unless separately placed. Left as None here
            # so Settings decides the layout; this module only decides WHERE.
            out[key] = Resolved(key, None, "derived", "from root")
    return out


def other_settings_from_files(start: Path | None = None) -> dict[str, object]:
    """Non-placement keys a config file sets, lowest precedence first.

    The throughput knobs were already environment-overridable; a file that can
    set where the data goes but not how hard to push the server would be an
    arbitrary line to draw.
    """
    values: dict[str, object] = {}
    for _scope, path, exists in reversed(config_search_path(start)):
        if not exists:
            continue
        for key, value in read_config_file(path).items():
            if key not in PLACEMENT_KEYS:
                values[key] = value
    return values
