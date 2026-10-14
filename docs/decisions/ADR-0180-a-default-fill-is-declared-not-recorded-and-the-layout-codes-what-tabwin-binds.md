## ADR-0180: A default fill is declared not recorded, and a field the layout confines to one procedure is coded by the layout

**Date:** 2026-10-14. **Status:** active. **Amends:** ADR-0108 (a TabWin binding is not a code's meaning: a second instance),
ADR-0154 (the missing codes of categories).

**Context.** An epidemiologist's Table 1 for Alagoas, SIH-RD admissions with I21-I22 as principal diagnosis, 2014-2023 (9,324
AIHs of type 1), read:
- `GESTRISCO` "Sim" on every AIH, 5,517 of them men. The raw values (`RDAL1607.dbc`, 15,734 AIHs, read with a header parse of
  the inflated DBF) are `1` on 15,733, men included, so the lake is the file. SISAIH01 field 88 codes it `0-Sim 1-Não` and asks
  it "Somente para Laqueadura"; TabNet's `RD2008.DEF` binds it to `SIMNAO` (`1` Sim). The records side with the layout: `1`
  is on all 969,672 AIHs of "parto normal em gestação de alto risco" as on 9.45 million of "parto normal", and `0` only on
  sterilisation AIHs (148,028 of 859,946 of three procedures; 4,747 of 118 million others), where it goes with an O-chapter
  indication 4 times as often.
- `INSTRU` 0 "Ignorado/não se aplica", `VINCPREV` 0 "Não classificado" (and `CONTRACEP`, `CNAER`) on 98.8-99.99% of AIHs, declared
  `missing: []` because a proposal from DATASUS's labels (ADR-0154) matches whole labels and these read as a pair.
- `RACA_COR` 99 "Sem informação" on 57% of the study's AIHs, with no `missing` at all: the completeness table said race was recorded on 100%.
  (The race labels were not unbound: `pg.levels` decodes 01-05 and 99; the study asked it for the codes `0`-`9`, PegaSUS's
  `gateway._value_labels`.)

**Decision.**
- A field the input layout restricts to one procedure is coded by that layout, written in the curation (`codes:`, ADR-0079), and
  the TabWin binding is not followed where the records contradict it. `GESTRISCO`: `0` Sim, `1` Não (valor padrão), and `1`
  declared not recorded: it is the fill of every AIH and cannot be told from the documented Não on a sterilisation AIH, so the
  column reads as unrecorded outside sterilisation, which is what it is.
- A code that stands for not recorded and for not applicable (`INSTRU` 0) is declared missing, and the column's `note` says it
  also means not applicable, so the share not recorded is read as including the AIHs the item does not concern. A code the
  table labels so through a catch-all range, in a column of one digit, is declared with it (`INSTRU` 5-9, `VINCPREV` 7-9, as
  `ESC` 6-8); in a longer code only the codes the records hold (`RACA_COR` 00 and 99, `CONTRACEP` 00 and 13).
- `RACA_COR` declares `00` and `99`; SIM-DO's `SEXO` declares `0`, `9` and `I` as the layout says.
- SIM-DO's `ESC2010` begins in 2012 (the 2011 files carry it empty), `ESCFALAGR1` and `ESCMAEAGR1` in 2014; the notes of `ESC` and
  `ESC2010` say which years each holds and that `ESC` 1 and `ESC2010` 0 are the same persons.

**Consequence.** PegaSUS's stored compositions of `INSTRU`, `VINCPREV`, `GESTRISCO`, `CONTRACEP1`, `CONTRACEP2` and the `RACA_COR` groups of
SIH-RD are re-keyed (the missing codes are in the key). Alagoas's infarction AIHs: race recorded on 43.0% (was 100%), schooling,
social-security link, contraceptive and `GESTRISCO` on 0.0% (were 100%).

**What would reverse it.** A SIH document that codes `GESTRISCO` for every AIH, or a `1` that the records tie to risk.
