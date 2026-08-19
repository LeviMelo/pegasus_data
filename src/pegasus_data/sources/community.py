"""Community transcriptions of DATASUS codings — the lowest rung that still counts.

Some of this tree is documented nowhere DATASUS publishes. CNES is the clearest
case: 163 of its columns are categorical, its record layout is thin, and its
value codings live mostly outside the FTP tree. Meanwhile people who work with
these files daily have written the codings down, and pretending otherwise leaves
columns unlabelled that everyone in the field can already read.

So this ingests them, at ``source='community'`` — below ``pdf``, above
``inferred``. Two properties make that safe:

* It can never override a first-party table. ``SOURCE_AUTHORITY`` puts
  ``community`` behind ``cnv``, ``def``, ``sigtap``, ``dbf_lookup``, ``demas_api``
  and ``pdf``, so where DATASUS says anything at all, DATASUS wins and the
  community reading is recorded as the losing side of a conflict.
* Every entry carries the repository, the **commit SHA** and the file it came
  from in ``source_ref``. A transcription without a version is a rumour; with one
  it is a citation someone can check and re-run.

The first supported source is ``rfsaldanha/microdatasus`` (MIT), an R package
that recodes DATASUS microdata and whose ``process_*.R`` files encode the value
labels as literal ``"code" ~ "label"`` pairs. Parsing R rather than executing it
is deliberate: this reads data out of source text and never runs it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog
from ..semantics.dictionary import DictionaryEntry, persist_entries

MICRODATASUS_REPO = "https://github.com/rfsaldanha/microdatasus"
_RAW = "https://raw.githubusercontent.com/rfsaldanha/microdatasus"
_API = "https://api.github.com/repos/rfsaldanha/microdatasus"

#: ``process_<name>.R`` → the system this project calls it. SINAN's per-disease
#: files all describe the same system; the disease is the series, not a system.
FILE_SYSTEMS: dict[str, str] = {
    "process_sia": "SIASUS",
    "process_sih": "SIHSUS",
    "process_sim": "SIM",
    "process_sinasc": "SINASC",
    "process_cnes": "CNES",
    "process_sinan_chagas": "SINAN",
    "process_sinan_chikungunya": "SINAN",
    "process_sinan_dengue": "SINAN",
    "process_sinan_leishmaniose_tegumentar": "SINAN",
    "process_sinan_leishmaniose_visceral": "SINAN",
    "process_sinan_malaria": "SINAN",
    "process_sinan_zika": "SINAN",
}

#: ``if ("PA_SEXO" %in% variables_names) {`` — opens the block that recodes one
#: column, and is what lets a pair be attributed to the right field.
_FIELD_BLOCK = re.compile(r'if\s*\(\s*"([A-Z0-9_]+)"\s*%in%\s*variables_names\s*\)\s*\{', re.I)

#: ``"0" ~ "Não exigido"`` (recode_values) and ``"0" = "Não exigido"`` (case_match),
#: the two forms the package has used across its versions.
_PAIR_TILDE = re.compile(r'"((?:[^"\\]|\\.)*)"\s*~\s*"((?:[^"\\]|\\.)*)"')
_PAIR_EQUALS = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"')

_UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")

#: R writes accented Portuguese as \uXXXX in these files, so a raw read gives
#: "RAÇA/COR" where the label is "RAÇA/COR".
def _unescape(text: str) -> str:
    text = _UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)
    return text.replace('\\"', '"').replace("\\\\", "\\")


@dataclass(slots=True)
class CommunitySource:
    repo: str
    commit: str
    files: dict[str, str] = field(default_factory=dict)  # filename -> text

    def reference(self, filename: str, field_name: str) -> str:
        return f"{self.repo}@{self.commit[:12]}!{filename}#{field_name}"


def parse_r_recodes(text: str) -> Iterator[tuple[str, str, str]]:
    """Yield ``(field, code, label)`` from one ``process_*.R``.

    Attribution is by position: a pair belongs to the field whose ``if`` block it
    sits inside. Scanning the file for pairs without that bracketing would smear
    every column's codes across every other column, which is worse than
    extracting nothing.
    """
    marks = [(m.start(), m.group(1).upper()) for m in _FIELD_BLOCK.finditer(text)]
    for index, (start, field_name) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        block = text[start:end]
        pairs = _PAIR_TILDE.findall(block) or _PAIR_EQUALS.findall(block)
        for raw_code, raw_label in pairs:
            code, label = _unescape(raw_code), _unescape(raw_label)
            # `.data$X` is the default arm, not a value; an empty side is noise.
            if not code or not label or code.startswith(".data") or label.startswith(".data"):
                continue
            yield field_name, code, label


def fetch_microdatasus(*, commit: str | None = None, timeout: int = 60) -> CommunitySource:
    """Download the ``process_*.R`` files at a pinned commit.

    Resolves ``master`` to a concrete SHA when no commit is given, so the result
    is reproducible even though the request was not pinned.
    """
    import httpx

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        sha = commit or client.get(f"{_API}/commits/master").json()["sha"]
        tree = client.get(f"{_API}/git/trees/{sha}?recursive=1").json()
        wanted = [
            entry["path"]
            for entry in tree.get("tree", [])
            if entry["path"].startswith("R/process_") and entry["path"].endswith(".R")
        ]
        files: dict[str, str] = {}
        for path in sorted(wanted):
            response = client.get(f"{_RAW}/{sha}/{path}")
            response.raise_for_status()
            files[path.rsplit("/", 1)[-1]] = response.text
    return CommunitySource(repo=MICRODATASUS_REPO, commit=sha, files=files)


def entries_from_source(
    source: CommunitySource, *, systems: Sequence[str] | None = None
) -> list[DictionaryEntry]:
    """Turn parsed recodes into dictionary entries with full provenance."""
    wanted = {s.upper() for s in systems} if systems else None
    entries: list[DictionaryEntry] = []
    for filename, text in source.files.items():
        stem = filename[:-2] if filename.endswith(".R") else filename
        system = FILE_SYSTEMS.get(stem)
        if system is None or (wanted and system not in wanted):
            continue
        for field_name, code, label in parse_r_recodes(text):
            entries.append(
                DictionaryEntry(
                    system=system,
                    value_raw=code,
                    value_label=label,
                    source="community",
                    source_ref=source.reference(filename, field_name),
                    confidence=0.4,
                    # Grouped under the field's own name: these codings are
                    # per-column, not a shared table, and binding them to
                    # anything else would imply a generality they do not have.
                    value_group=field_name,
                    field_name=field_name,
                )
            )
    return entries


def ingest(
    catalog: Catalog,
    *,
    systems: Sequence[str] | None = None,
    commit: str | None = None,
    source: CommunitySource | None = None,
) -> dict[str, object]:
    """Ingest community codings and bind them to the fields they describe."""
    resolved = source or fetch_microdatasus(commit=commit)
    entries = entries_from_source(resolved, systems=systems)
    written = persist_entries(catalog, entries)

    # Bind each field to its own group, at community confidence. A first-party
    # binding for the same field outranks this one wherever it exists.
    bindings = sorted({(e.system, e.value_group or "", e.source_ref) for e in entries})
    bound = catalog.executemany(
        """
        INSERT INTO field_codelists (system, family_id, field_name, codelist, source,
                                     source_ref, confidence)
        VALUES (?,?,?,?,'community',?,0.4)
        ON CONFLICT(system, family_id, field_name, codelist) DO UPDATE SET
            source_ref=excluded.source_ref
        """,
        [(system, "", group, group, ref) for system, group, ref in bindings if group],
    )
    by_system: dict[str, int] = {}
    for entry in entries:
        by_system[entry.system] = by_system.get(entry.system, 0) + 1
    catalog.log_event(
        "community",
        "ingested community codings",
        detail=f"{len(entries)} pairs from {resolved.repo}@{resolved.commit[:12]}",
    )
    return {
        "repo": resolved.repo,
        "commit": resolved.commit,
        "files": len(resolved.files),
        "pairs": len(entries),
        "merged": written,
        "fields_bound": bound,
        "by_system": dict(sorted(by_system.items(), key=lambda kv: -kv[1])),
    }
