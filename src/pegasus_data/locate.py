"""Where the data goes, and who decided.

Placement was already overridable — ``PEGASUS_DATA_HOME``, ``--root``, ``root=``
— but only in ways you had to remember every time, and only as one directory.
Three things were missing, and all three show up as "where did my data go?":

**It followed the working directory.** ``default_root()`` was
``Path.cwd() / "pegasus_data_home"``, so running a command from a subdirectory
of your own project silently used a *different*, empty root. A walk up to the
nearest existing home (2026-09) only narrowed this. Every project that named no
root still grew its own home, and each one downloaded again what another
already held. On 2026-10-24 one machine had eight homes: 11.6 GB fetched into
the repository's home on 23/10 alone, most of it already in the per-user home.
The built-in default is now ONE per-user data directory, whatever the working
directory (:func:`default_data_home`). A project that wants a home of its own
says so in its config file.

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

**An explicit root carries its places with it.** The catalog under a root lists the
lake's partitions relative to that root's lake and the blobs it holds, so an
explicit ``root=X`` (``--root X``) with ``PEGASUS_LAKE_DIR`` or a config file's
``lake`` still in force opened the catalog of X over another lake. Under an
explicit root, ``blobs``, ``lake``, ``work`` and ``catalog`` are X's own unless the
same call names them; the layers it overrides are named in ``origins``. (The
curated YAML is code, not data: it keeps its layers.)
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
    "UNDER_ROOT",
    "Resolved",
    "config_search_path",
    "find_project_config",
    "read_config_file",
    "resolve_placement",
    "scratch_dir",
    "use_scratch",
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

#: The places that live under the data home: an explicit root decides them, not the environment or a file.
UNDER_ROOT: tuple[str, ...] = ("blobs", "lake", "work", "catalog")

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


# ------------------------------------------------------------------ scratch


def use_scratch(work_dir: str | Path) -> None:
    """Make ``work_dir`` the decoders' scratch space for this process and the worker processes it starts (they inherit
    the environment). An explicit ``PEGASUS_WORK_DIR`` already in the environment wins."""
    os.environ.setdefault(PLACEMENT_KEYS["work"][0], str(work_dir))


def scratch_dir() -> str | None:
    """Where a decoder's temporary files go: the ``work`` placement, created on demand, else the system temp (``None``).

    Every inflated DBF, spool and staged archive was made on the system drive whatever ``work`` said; 1.7 GB of
    `pegasus_decode_*`, 2.0 GB of `pegasus_dbc_*` and 174 database copies were found there (2026-10-14)."""
    value = os.environ.get(PLACEMENT_KEYS["work"][0])
    if not value:
        return None
    path = Path(value).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return str(path)


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
        # the roaming profile, from the user's home when APPDATA is not set: a scheduled task runs without it, and the
        # config was then looked for under ~/.config, so its home fell to the empty default and every run downloaded
        # into it (nees-gt-ms's daily update, 2026-11-27)
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "pegasus-data" / "config.toml"
    if sys.platform == "darwin":
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


def default_data_home() -> Resolved:
    """Where data goes when nothing said otherwise: the per-user data directory, never the working directory.

    The place each platform keeps a user's large, machine-local application data
    (not the roaming profile on Windows): ``%LOCALAPPDATA%/pegasus-data``,
    ``~/Library/Application Support/pegasus-data``,
    ``$XDG_DATA_HOME/pegasus-data`` (``~/.local/share``).
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return Resolved("root", base / "pegasus-data", "default", "the per-user data directory")


class UnreadUserConfig(RuntimeError):
    """The data home fell to the default while a user config that places it exists where this process did not look."""


def _refuse_unread_user_config(start: Path | None) -> None:
    """Refuse the default home when a per-user config that sets a root exists at a standard place this resolution did not
    read (a process whose environment lacks APPDATA or XDG_CONFIG_HOME): falling silently to an empty home downloads into
    it, the failure nees-gt-ms's daily task met (2026-11-27). ``PEGASUS_CONFIG`` (the tests' and a deliberate choice)
    decides alone."""
    if os.environ.get("PEGASUS_CONFIG"):
        return
    read = {path.resolve() for _scope, path, exists in config_search_path(start) if exists}
    candidates = [Path.home() / "AppData" / "Roaming" / "pegasus-data" / "config.toml",
                  Path.home() / ".config" / "pegasus-data" / "config.toml"]
    for candidate in candidates:
        if candidate.is_file() and candidate.resolve() not in read and "root" in read_config_file(candidate):
            raise UnreadUserConfig(
                f"no data home was found for this process, but {candidate} sets one: its environment lacks the variable "
                "that points to it (APPDATA, XDG_CONFIG_HOME). Set PEGASUS_DATA_HOME, or run it with that variable, rather "
                "than let it fill the empty default home")


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
        if "root" in explicit and key in UNDER_ROOT:
            overridden = [f"{env_name}={os.environ[env_name]}"] if os.environ.get(env_name) else []
            overridden += [f"{file_origin[key]}: {key}={file_values[key]}"] if key in file_values else []
            out[key] = Resolved(key, None, "derived",
                                "from the explicit root" + (f"; not used: {'; '.join(overridden)}" if overridden else ""))
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
            _refuse_unread_user_config(start)
            out[key] = default_data_home()
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
