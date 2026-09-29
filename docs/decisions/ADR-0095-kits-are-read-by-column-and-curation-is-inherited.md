## ADR-0095: A `.CNV` is read by its columns; a republishing system inherits curation; the age unit is keyed with the age

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0088.

**Context.** A live query of the open-data APAC for fistula creation
(`DADOS_ABERTOS-APAC_ACF`, 2023, 36,817 rows) found four defects.
- **Codes glued to their labels.**
  - A `.CNV` is fixed-width. When a label fills its field, the code starts at
    the expression column with no space before it: `MOTSAIPE.CNV` line 6 reads
    `… ACOMPAN. DO PACIENT15`.
  - The parser required a space before the column and otherwise split on
    whitespace, so the dictionary held `PACIENT15`, `ASSIST41` and, in
    `CARAT_AT`, `…(AGENT.FIS./QUIM.06`. Discharge reasons 15 and 41 and
    attendance character 06 never decoded.
  - Re-parsing every `.CNV` of the 36 ingested kits (7,952 files) changes
    **43,916 category lines**. SIASUS has 40,420 of them, including 3,237
    establishment names in `CNESNSP1.CNV`, 2,070 procedures in `PROC1199.CNV`
    and 1,230 occupations in `CBO2002.CNV`. SINASC has 2,138, SIM 1,181 and
    SINAN 131. Artifact: `data/probes/cnv_abutting_codes.json`.
- **A re-read `.CNV` did not replace its old reading.** On re-ingestion only a
  kit's DBF code tables were superseded. `.CNV` rows cite `kit!CNV/X.CNV:<line>`,
  which matched neither pattern, so a parser fix would have left `PACIENT15`
  beside `15`.
- **The open-data exports were undescribed.** `Dados_Abertos/APAC_SIA/*.duck.zip`
  carry SIA's own `AB_*`, `AP_*` and `ACF_*` columns. They are curated under
  SIASUS, so 218 DADOS_ABERTOS family-fields measured as undescribed.
- **Units without their values.**
  - `AP_COIDADE`, SIH/CIH/CIHA `COD_IDADE` and SIA `TPIDADEPAC` hold only the
    age *unit* (2 days, 3 months, 4 years, 5 years past 100).
  - The kits' `.DEF` reads the unit together with the 2-digit age that follows
    it, and `IDADEDET.CNV` names the 3-character pair: `463` = 63 anos,
    `205` = 5 dias. SIH's curation had recorded that "no DATASUS codelist of
    time units" exists, but this is that codelist.
- **The ACF flags.** The kit tabulates `ACF_DUPLEX` and the other flags with
  `SIMNAO2.CNV` (1/0), but the data hold S/N, as the APAC layout defines them
  (`APA_DUPLEX … (S-Sim, N-Não)`). Nothing decoded.

**Decision.**
- **Trust the column when a label abuts it** (`cnv_parser._code_abuts_label`).
  The column wins only if the text starting there is a match expression whose
  first code has the header's declared width. An overflowing label that
  pushes prose past the column (`medico02.CNV`) still takes the existing
  fallbacks.
- **A glued last token is split when the label also overran the column.**
  `FORMORGS.CNV` reads `… punção/biópsi020101`: the label ran past the
  column and abutted the code, so the column rule rightly declines. When the
  last token is prose (lower case or punctuation) ending in a code or range
  whose every end has the declared width, those digits are the code:
  `020101`, and `9906400000010-9906400051239` kept whole. This recovers
  129 more lines (SIASUS 124, SIHSUS 4, RESP 1;
  `data/probes/cnv_glued_tail.txt`).
- **Re-ingestion supersedes `.CNV` readings.** Kit members and loose `.CNV`
  files are superseded like DBF tables, matching `…:<line>` as well
  (`dictionary.supersede_source`). It reads the kit's `source_ref` range once through
  an index (`ix_dict_source`) and deletes by rowid: a first version issued one
  `LIKE` delete per member, and re-reading the CIHA kit took 45 minutes.
- **`curation.INHERITS`.** A system that republishes another's fields inherits
  that system's curation, and its own entries win. The only entry is
  DADOS_ABERTOS ← SIASUS.
  - `read_reference_table` falls back to the parent system's copy of a
    codelist. This is declared ownership, not cross-system borrowing, which
    stays off.
  - The vaccination exports (`DOSES_*`, `COBERTURA_*`) are not SIA and inherit
    nothing.
- **Key the unit with the age.** `key: [<unit>, <age>]` with `IDADEDET` on the
  four unit fields (ADR-0088's relation), so a row reads "63 anos (463)".
- **The ACF flags decode S/N from the layout** (inline `codes:`).
  `ACF_FREMIT` is a 1–4 grade with no documented anchors, so it is a
  measurement (`code_system: none`), not a code.
- **Not decoded, because no source gives the codes:**
  - `AP_TPATEN` 12: `TP_ATEND.CNV` lists 00–06;
  - `AP_TIPPRE` 00: every ACF row, and absent from `TIPOPRES`;
  - `AP_UFNACIO` `10`: two characters in a 3-character field, and never
    padded (CLAUDE.md §6).

  They read `code (?)`.

**Related change.** `query()` takes `allow_partial` (CLI `--allow-partial`).
The fetch layer's own error told the caller to pass it, but `query()`
hard-coded `False`, so one unreadable file out of 3,768 refused the whole
table. A short result now carries a `PartialSourceWarning`, and
`report.source_report.excluded` names the files.

**The label pack (added the same day).**
- **The shipped pack predated all of this.** `resources/labels.parquet` was built
  on 2026-08-23, so every fresh install decoded from it.
- **A rebuild from the corrected catalog would have dropped 368 codelists.**
  63 of them are bound by curation (SIA `PA_RACACOR` and `PA_MOTSAI`; SINASC
  `LOCNASC`, `RACACORMAE` and `CONSULTAS`; CNES `SERAP*`; SINAN dengue signs).
  The rebuilt maintainer catalog never re-ingested their sources.
- **Decision.** `build_label_pack(carry_from=)`, CLI `labelpack --carry-from`,
  keeps from the pack it replaces every **(codelist, validity window)** the
  catalog no longer holds. A window is lost only to a newer reading of it.
  - A first version carried whole codelists only. It lost SIH `COBRANCA`'s and
    `NACIONAL`'s current windows, because the catalog still reads their
    1992–2007 windows from the historical kits and the current kit has neither
    table. That version left the SIH discharge reason `12` and nationality
    `010` undecoded on a fresh home, as the fresh-home sweep showed.
- **Result.** Built with `--carry-from data/probes/labels_2026-08-23.parquet`:
  0 codelists lost, 367 carried forward. The dropped codes are the old parser's junk: `L` (a header flag),
  `BRANCOS` and `opcional` (comment text), and the glued readings.
- **Check.** On a new, empty home, `query("SIASUS-ACF", period="2023-01")` reads
  `AP_MOTSAI` "ALTA COM PREVISÃO DE RETORNO … (15)" and `AP_CATEND` "OUTROS TIPOS
  LESÕES/ENVENENAMENTOS … (06)".
