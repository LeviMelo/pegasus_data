"""Name SINAN's agravos, from DATASUS's own open-data tree.

SINAN publishes one dataset per *agravo de notificação compulsória* — 69 of
them — and the legacy tree names each with a four-letter code: ACBI, ACGR,
ANIM, LERD. Nothing on that side of the server says what they stand for, so
`describe("SINAN-ACBI")` could say only that it is a SINAN series.

`Dados_Abertos/SINAN/` files the same data under Portuguese names —
`Acidente_tbr_mat_biologico`, `Acidente_trabalho`, `Acidente_anim_peconhentos`,
`LER_DORT` — which makes the open-data tree a *crosswalk DATASUS itself
published*. Joining the two by series prefix names 37 of the agravos from
observed evidence rather than from anyone's memory.

The generated file is a starting point, not the finished article: it carries the
name and what one row is, which is exactly what the four-letter code fails to
convey, and leaves the biases and gotchas for someone who knows the disease.

Usage::

    python scripts/sinan_agravos.py CATALOG > src/pegasus_data/curation/datasets_sinan.yml
"""

from __future__ import annotations

import io
import sqlite3
import sys

#: Portuguese folder name -> how it reads in English, for `translated` prose.
#: Only where the folder name is not already plain; the rest are passed through.
_READS_AS = {
    "Acidente_tbr_mat_biologico": "occupational exposure to biological material",
    "Acidente_trabalho": "serious work-related accident",
    "Acidente_anim_peconhentos": "venomous animal accident",
    "Atendim_antirrabico_humano": "human anti-rabies care",
    "Cancer_Trabalho": "work-related cancer",
    "Chagas_aguda": "acute Chagas disease",
    "Dermatose_trabalho": "work-related dermatosis",
    "Intoxicacao_exogena": "exogenous intoxication (poisoning)",
    "LER_DORT": "repetitive strain / work-related musculoskeletal disorder",
    "Leishmaniose_viceral": "visceral leishmaniasis",
    "Leishmaniose_tegumentar": "cutaneous leishmaniasis",
    "PAIR_relacionado_trabalho": "noise-induced hearing loss, work-related",
    "Febre_maculosa": "spotted fever",
    "Febre_tifoide": "typhoid fever",
    "Violencia_domestica": "interpersonal and self-inflicted violence",
    "Esquistossomose": "schistosomiasis",
    "Hantavirose": "hantavirus infection",
    "Leptospirose": "leptospirosis",
    "Coqueluche": "whooping cough",
    "Difteria": "diphtheria",
    "Meningite": "meningitis",
    "Colera": "cholera",
    "Peste": "plague",
    "Malaria": "malaria",
    "Hepatite": "viral hepatitis",
}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    conn = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    rows = conn.execute(
        """
        SELECT f.directory AS directory, fa.series_prefix AS series
          FROM files f JOIN file_facts fa ON fa.path = f.path
         WHERE f.path LIKE '%Dados_Abertos/SINAN/%'
           AND f.gone_at IS NULL
           AND fa.series_prefix IS NOT NULL
         GROUP BY f.directory, fa.series_prefix
        """
    ).fetchall()
    conn.close()

    mapping: dict[str, str] = {}
    for directory, series in rows:
        folder = str(directory).split("/SINAN/", 1)[1].split("/")[0]
        # A prefix seen under two folders is ambiguous and is left out rather
        # than resolved by whichever sorted first.
        if series in mapping and mapping[series] != folder:
            mapping[series] = ""
        else:
            mapping[series] = folder
    mapping = {k: v for k, v in mapping.items() if v}

    print("# SINAN's agravos, named from DATASUS's own open-data tree.")
    print("#")
    print("# The legacy tree names each notifiable disease with a four-letter code and")
    print("# says nowhere what it stands for. Dados_Abertos/SINAN/ files the same data")
    print("# under Portuguese disease names, which makes the open-data tree a crosswalk")
    print("# DATASUS itself published. This file is that join.")
    print("#")
    print("# What one row is comes from what SINAN is: a compulsory-notification system,")
    print("# so a row is a NOTIFICATION, not a case and not a person. Someone notified")
    print("# twice is two rows, and a notification later discarded on investigation stays")
    print("# in the file with its classification changed.")
    print("datasets:")
    for series, folder in sorted(mapping.items()):
        pretty = folder.replace("_", " ")
        reads = _READS_AS.get(folder)
        name = reads or pretty.lower()
        print(f"  SINAN_{series}:")
        print("    system: SINAN")
        print(f"    series: {series}")
        print("    asserted_by: pegasus_data")
        print("    source: manual")
        print(
            f"    source_ref: /dissemin/publicos/Dados_Abertos/SINAN/{folder}/ "
            "(DATASUS files this series under that name in its open-data tree)"
        )
        print(f"    what_one_row_is: one notification of {name}")
        print("    unit_of_analysis: notification")
        print("    gotchas:")
        print(
            "      - A row is a notification, not a confirmed case. CLASSI_FIN carries "
            "the outcome of investigation, including discarded."
        )
        print(
            "      - Counting by DT_NOTIFIC measures reporting; counting by DT_SIN_PRI "
            "measures onset. They differ by weeks."
        )
    print()
    print(f"# {len(mapping)} agravos named from the open-data tree.")


if __name__ == "__main__":
    main()
