"""Give the 36 SINAN agravos an identity, not just a row definition.

``sinan_agravos.yml`` already said what one row of each agravo IS, sourced from
the folder DATASUS itself files the same data under in its open-data tree. What
it never carried was a NAME, so ``explore("SINAN")`` listed 36 four-letter codes
with an empty name column and the caller had to already know that ``LTAN`` is
cutaneous leishmaniasis.

The Portuguese name is DATASUS's own folder name, normalised to real orthography
(``Leishmaniose_tegumentar`` -> ``Leishmaniose tegumentar americana``); the
English name is the standard epidemiological term for the same notifiable
disease. ``source_ref`` on each entry already records the folder it came from, so
the provenance travels with the name.

Ten entries also had an untranslated ``what_one_row_is`` left over from the first
wave — "one notification of tuberculose" — which this corrects.

Idempotent: run it twice and the second run reports nothing to do.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "pegasus_data" / "curation" / "datasets" / "sinan_agravos.yml"

#: series -> (official_name, translated_name, corrected what_one_row_is or None)
NAMES: dict[str, tuple[str, str, str | None]] = {
    "ACBI": ("Acidente de trabalho com exposição a material biológico",
             "Occupational exposure to biological material", None),
    "ACGR": ("Acidente de trabalho grave", "Serious occupational accident", None),
    "ANIM": ("Acidente por animais peçonhentos", "Venomous animal accident", None),
    "ANTR": ("Atendimento antirrábico humano", "Human anti-rabies care", None),
    "CANC": ("Câncer relacionado ao trabalho", "Work-related cancer", None),
    "CHAG": ("Doença de Chagas aguda", "Acute Chagas disease", None),
    "CHIK": ("Febre de chikungunya", "Chikungunya", None),
    "COQU": ("Coqueluche", "Whooping cough", None),
    "DENG": ("Dengue", "Dengue", None),
    "DERM": ("Dermatoses relacionadas ao trabalho", "Work-related dermatoses", None),
    "DIFT": ("Difteria", "Diphtheria", None),
    "ESQU": ("Esquistossomose", "Schistosomiasis", None),
    "FMAC": ("Febre maculosa", "Spotted fever", None),
    "FTIF": ("Febre tifoide", "Typhoid fever", None),
    "HANT": ("Hantavirose", "Hantavirus infection", None),
    "HEPA": ("Hepatites virais", "Viral hepatitis", None),
    "IEXO": ("Intoxicação exógena", "Exogenous intoxication (poisoning)", None),
    "LEIV": ("Leishmaniose visceral", "Visceral leishmaniasis", None),
    "LEPT": ("Leptospirose", "Leptospirosis", None),
    "LERD": ("LER/DORT", "Repetitive strain and work-related musculoskeletal disorders",
             None),
    "LTAN": ("Leishmaniose tegumentar americana", "Cutaneous leishmaniasis", None),
    "MALA": ("Malária", "Malaria", None),
    "MENI": ("Meningite", "Meningitis", None),
    "PAIR": ("Perda auditiva induzida por ruído relacionada ao trabalho",
             "Noise-induced hearing loss, work-related", None),
    "PEST": ("Peste", "Plague", None),
    "PFAN": ("Paralisia flácida aguda", "Acute flaccid paralysis",
             "one notification of acute flaccid paralysis"),
    "PNEU": ("Pneumoconioses relacionadas ao trabalho", "Work-related pneumoconioses",
             "one notification of work-related pneumoconiosis"),
    "RAIV": ("Raiva humana", "Human rabies", "one notification of human rabies"),
    "ROTA": ("Rotavírus", "Rotavirus", None),
    "SIFA": ("Sífilis adquirida", "Acquired syphilis",
             "one notification of acquired syphilis"),
    "TETA": ("Tétano acidental", "Accidental tetanus",
             "one notification of accidental tetanus"),
    "TETN": ("Tétano neonatal", "Neonatal tetanus",
             "one notification of neonatal tetanus"),
    "TOXC": ("Toxoplasmose congênita", "Congenital toxoplasmosis",
             "one notification of congenital toxoplasmosis"),
    "TOXG": ("Toxoplasmose gestacional", "Gestational toxoplasmosis",
             "one notification of gestational toxoplasmosis"),
    "TUBE": ("Tuberculose", "Tuberculosis", "one notification of tuberculosis"),
    "ZIKA": ("Zika vírus", "Zika virus", "one notification of Zika virus infection"),
}

_SERIES = re.compile(r"^    series:\s*(\w+)\s*$")
_ROW = re.compile(r"^    what_one_row_is:\s*(.+?)\s*$")


def main() -> int:
    text = open(TARGET, encoding="utf-8").read()
    lines = text.splitlines()
    out: list[str] = []
    current: str | None = None
    added = renamed = 0

    for line in lines:
        match = _SERIES.match(line)
        if match:
            current = match.group(1).upper()
            out.append(line)
            entry = NAMES.get(current)
            if entry and "    official_name:" not in text.split(f"series: {current}")[-1][:200]:
                official, translated, _ = entry
                out.append(f"    official_name: {official}")
                out.append(f"    translated_name: {translated}")
                added += 1
            continue

        row = _ROW.match(line)
        if row and current and NAMES.get(current) and NAMES[current][2]:
            fixed = NAMES[current][2]
            if row.group(1) != fixed:
                out.append(f"    what_one_row_is: {fixed}")
                renamed += 1
                continue
        out.append(line)

    if not added and not renamed:
        print("nothing to do")
        return 0

    open(TARGET, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
    print(f"named {added} agravos; corrected {renamed} untranslated row definitions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
