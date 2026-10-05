# Label pack: the minority-kit rule destroyed 12,731 valid runs; it now drops only a recoded codebook's minority kit

**Script and artifact.** `pegasus-data labelpack` (`labelpack._recoded_kit_pairs`, the drop in `build_label_pack`) on the
local catalog (12.9 GB, 662,108 `dictionary_conflicts`), compared against the pack before the rule (`git show
2a3d192^:src/pegasus_data/resources/labels.parquet`) at run level and with every run expanded to its codes. Scratch outputs
only; the shipped pack is the artifact. Regime: branch `pegasus-core-fixes`, local data home, 2026-10-05, through
`heavy.py`.

**What went wrong.** 53ea78b/2a3d192 packed one kit per (system, codelist) whenever the codelist had any row in
`dictionary_conflicts`, whatever the conflict was and whatever the window. The rebuilt pack lost 12,733 runs and 2,920 distinct
(codelist, code) pairs lost every label. The conflicts are mostly wording, not meaning:

| What was removed | Runs | Codelists | Verdict |
|---|---|---|---|
| Undated claim beside dated windows (SIH `CIDX01`..`CIDX20F`): the open window, identical labels | 9,576 | 19 | wrong: a window is identity, the 2013+ vintage lost its labels |
| Entity registers and lists whose kits rename the same code (`UNISAU*`, `BR_REGMETR`, `NHE*`, `CBO_02`, `ANOMES`) | 3,100 | 78 | wrong: case, accents, abbreviation, `1 L;` order marks; a code only one kit lists is still that entity |
| Small codebooks whose kits differ in wording or a catch-all (`FXINFAN1/2` `< 7d` / `< 7 dias`, `APGAR` and `SEXO` `Ign` / `Ignorado`, `SINASC ANO` `Ign` over 23..93, `TP_ESTAB`, `NUMFILH`, `EVODENG` plural) | 55 | 9 | wrong |
| SINASC `RACACOR` 5 `Preta`, 6-8 `Ignorado` (1994-95 kit codes 1 Amarela, 2 Branca, 3 Indigena, 5 Preta; 1996 kit 1 Branca, 2 Preta, 3 Amarela) | 2 | 1 | right: one system, one (open) window, kits recode the same codes |

Also undone: the rule flipped `CBO_02` (146 runs) and `TP_FINAN` (2) from "every system agrees" to per-system rows, which the 2a3d192 note
counted as 149 new rows; they were not new content.

**The rule now.** `_recoded_kit_pairs` reads `dictionary_conflicts` and calls two kits a recoding of a codelist when, of the codes
they disagree on, more differ in meaning than in wording (`_same_meaning`: case, accents, punctuation, a prefix abbreviation, token
containment, a plural, a catch-all such as `Ign` / `Outros`; a different word or number is a difference). The drop then applies
only inside one (system, validity window) where both kits still hold rows, only to a codebook (at most 128 codes, codes of at most 3
characters), only to the kit with fewer specific (non-catch-all) rows; equal counts drop nothing. Other windows, other systems,
registers and unconflicted codes keep their labels.

**Result against the pack before the rule** (4,219,910 runs): 4,219,908 runs; the only difference is SINASC `RACACOR` 5 and 6-8; 3
codes without a label remain (`RACACOR` 6, 7, 8, which only the older kit defines). 12,731 of 12,733 runs restored. Manifest `rows`
for the pack was 3,654,320 against 4.2M actual runs; now correct.

**`translate`** (checked with the call, codes 1-5 and a polluted set 0, 6, 9, 01, 03, 04, `SIM` `RACACOR`, `SINASC`
`RACACOR` and `RACACORMAE`): in the local home all three give Branca, Preta, Amarela, Parda, Indigena in both sets, the extra codes
unlabelled (the curated `codes:` tables, rung 1). On a fresh root the shipped seed (not regenerated since 2026-10-04) lacks those
curated tables, so a fresh install still reads SIM `RACACOR` 1 `Bra`, 3 `Amar`, 5 `Indig` from the pack and nothing in the polluted
set; SINASC `RACACOR` 5 is now unlabelled instead of `Preta`. Regenerating the seed (`scripts/build_resources.py`) closes that; it
was not done here because it would export the catalog's other uncommitted curation along with it.
