"""A municipality code must never come back named as something larger.

`CODMUNRES = 120040` is Rio Branco. For weeks it came back "Baixo Acre e Purus",
the health region Rio Branco sits in, and every layer behaved exactly as
designed while producing it:

  * `.DEF` binds 145 tables to CODMUNRES, all at confidence 0.9;
  * ranking breaks a confidence tie on name affinity, then ALPHABETICALLY;
  * `CIRAC` sorts 3rd and `BR_MUNICIPALFA` sorts 118th;
  * measurement weighs only the first `_MAX_CANDIDATES` (12) candidates.

So the correct table was bound, was never loaded, and was never measured, and
CIRAC — which decodes 100% of municipality codes, to 24 region names — won on
alphabetical order. The rollup guard NAMED it in a warning, which is not the
same as not doing it.

The fix is that the variable -> decoder link is stated in curation rather than
inferred at read time, so ranking never decides a municipality label. These
tests hold that statement in place; they are about the LINK, and they read the
shipped curation and label pack rather than fetching anything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
pq = pytest.importorskip("pyarrow.parquet")

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "src" / "pegasus_data" / "curation" / "variables"
LABELS = ROOT / "src" / "pegasus_data" / "resources" / "labels.parquet"

#: The national municipality table, and the gestor variant that adds the
#: "UF0000 - gestão estadual" sentinels the plain one has no row for.
MUNICIPALITY_TABLES = {"BR_MUNICIPALFA", "BR_MUNICGESTOR"}

#: A table that answers at a COARSER grain than a municipality. Binding one to a
#: municipality column decodes every value and answers a different question.
ROLLUP = re.compile(
    r"^(CIRA|RSAUD|CSAUD|REGSAUD|MACSAUD|REGMETR|CAPITA|BR_CAPITAL|MESO|MICRO"
    r"|REGIAO|BR_REGIAO|AGLB)",
    re.I,
)

#: `AC_MUNICIP` is Acre's 32 municipalities. On national data it is not a
#: rollup, it is simply the wrong 0.6% of the country.
PER_UF = re.compile(r"^([A-Z]{2}_MUNICIP|MUNIC(?!BR)[A-Z]{2})$")

#: Columns that mention a municipality and are not one, with the reason. A bare
#: exclusion list rots; a reason can be checked against the column.
NOT_A_MUNICIPALITY_CODE = {
    ("PCE", "ID_LOC"): (
        "a 12-character composite geocode - UF in 1-2, municipality in 1-7, and "
        "a SISLOC locality in 8-12 that curation itself records as having no "
        "counterpart in any IBGE table. No municipality table decodes it whole, "
        "and exact-width matching (6.2) means none can be applied to part of it."
    ),
}


def _curated() -> list[tuple[str, str, list[str], dict]]:
    out = []
    for path in sorted(CURATION.glob("*/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        system = str(doc.get("system") or path.parent.name).upper()
        for name, body in (doc.get("variables") or {}).items():
            if not isinstance(body, dict):
                continue
            named = ([body["codelist"]] if body.get("codelist") else [])
            named += list(body.get("codelists") or [])
            out.append((system, str(name).upper(), [str(c) for c in named], body))
    return out


CURATED = _curated()


def _shipped_codelists() -> set[str]:
    column = pq.read_table(LABELS, columns=["codelist"]).column("codelist")
    return {str(c).upper() for c in column.to_pylist()}


def test_every_curated_codelist_actually_exists() -> None:
    """A curated name that does not ship silently decodes NOTHING.

    A curated list bypasses measurement by design — it is a human decision and
    nothing may widen it — so a misspelled table is not caught by falling back
    to a bound one. It produces an empty label column and no error.

    56 references were in this state, `ibge_municipio` on 30 columns and a prose
    placeholder, `'..._MUNICIP (per-UF IBGE municipality lists)'`, on 6.
    """
    ships = _shipped_codelists()
    phantom = sorted(
        {
            f"{system}.{field} -> {codelist}"
            for system, field, named, _ in CURATED
            for codelist in named
            if codelist.upper() not in ships
        }
    )
    assert not phantom, (
        f"{len(phantom)} curated codelist references name a table that does not "
        f"ship, so those columns claim to be decoded and are not: {phantom[:10]}"
    )


def _municipality_columns() -> list[tuple[str, str, list[str]]]:
    """Columns curation itself says hold a municipality code."""
    return [
        (system, field, named)
        for system, field, named in (
            (s, f, n) for s, f, n, _ in CURATED
        )
        if named and named[0].upper() in MUNICIPALITY_TABLES
    ]


def test_municipality_columns_exist_and_are_numerous() -> None:
    """Guards the two tests below against silently matching nothing."""
    found = _municipality_columns()
    assert len(found) >= 100, (
        f"only {len(found)} columns are bound to a municipality table; the link "
        "fix covered 128, so something has undone it"
    )


@pytest.mark.parametrize("table", sorted(MUNICIPALITY_TABLES))
def test_the_municipality_table_ships_and_is_not_itself_a_rollup(table: str) -> None:
    """The table has to exist, and has to answer at municipality grain.

    Granularity is the property that matters and it is measurable: CIRAC maps
    24 codes to 4 labels (0.17) and is a rollup; a municipality table maps ~5,600
    codes to ~5,600 labels.
    """
    import pyarrow.compute as pc

    data = pq.read_table(LABELS)
    rows = data.filter(pc.equal(data.column("codelist"), table))
    assert rows.num_rows > 0, f"{table} does not ship in the label pack"
    exact = {
        str(lo): label
        for lo, hi, label in zip(
            rows.column("code_lo").to_pylist(),
            rows.column("code_hi").to_pylist(),
            rows.column("label").to_pylist(),
            strict=True,
        )
        if lo == hi
    }
    assert len(exact) > 5_000, f"{table} has only {len(exact)} municipalities"
    grain = len(set(exact.values())) / len(exact)
    assert grain > 0.9, (
        f"{table} maps {len(exact)} codes to {len(set(exact.values()))} labels "
        f"(granularity {grain:.2f}); at municipality grain this is ~1.0, so this "
        "table answers a coarser question than a municipality column asks"
    )


@pytest.mark.parametrize(
    "code,expected",
    [
        ("120040", "Rio Branco"),      # the code that reported "Baixo Acre e Purus"
        ("120001", "Acrelândia"),      # and the one that reported the same region
        ("355030", "São Paulo"),
        ("330455", "Rio de Janeiro"),
        ("230440", "Fortaleza"),
        ("530010", "Brasília"),        # reached through a RANGE row, 530000-539999
    ],
)
def test_known_municipality_codes_decode_to_their_city(code: str, expected: str) -> None:
    """The specific values from the defect, and one that needs range matching."""
    from pegasus_data.labelpack import read_packed

    packed = read_packed("BR_MUNICIPALFA", system="SINASC")
    assert packed is not None and packed.num_rows, (
        "BR_MUNICIPALFA did not load from the shipped pack"
    )
    lookup = dict(
        zip(packed.column("code").to_pylist(), packed.column("label").to_pylist(), strict=True)
    )
    got = lookup.get(code)
    assert got is not None, f"{code} is not decodable by BR_MUNICIPALFA"
    assert expected.lower() in got.lower(), (
        f"{code} decoded to {got!r}, which is not {expected!r}. A municipality "
        "code labelled with anything larger than its city is the defect this "
        "test exists for."
    )


def test_no_municipality_column_is_bound_to_a_rollup_or_one_states_list() -> None:
    """The two ways this went wrong, stated as one rule.

    `SINASC.CODMUNNASC` listed six tables and not one at municipality grain;
    `SINASC.MUNI_MAE` named BR_CAPITAL, a list of capitals; `SIM.MUNIRES` named
    `AC_MUNICIP`, Acre's 32 municipalities, on national data.
    """
    bad = []
    for system, field, named, body in CURATED:
        blurb = " ".join(
            str(body.get(k) or "") for k in ("official_name", "translated_name", "description")
        )
        # By MEANING: the name alone catches IMUNO* (immunology) and misses
        # MUNIRESAT, ATE_MUNICI and DS_TRANS1.
        if not re.search(r"munic[íi]pio|municipality", blurb, re.I):
            continue
        if re.match(r"^\w*IMUN", field):
            continue
        if not named or (system, field) in NOT_A_MUNICIPALITY_CODE:
            continue
        primary = named[0].upper()
        if primary in MUNICIPALITY_TABLES:
            continue
        if ROLLUP.match(primary) and re.search(r"IBGE|munic[íi]pio de|municipality of", blurb, re.I):
            bad.append(f"{system}.{field} -> {primary} (rollup)")
        elif PER_UF.match(primary):
            bad.append(f"{system}.{field} -> {primary} (one state's list, on national data)")
    assert not bad, (
        "these columns hold a municipality code and are bound to something that "
        f"is not a municipality table: {bad}"
    )


def test_every_municipality_column_is_declared_external() -> None:
    """The IBGE code is a join key, so it has to survive the labelling.

    §5 names "IBGE município" in its own definition of `external`: a canonical
    identifier in its own right, where the code AND the label are kept. Fourteen
    municipality columns disagreed, and the two ways of disagreeing failed
    differently:

      `internal` REPLACES the code with the label. `SIM.CODMUNRES` came back
      holding `'120001 Acrelândia, AC'` and nothing joinable — while SINASC's
      identically-meant column kept both, so the same fact had two shapes
      depending on which system you asked.

      `none` means "the value as typed" and skips labelling entirely, so ten
      columns had a municipality table bound and quietly never used it.
    """
    bad = [
        f"{system}.{field} (code_system={body.get('code_system')!r})"
        for system, field, named, body in CURATED
        if named
        and named[0].upper() in MUNICIPALITY_TABLES
        and body.get("code_system") != "external"
    ]
    assert not bad, (
        "a municipality code is an external identifier and must keep its code "
        f"beside the label: {bad}"
    )
