"""The data ontology: what the systems and datasets ARE, and how the crawl binds to them.

There are two separate things in this module and conflating them is the mistake
it exists to prevent.

**The declared ontology** is institutional fact. "SIH publishes a dataset called
AIH Reduzida, known as RD" is a statement about how the Ministry of Health
organises its information systems. It is authored in ``curation/ontology.yml``,
it is true whether or not the FTP server expresses it, and it survives DATASUS
reorganising the tree. A declared node with no files is not an error — it is a
dataset we know exists and have not found published.

**The binding** is evidence. It maps what the crawler actually saw — a
``(system, series)`` pair derived from a file path — onto a declared node. It is
derived, auditable, and disposable: change a binding rule and you change what the
crawler recognises, never what a dataset *is*.

The two demonstrably come apart, which is why the separation is not academic:

* One file, many datasets. ``SIASUS/APAC/2002/acac0201.exe`` carries seven
  distinct datasets as seven DBF members.
* One dataset, many locations. The SIA APAC datasets appear under ``SIASUS/`` and
  again under ``Dados_Abertos/`` as ``APAC_AB``, ``APAC_AD`` and so on.
* One dataset, many names. SINAN's agravos carry four-letter legacy codes in the
  old tree and Portuguese names in the open-data tree.

Binding also has to cope with a ``series`` column that is polluted, because it
was derived from filenames: of 1,505 observed ``(system, series)`` pairs only 181
are clean codes. The rest are archive members that leaked in (``RD:RDAC1701``),
whole filenames (``PASP2509A`` = PA + SP + 2509 + part A), placeholder filenames
DATASUS left in the tree (``EFUFAAMM``), and per-year dataset names
(``SISCAN_CITO_COLO_2013``). The rules below collapse those 1,505 onto ~199
canonical codes, and every rule records which one fired so the mapping can be
audited rather than trusted.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

CURATION = Path(__file__).parent / "curation"

#: Brazilian state codes plus BR, used to recognise a filename's UF segment.
UFS = frozenset(
    {
        "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
        "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
        "SP", "SE", "TO", "BR",
    }
)

#: ``<prefix><UF><date>[part]`` — the filename convention across the tree. The
#: part suffix is ``_1``/``_2`` or a bare letter: SIA splits one month's
#: production into ``PASP2509A``, ``PASP2509B``, ``PASP2509C`` when one file
#: would be too large.
_FILENAME = re.compile(
    r"^(?P<prefix>[A-Z]{2,6}?)(?P<uf>[A-Z]{2})(?P<date>\d{2,8})(?:_\d+|[A-Z])?$"
)
#: Placeholder filenames left in the tree: ``EFUFAAMM`` is EF + UF + AA + MM.
_TEMPLATE = re.compile(r"^(?P<prefix>[A-Z]{2,6})UFAAMM$")
#: Per-year dataset names: ``SISCAN_CITO_COLO_2013``.
_YEAR_TAIL = re.compile(r"^(?P<stem>[A-Z0-9_]+?)_(?:19|20)\d{2}$")


def canonical_series(series: str) -> tuple[str, str]:
    """Collapse an observed series string onto a canonical code.

    Returns ``(code, rule)``. ``rule`` names which pattern fired — ``declared``
    never appears here, because this function knows nothing about the ontology;
    it only cleans up an artefact of filename parsing. Keeping the rule in the
    return value is what makes the binding auditable instead of magic.
    """
    text = str(series or "").strip().upper()
    if not text:
        return "", "empty"

    if ":" in text:  # an archive member leaked in as "SERIES:MEMBER[:MEMBER]"
        return text.split(":", 1)[0], "colon-member"

    match = _TEMPLATE.match(text)
    if match:  # a placeholder filename, not a dataset
        return match.group("prefix"), "template"

    match = _YEAR_TAIL.match(text)
    if match:
        return match.group("stem"), "year-suffix"

    match = _FILENAME.match(text)
    if match and match.group("uf") in UFS:
        return match.group("prefix"), "filename"

    return text, "clean"


# --------------------------------------------------------------------- nodes


@dataclass(frozen=True)
class SystemNode:
    """An information system, as an institution declares it."""

    code: str
    official_name: str | None = None
    translated_name: str | None = None
    kind: str = "data"
    status: str = "active"
    what_it_is: str | None = None
    authority: str | None = None
    #: Names the crawler files this system under, when they differ from ``code``
    #: (the tree says SIHSUS; the institution says SIH).
    crawled_as: tuple[str, ...] = ()

    @property
    def is_data(self) -> bool:
        return self.kind == "data"


@dataclass(frozen=True)
class DatasetNode:
    """A dataset within a system — the subfamily level, e.g. ``SIH.RD``."""

    code: str
    system: str
    official_name: str | None = None
    translated_name: str | None = None
    what_it_is: str | None = None
    status: str = "active"
    confidence: str = "high"
    #: Declared evidence: series codes this dataset has been seen under. These
    #: are hints for the binder, NOT part of the dataset's identity.
    observed_as: tuple[str, ...] = ()

    @property
    def short_code(self) -> str:
        """``RD`` from ``SIH.RD``."""
        return self.code.split(".", 1)[-1]


@dataclass(frozen=True)
class Binding:
    """One observed ``(system, series)`` pair resolved onto a declared node."""

    observed_system: str
    observed_series: str
    dataset: str | None
    system: str | None
    rule: str
    canonical: str

    @property
    def bound(self) -> bool:
        return self.dataset is not None


@dataclass
class DatasetAxes:
    """Which axes a dataset's FILES are split on, measured rather than assumed.

    An axis is present when the files carry it. ``uf`` present means there is a
    file per state; ``uf`` absent means the data is national and the state, if
    it exists at all, is a column *inside* the file. Filtering on an absent axis
    matches nothing, which is why this is worth knowing before the filter runs
    rather than after it returns empty.

    The fractions are kept because reality is not binary: SIA.PA carries a state
    on 93% of files and the remainder are national consolidations, so a caller
    filtering by state silently drops 7%.
    """

    dataset: str
    files: int = 0
    date_formats: dict[str, int] = field(default_factory=dict)
    _uf: int = 0
    _year: int = 0
    _month: int = 0

    #: Below this share of files, an axis is treated as absent rather than
    #: partial. A handful of stray files carrying a state does not make a
    #: national series filterable by state.
    THRESHOLD = 0.5

    def _share(self, n: int) -> float:
        return (n / self.files) if self.files else 0.0

    @property
    def uf(self) -> float:
        return self._share(self._uf)

    @property
    def year(self) -> float:
        return self._share(self._year)

    @property
    def month(self) -> float:
        return self._share(self._month)

    @property
    def names(self) -> list[str]:
        """The axes a caller may filter on."""
        return [
            name
            for name, share in (("uf", self.uf), ("year", self.year), ("month", self.month))
            if share >= self.THRESHOLD
        ]

    def missing(self, *, uf: bool = False, year: bool = False, month: bool = False) -> list[str]:
        """Which of the requested filters this dataset has no axis for."""
        asked = {"uf": uf, "year": year, "month": month}
        return [name for name, wanted in asked.items() if wanted and name not in self.names]

    #: An axis this close to complete is complete. Without it, a dataset whose
    #: share rounds to 100% still trips the partial-axis warning and the caller
    #: is told "only 100% of files carry a year", which is nonsense and teaches
    #: them to ignore the warnings that matter.
    COMPLETE = 0.999

    def partial(self) -> list[tuple[str, float]]:
        """Axes present on most files but not all — a silent-drop risk."""
        return [
            (name, share)
            for name, share in (("uf", self.uf), ("year", self.year), ("month", self.month))
            if self.THRESHOLD <= share < self.COMPLETE
        ]

    def observe(self, *, uf: object = None, year: object = None,
                month: object = None, n: int = 1) -> None:
        """Fold ``n`` files into the tally.

        Shared by the catalog path (a SQL aggregate over ``file_facts``) and the
        snapshot path (plain row dicts), so the two cannot drift into disagreeing
        about whether a dataset is filterable.
        """
        self.files += n
        if uf:
            self._uf += n
        if year:
            self._year += n
        if month:
            self._month += n

    @classmethod
    def measure(cls, dataset: str, rows: "Iterable[Mapping[str, Any]]") -> "DatasetAxes":
        """Tally axes from explore-shaped rows (``uf``, ``year``, ``yyyymm``)."""
        axes = cls(dataset=dataset)
        for row in rows:
            axes.observe(
                uf=row.get("uf"),
                year=row.get("year"),
                month=len(str(row.get("yyyymm") or "")) >= 6,
            )
        return axes

    def explain(self, name: str) -> str:
        """Why filtering on ``name`` cannot work here, in one sentence."""
        present = ", ".join(self.names) or "nothing"
        return (
            f"{self.dataset} is not split by {name}. Its {self.files:,} files are "
            f"split by: {present}."
        )

    def fractions(self) -> dict[str, float]:
        """Share of files carrying each axis, whether or not it counts as present."""
        return {"uf": self.uf, "year": self.year, "month": self.month}

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "files": self.files,
            "axes": self.names,
            "uf": round(self.uf, 4),
            "year": round(self.year, 4),
            "month": round(self.month, 4),
            "date_formats": self.date_formats,
        }


@dataclass
class Reconciliation:
    """What the declaration and the crawl each know that the other does not.

    Both directions matter and they mean different things. A declared node with
    no files is a dataset we believe exists and have not located — a research
    lead. An observed series that binds to nothing is data we hold and cannot
    name — a gap in the declaration, and the more urgent of the two, because the
    API cannot describe it.
    """

    bound: list[Binding] = field(default_factory=list)
    unbound: list[Binding] = field(default_factory=list)
    unobserved: list[str] = field(default_factory=list)
    files_by_dataset: dict[str, int] = field(default_factory=dict)
    #: Files whose role is not ``data`` — the ``.CNV`` and ``.DEF`` codelists,
    #: the record layouts, the legislation PDFs. These are NOT datasets and are
    #: not expected to bind; they are where the *meaning* of the datasets comes
    #: from. Counted separately so that "unbound" keeps its one alarming
    #: meaning: microdata the API cannot name.
    support_files: dict[str, int] = field(default_factory=dict)
    #: Data files that bound, and data files that did not. The second number is
    #: the exhaustiveness measure the project is judged on.
    data_files_bound: int = 0
    data_files_unbound: int = 0

    @property
    def is_exhaustive(self) -> bool:
        """True when every data file on the tree reaches a declared dataset."""
        return self.data_files_unbound == 0

    def summary(self) -> dict[str, Any]:
        total = self.data_files_bound + self.data_files_unbound
        return {
            "observed_pairs": len(self.bound) + len(self.unbound),
            "bound_pairs": len(self.bound),
            "unbound_pairs": len(self.unbound),
            "datasets_declared": len(self.files_by_dataset) + len(self.unobserved),
            "datasets_observed": len([k for k, v in self.files_by_dataset.items() if v]),
            "datasets_unobserved": len(self.unobserved),
            "data_files": total,
            "data_files_bound": self.data_files_bound,
            "data_files_unbound": self.data_files_unbound,
            "data_coverage": (self.data_files_bound / total) if total else 0.0,
            "support_files": sum(self.support_files.values()),
            "exhaustive": self.is_exhaustive,
        }


# ------------------------------------------------------------------ ontology


class Ontology:
    """The declared ontology, plus the machinery that binds observations to it."""

    def __init__(
        self,
        systems: Mapping[str, SystemNode],
        datasets: Mapping[str, DatasetNode],
    ) -> None:
        self.systems = dict(systems)
        self.datasets = dict(datasets)
        self._build_indexes()

    # ------------------------------------------------------------- loading

    @classmethod
    def load(cls, curation_dir: Path | None = None) -> Ontology:
        """Read the declaration from ``curation/``.

        SINAN's per-agravo datasets live in ``datasets/sinan_agravos.yml`` rather than
        being restated here — one agravo per dataset, 58 of them, and they were
        already curated. They are folded in as dataset nodes so that
        ``info("SINAN.DENG")`` resolves like any other.
        """
        root = curation_dir or CURATION
        data = _read_yaml(root / "ontology.yml")

        systems: dict[str, SystemNode] = {}
        for code, body in (data.get("systems") or {}).items():
            body = body or {}
            systems[str(code).upper()] = SystemNode(
                code=str(code).upper(),
                official_name=body.get("official_name"),
                translated_name=body.get("translated_name"),
                kind=str(body.get("kind", "data")),
                status=str(body.get("status", "active")),
                what_it_is=_clean(body.get("what_it_is")),
                authority=body.get("authority"),
                crawled_as=tuple(str(x).upper() for x in (body.get("crawled_as") or ())),
            )

        datasets: dict[str, DatasetNode] = {}
        for code, body in (data.get("datasets") or {}).items():
            body = body or {}
            datasets[str(code).upper()] = DatasetNode(
                code=str(code).upper(),
                system=str(body.get("system", "")).upper(),
                official_name=body.get("official_name"),
                translated_name=body.get("translated_name"),
                what_it_is=_clean(body.get("what_it_is")),
                status=str(body.get("status", "active")),
                confidence=str(body.get("confidence", "high")),
                observed_as=tuple(str(x).upper() for x in (body.get("observed_as") or ())),
            )

        # SINAN agravos, declared in their own file.
        sinan_path = root / "datasets" / "sinan_agravos.yml"
        if sinan_path.exists():
            for code, body in (_read_yaml(sinan_path).get("datasets") or {}).items():
                body = body or {}
                series = str(body.get("series") or "").upper()
                if not series:
                    continue
                node_code = f"SINAN.{series}"
                if node_code in datasets:
                    continue
                datasets[node_code] = DatasetNode(
                    code=node_code,
                    system="SINAN",
                    official_name=body.get("official_name"),
                    translated_name=body.get("translated_name"),
                    what_it_is=_clean(body.get("what_one_row_is")),
                    observed_as=(series,),
                )

        return cls(systems, datasets)

    def _build_indexes(self) -> None:
        # Crawled system name -> declared system code. The tree says SIASUS; the
        # institution says SIA.
        self._system_alias: dict[str, str] = {}
        for node in self.systems.values():
            self._system_alias[node.code] = node.code
            for alias in node.crawled_as:
                self._system_alias[alias] = node.code

        # (declared system, series) -> dataset, and a series-only fallback for
        # republication trees, where the crawled system is Dados_Abertos but the
        # dataset belongs to SIA.
        self._by_system_series: dict[tuple[str, str], str] = {}
        self._by_series: dict[str, str] = {}
        self._series_collisions: set[str] = set()
        for node in self.datasets.values():
            keys = set(node.observed_as) | {node.short_code}
            for key in keys:
                self._by_system_series[(node.system, key)] = node.code
                if key in self._by_series and self._by_series[key] != node.code:
                    self._series_collisions.add(key)
                else:
                    self._by_series[key] = node.code

    # ------------------------------------------------------------- binding

    def system_of(self, name: str) -> SystemNode | None:
        """The declared system behind a crawled directory name.

        The tree says ``SIASUS``; the institution says ``SIA``. Callers that
        report what exists should say the second, because the first is a folder
        name that has changed before and will change again.
        """
        code = self._system_alias.get(str(name or "").upper())
        return self.systems.get(code) if code else None

    def bind(self, system: str, series: str) -> Binding:
        """Resolve one observed pair onto a declared dataset.

        Declaration is consulted before pattern rules: if a dataset says it has
        been seen as ``APAC_AB``, that wins over anything the filename regex
        would infer. The rules are a fallback for what nobody has declared yet.
        """
        observed_system = str(system or "").upper()
        observed_series = str(series or "").upper()
        declared_system = self._system_alias.get(observed_system)

        # 1. The raw series, exactly as declared.
        raw_hit = self._lookup(declared_system, observed_series)
        if raw_hit:
            return Binding(
                observed_system, observed_series, raw_hit,
                self.datasets[raw_hit].system, "declared", observed_series,
            )

        # 2. Clean the filename artefacts off, then try again.
        canonical, rule = canonical_series(observed_series)
        hit = self._lookup(declared_system, canonical)
        if hit:
            return Binding(
                observed_system, observed_series, hit,
                self.datasets[hit].system, rule, canonical,
            )

        return Binding(
            observed_system, observed_series, None, declared_system, rule, canonical
        )

    def _lookup(self, declared_system: str | None, key: str) -> str | None:
        if not key:
            return None
        if declared_system:
            hit = self._by_system_series.get((declared_system, key))
            if hit:
                return hit
        # Series-only fallback, but never when the code is ambiguous across
        # systems — a wrong bind is worse than an unbound one.
        if key not in self._series_collisions:
            return self._by_series.get(key)
        return None

    def reconcile(self, conn: sqlite3.Connection) -> Reconciliation:
        """Compare the declaration against what the crawl actually holds.

        Counts files by ``role``, because the tree is not all microdata. Of
        207,251 files, 219 are ``.CNV`` and ``.DEF`` codelists, record layouts
        and legislation PDFs — the support layer the dictionary is built from.
        Those are not datasets and must not be counted as gaps, or the one
        number that matters (data the API cannot name) gets buried in noise
        that is working exactly as intended.
        """
        report = Reconciliation()
        seen: set[str] = set()
        for system, series, files in conn.execute(
            "SELECT system, series, SUM(file_count) FROM strata "
            "WHERE system IS NOT NULL AND series IS NOT NULL GROUP BY 1, 2"
        ):
            binding = self.bind(str(system), str(series))
            if binding.bound and binding.dataset:
                report.bound.append(binding)
                seen.add(binding.dataset)
                report.files_by_dataset[binding.dataset] = (
                    report.files_by_dataset.get(binding.dataset, 0) + int(files or 0)
                )
            else:
                report.unbound.append(binding)
        report.unobserved = sorted(set(self.datasets) - seen)

        # Now the file-level truth, which is what exhaustiveness actually means.
        try:
            rows = conn.execute(
                "SELECT system, series_prefix, role, COUNT(*) FROM file_facts GROUP BY 1, 2, 3"
            ).fetchall()
        except sqlite3.OperationalError:  # pragma: no cover - older catalogs
            return report
        for system, series, role, count in rows:
            n = int(count or 0)
            if str(role or "data") != "data":
                report.support_files[str(role)] = report.support_files.get(str(role), 0) + n
                continue
            if self.bind(str(system), str(series or "")).dataset:
                report.data_files_bound += n
            else:
                report.data_files_unbound += n
        return report

    # ----------------------------------------------------------- resolution

    def resolve(self, target: str) -> tuple[str, Any] | None:
        """Resolve a user-supplied string onto a node.

        Accepts ``"SIH"``, ``"SIHSUS"``, ``"SIH.RD"``, ``"SIHSUS.RD"`` or a bare
        ``"RD"``. Returns ``(kind, node)`` where kind is ``"system"`` or
        ``"dataset"``, or ``None``.
        """
        text = str(target or "").strip().upper().replace("/", ".")
        if not text:
            return None

        if text in self.datasets:
            return ("dataset", self.datasets[text])

        declared = self._system_alias.get(text)
        if declared:
            return ("system", self.systems[declared])

        if "." in text:
            head, tail = text.split(".", 1)
            system = self._system_alias.get(head, head)
            hit = self._lookup(system, tail)
            if hit:
                return ("dataset", self.datasets[hit])
            return None

        hit = self._lookup(None, text)
        if hit:
            return ("dataset", self.datasets[hit])
        return None

    def axes(self, conn: sqlite3.Connection) -> dict[str, "DatasetAxes"]:
        """How each dataset is actually PARTITIONED on the server.

        The API had been assuming every dataset is split by state, year and
        month, and that assumption is false in a way that produces wrong
        answers rather than errors. ``SIM.DOFET`` — fetal deaths — is published
        as 48 NATIONAL files, ``DOFET79.DBC`` and so on. Ask for
        ``uf="AC"`` and the filter matches nothing, so the caller is handed an
        empty result and concludes that Acre records no fetal deaths.

        The state is not missing from that data. It is a COLUMN inside the
        national file rather than an axis the files are split on, and those are
        completely different things. This measures which is which, so callers
        can be told rather than left to infer it from an empty table.

        Four date formats exist on the tree — ``YYMM`` for 196,939 files,
        ``YY``, ``YYYY``, and none at all — so month is not universally
        available either.
        """
        out: dict[str, DatasetAxes] = {}
        for system, series, geo, year, normalized, fmt, count in conn.execute(
            "SELECT system, series_prefix, geo_code, year, normalized_date,"
            " date_format, COUNT(*) FROM file_facts"
            " WHERE role = 'data' AND system IS NOT NULL"
            " GROUP BY 1, 2, 3, 4, 5, 6"
        ):
            code = self.bind(str(system), str(series or "")).dataset
            if not code:
                continue
            axes = out.setdefault(code, DatasetAxes(dataset=code))
            n = int(count or 0)
            axes.observe(
                uf=geo, year=year, month=len(str(normalized or "")) >= 6, n=n
            )
            if fmt:
                axes.date_formats[str(fmt)] = axes.date_formats.get(str(fmt), 0) + n
        return out

    def suggest(self, target: str, *, limit: int = 5) -> list[str]:
        """Near matches for something that did not resolve.

        A name the API cannot resolve is almost always a typo or a
        half-remembered code, not a request for the full list of 131 datasets.
        ``SIH-RDD`` should produce ``SIH.RD``, and it is cheap to say so.

        Ranked by: an exact system match first (the user got the system right
        and the dataset wrong, which is the commonest case), then shared prefix,
        then edit distance. Substring matches are included because people search
        for ``QUIMIO`` expecting the chemotherapy dataset.
        """
        text = str(target or "").strip().upper().replace("/", ".").replace("-", ".")
        if not text:
            return []
        head = text.split(".", 1)[0]
        declared_head = self._system_alias.get(head)

        scored: list[tuple[tuple[int, int, str], str]] = []
        for code, node in self.datasets.items():
            names = " ".join(
                filter(None, [node.official_name, node.translated_name])
            ).upper()
            same_system = 0 if (declared_head and node.system == declared_head) else 1
            distance = _edit_distance(text, code)
            # Also try the SHORT code. "DENGUE" does not contain "SINAN.DENG"
            # and vice versa, but it does contain "DENG", which is how a person
            # actually searches for the dengue dataset.
            short = node.short_code
            if (
                text in code
                or code in text
                or (len(short) >= 3 and (short in text or text in short))
                or any(part and len(part) >= 3 and part in names for part in text.split("."))
            ):
                distance = min(distance, 1)
            scored.append(((same_system, distance, code), code))

        for code in self.systems:
            scored.append(((0 if code == declared_head else 1, _edit_distance(text, code), code), code))

        scored.sort(key=lambda item: item[0])
        out: list[str] = []
        for (_, distance, _), code in scored:
            if distance > max(4, len(text) // 2):
                continue
            if code not in out:
                out.append(code)
            if len(out) >= limit:
                break
        return out

    def datasets_of(self, system: str) -> list[DatasetNode]:
        declared = self._system_alias.get(str(system).upper(), str(system).upper())
        return sorted(
            (d for d in self.datasets.values() if d.system == declared),
            key=lambda d: d.code,
        )


# ----------------------------------------------------------------- helpers


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, iterative and small — these strings are short codes."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise RuntimeError("PyYAML is required to read the ontology") from exc
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}
