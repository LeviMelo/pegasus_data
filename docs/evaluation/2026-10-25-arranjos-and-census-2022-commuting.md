# IBGE's population arrangements and the Census 2022 commuting tables (2026-10-25)

Regime: branch `mobility` from `a1b70be`, data home `C:\Users\Galaxy\pegasus_core_data`, 2026-10-25. ADR-0211.

**Arranjos Populacionais, 2nd edition.**
- **Source.** `sources/ibge_arranjos.py` reads `ComposicaoRecortes_01_PorMunicipio` from IBGE's geodatabase
  `ArranjosPopulacionais_mbd_2ed.zip`, cached in `registries/ibge_arranjos/`.
  - The download is an 88 MB zip holding a 240 MB Access `.mdb`. It is the only file with codes; `tab01.xlsx` names
    the arrangements without them.
  - The table has 5,567 municipality rows, the 2010 division.
- **Counted, per classification.** The `geography` pack gained these rows:

  | Classification | Municipalities | Members |
  |---|---|---|
  | `population_arrangement` | 953 | 294 |
  | `urban_concentration_medium` | 386 | 161 |
  | `urban_concentration_large` | 256 | 26 |

  - **Arrangements.** 23 arrangements have a single Brazilian member: their other members are foreign, as in
    "Internacional de Guajará-Mirim/Brasil - Guayaramerín/Bolívia".
  - **Blanks.** One municipality, 3145406, holds `<Null>` (IBGE's blank) and is left without a member.
  - **Codes.** A member's code is its core municipality's code: Campinas 3509502 is in arrangement 3509502,
    "Campinas/SP", and in the large concentration of the same code.
- **The rest of the pack is unchanged.** It went from 110,122 to 111,717 rows. The 1,595 added are exactly these;
  every other row is identical.

**Census 2022 commuting (SIDRA 10321, 10330-10333).**
- **Already served.** The SIDRA reader serves them per municipality with no new code:
  - 10330: v13376, `c469` place of work, fetched with `-c 469=all`;
  - 10321: v13631, `c468` place of school.
  - Each came back with 22,280 facts: 5,570 municipalities × 4 categories (Total, own municipality, other municipality,
    foreign country).
- **Declared as samples.** IBGE's notes, read in a browser on 2026-10-25 and dated 2026-06-26, call all five "Dados dos
  resultados preliminares da amostra, estimados a partir de áreas de ponderação preliminares". They are declared in
  `curation/sidra/notes.yml`, so `basis` reads `sample` where it read `unknown`.
- **The Total is not the sum of the categories.**
  - The notes say each Total includes the persons whose place was "ignorado".
  - 10331-10333 also leave out persons working in more than one municipality or country.
  - A share computed as other municipality ÷ Total therefore has the unknowns in its denominator.
