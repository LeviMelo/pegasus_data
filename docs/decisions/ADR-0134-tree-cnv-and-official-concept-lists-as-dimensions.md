## ADR-0134: TabWin tree `.CNV` files are read as trees, their ranges expand against the canonical ICD-10, and the official concept lists are dimensions

**Date:** 2026-10-03. **Status:** active. Addresses OQ-28.

**Context.**
- **The lists.** The Ministry's own concept lists ship in its TabWin kits as
  `.CNV` files:
  - the mortality tabulation list (`CID10BR`);
  - avoidable causes of death for ages 0–4 and 5–74 (`CID10-EVIT0A4`,
    `CID10-EVIT5A74`);
  - hospitalisations for primary-care-sensitive conditions, ICSAP
    (`SENSIVEISATB03` groups, `SENSIVEISATB01` conditions).
- **Three parser defects made them unusable.**
  1. **Tree files were read as flat.** A line is written
     `  1   2  . 001 Doenças...` (parent, sequence, depth dots, label), and
     the parent number and the dots were taken into the label.
  2. **The expression column was misplaced.** An expression with a blank
     inside it (`A37 -A379`) moved the column, so the file fell back to
     token splitting: code `-A379` under label `Coqueluche A37`.
  3. **Ranges did not expand.** An alphanumeric range expanded only against
     the kit's own ICD table, and only for files named `CID*`. The ICSAP and
     avoidable-death lists kept every range unexpanded (OQ-28).
- **The result in the label pack:** `CID10BR` held 10 codes, and
  `CID10-EVIT0A4` 90.

**Decision.**
1. **Tree detection.** A `.CNV` is a tree when at least 40% of its lines
   open with two numbers and the second continues the running sequence.
   - The test is relative, so a year label (`009  2002`, ANOMES) is not
     taken for a child.
   - A child's parent number is kept as `CnvCategory.parent`.
   - Depth dots are layout, not label.
2. **Where the expression starts.** It extends left over a token only
   across a gap of at most one blank, and only while the suffix is still one
   expression. A label that is itself a code (`M480,`) never joins it.
3. **The range expansion universe** is the kit's ICD codes joined with the
   canonical ICD-10 (ADR-0087). An ICD-9 list gets none, since its V and E
   codes would collide with ICD-10.
4. **Dimensions** in `joins.yml`:
   - SIM `CAUSABAS`: `chapter`, `mortality_list`, `avoidable_0_4`,
     `avoidable_5_74`;
   - SIH `DIAG_PRINC`: `icsap_group`, `icsap_condition`;
   - CIHA `DIAG_PRINC`: `chapter`, `icsap_group`.

   TabWin's last-match rule stands, so a code reaches its most specific item.

**Evidence.**
- **The parser change across all 3,687 local `.CNV` files:**
  - 225,537 labels lost a parent number or depth dots;
  - 390 lost a code fragment;
  - the 763 codes lost were all fragments.
- **After the rebuild:** EVALUATION 2026-10-03 "Official concept lists as
  dimensions".
  - `CID10BR` covers 13,835 codes; each avoidable-death list 16,308; ICSAP
    693–701.
  - Unexpanded range rules: 686, from 1,586 in the last logged rebuild.
  - SIM SE 2022: every death resolves in all four SIM dimensions.
  - By label, 13,629 of 14,791 deaths sit in items whose counts equal
    TabNet's.

**Consequences.**
- **Two versions of the mortality list.** The kit's `CID10BR` (December
  2024) is older than the list TabNet serves:
  - it groups pregnancy causes as 088–091, where TabNet has 088–092, so
    every item number from 089 on is one lower than TabNet's;
  - the causes match by label, except within pregnancy (33 deaths in SE
    2022);
  - the dimension carries the kit's numbering.
- **The avoidable-death dimensions give the leaf cause.** Its parent group
  ("1.2 Reduzíveis por…") is held by the parser as `parent`, not yet in the
  label pack.
- **These lists apply to an age range** (0–4, 5–74). The caller filters by
  age; the dimension does not.
