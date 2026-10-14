## ADR-0182: Garbage codes are a declared classification: two published editions, levels 1-4, read by sort position

**Date:** 2026-10-14. **Status:** active. **Fulfils:** ADR-0140 item 4 (an openly licensed list is shipped after its licence is checked).

**Context.**
- An Alagoas study could not tell a real rise in AMI mortality from a recording change: AMI was 76.4 % of ischaemic heart disease deaths in
  2014 and 88.7 % in 2022, ill-defined causes 3.6 % to 6.4 %. The standard of Brazilian and global burden studies is the GBD's garbage codes in
  four levels; the project held only the TabWin kit's `SIM-POUCO-UTEIS`, whose five types the kit does not define.
- IHME's mapping is under a non-commercial agreement (ADR-0140). Two open-access supplements (CC BY 4.0) print the lists.

**Decision.**
- `curation/garbage_codes.yml` declares two editions, transcribed from their tables and never typed: **GBD2017** (França et al. 2020, Suppl. file 1:
  four range lists, one per level, and the note moving four codes) and **GBD2019** (Johnson et al. 2021, Suppl. appendix Fig. 3, the membership, and
  Fig. 4, class and package by garbage package). `garbage_codes(edition="GBD2019")` returns one row per ICD-10 code of the DATASUS release, spelled as
  SIM writes it: `level`, `package`, the printed token, `amended_from`, the source; the metadata says what was left out. CLI `garbage-codes`.
- **A printed range is a closed interval in ICD-10's order with the point** (A00 < A00.0 < A01): "R58.0-R78" stops at R78 itself, "A01" alone is the
  three-character code, an endpoint no code has ("ID5.9", "unsp.") closes the range where it falls. Reproducing França's Table 1 on SIM-DO Brazil
  2016 found it: level 2 equal to the unit, 16 of 18 leading groups equal, no code at two levels; the readings in which a three-character endpoint
  holds its subcodes put 16-29 codes at two levels and miss.
- **An edition is a claim about its own date:** a code ICD-10 created after the edition is not in it whatever a range spells (the ICD-10 tree's
  `valid_from`): COVID-19 (U07.1, U07.2) is no garbage code in either edition.
- **The default is GBD2019**, and the 2017 docstring and DATA_SOURCES say to use it from 2020 on: SIM-DO codes COVID-19 as B34.2 (Alagoas 2020-2021:
  3,589 and 4,239 deaths), a level-2 garbage code in GBD 2017 and none in GBD 2019. Both editions are kept; where they differ (86 of about 5,900
  codes) neither is overwritten.
- GBD2019's `level` and `package` are null for the 1,633 members its Figure 4 does not list (S00-T98, I50.0 and I50.1, N17, the mycoses): null,
  never the 2017 level. They are 4.5 % of Brazil 2016's member deaths.

**Alternatives.** Shipping only GBD2017 (complete levels): flags COVID as garbage in 2020-2021. Merging the editions' levels into one: a conflict
resolved silently. Hand-fixing the supplements' typos: the sort-position reading needs none, and the typos stay as printed. `code_lists.parquet`
(list, item, code): has no package, edition or source, and is built from the label pack; this is declared curation.

**Not decided.** Redistribution of the garbage deaths to target causes (Naghavi 2010's Annex 3 and Johnson's proportions are not used); the
~900 deaths of Brazil 2016 that the 2017 list places at level 1 and França's Table 1 at level 3 are unexplained.

**What would reverse it.** A published edition printing levels for every code in a form the reading rule does not reproduce.
