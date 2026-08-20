"""Runtime configuration: where things live, how hard we push the server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOST = "ftp.datasus.gov.br"
DEFAULT_BASE_PATH = "/dissemin/publicos"
DEMAS_BASE_URL = "https://apidadosabertos.saude.gov.br"
DEMAS_SWAGGER_PATH = "/static/swagger.json"

#: Brazilian federal units plus the national aggregate token used in filenames.
UF_CODES: frozenset[str] = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO", "BR",
    }
)

#: IBGE two-digit numeric UF codes (11..53, with gaps) mapped to their abbreviation.
UF_NUMERIC: dict[str, str] = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA",
    "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS",
    "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}
UF_TO_NUMERIC: dict[str, str] = {v: k for k, v in UF_NUMERIC.items()}


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


def default_root() -> Path:
    """Root of the local data lake and cache.

    Overridable with ``PEGASUS_DATA_HOME``; defaults to ``./pegasus_data_home``
    so a checkout stays self-contained and nothing is written outside the project
    unless the user says so.
    """
    return _env_path("PEGASUS_DATA_HOME", Path.cwd() / "pegasus_data_home")


@dataclass(slots=True)
class Settings:
    """Everything the pipeline needs to know about placement and throughput."""

    root: Path = field(default_factory=default_root)
    host: str = DEFAULT_HOST
    base_path: str = DEFAULT_BASE_PATH

    # Throughput. The server is slow and drops connections; 8 control channels is
    # the empirically safe starting point recorded in the architecture brief.
    connections: int = 8
    fetch_concurrency: int = 8
    process_workers: int = max(1, (os.cpu_count() or 4) - 1)
    timeout: int = 60
    max_retries: int = 4
    backoff_base: float = 1.5

    # Profiling budgets.
    profile_row_limit: int = 200_000
    max_distinct_tracked: int = 50_000
    top_values_kept: int = 200

    # Storage behaviour.
    #: Override for where curated YAML lives; None means the packaged directory.
    curation_root: Path | None = None

    #: No stage may hang silently (§A). A single work item that outlives
    #: `item_timeout` is abandoned and recorded; a stage that goes
    #: `stall_timeout` with nothing completing gives up on the batch. Both are
    #: generous — they exist to catch a stall, not to punish a slow file.
    item_timeout: float = 1200.0
    stall_timeout: float = 1800.0
    heartbeat_interval: float = 30.0
    keep_raw: bool = False
    compression: str = "zstd"
    row_group_size: int = 256 * 1024

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser()

    # ------------------------------------------------------------------ paths

    @property
    def catalog_path(self) -> Path:
        return self.root / "_catalog" / "catalog.sqlite"

    @property
    def curation_dir(self) -> Path:
        """Where the curated variable dictionary lives.

        Ships *with the package*, not with the data root. These files are source
        code — hand-written assertions under version control — while the root is
        a data directory that can be deleted and re-crawled. Putting curation in
        the root would mean losing every human judgement with the lake.

        That was the stated intent from the start and the path did not honour it:
        it resolved to the *repository* root, one level outside the package, so
        an installed wheel carried no curation at all and the manual-authority
        rung — the whole point of §4 — was empty for every user who had not
        cloned the source.
        """
        override = self.curation_root
        if override is not None:
            return Path(override)
        return Path(__file__).resolve().parent / "curation"

    @property
    def blobs_dir(self) -> Path:
        return self.root / "blobs"

    @property
    def lake_dir(self) -> Path:
        return self.root / "lake"

    @property
    def population_dir(self) -> Path:
        return self.lake_dir / "population"

    @property
    def demas_dir(self) -> Path:
        return self.lake_dir / "demas"

    @property
    def work_dir(self) -> Path:
        return self.root / "work"

    def ensure_dirs(self) -> None:
        for p in (
            self.root,
            self.root / "_catalog",
            self.blobs_dir,
            self.lake_dir,
            self.population_dir,
            self.demas_dir,
            self.work_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


def load_settings(**overrides: object) -> Settings:
    """Build settings from defaults, environment, then explicit overrides."""
    kwargs: dict[str, object] = {}
    if "PEGASUS_FTP_HOST" in os.environ:
        kwargs["host"] = os.environ["PEGASUS_FTP_HOST"]
    if "PEGASUS_BASE_PATH" in os.environ:
        kwargs["base_path"] = os.environ["PEGASUS_BASE_PATH"]
    if "PEGASUS_CONNECTIONS" in os.environ:
        kwargs["connections"] = int(os.environ["PEGASUS_CONNECTIONS"])
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return Settings(**kwargs)  # type: ignore[arg-type]
