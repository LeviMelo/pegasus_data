# Official concept lists as dimensions, checked against TabNet

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`, with the ADR-0134 parser;
- `pegasus-data semantics --root pegasus_data_home`, then `labelpack`
  (`data/logs/semantics_rebuild.done`): semantics exit 0 in 6,122 s, label
  pack exit 0 in 346 s;
- queries on `C:\Users\Galaxy\pegasus_linkage`.

**Why.** A concept list is a useful dimension only if its codes cover the
list and each death lands where the Ministry's own tabulation puts it.

**Label pack, before and after** (rows / distinct codes / distinct labels):

| codelist | before | after |
|---|---|---|
| `CID10BR` | 10 / 10 / 10 | 13,835 / 13,835 / 133 |
| `CID10-EVIT0A4` | 90 / 90 / 90 | 16,308 / 16,308 / 95 |
| `CID10-EVIT5A74` | 89 / 89 / 81 | 16,308 / 16,308 / 81 |
| `SENSIVEISATB03` (ICSAP groups) | 72 / 24 / 21 | 2,103 / 701 / 19 |
| `SENSIVEISATB01` (ICSAP conditions) | 225 / 75 / 71 | 2,079 / 693 / 75 |

- **The whole pack:** 3,658,724 → 4,211,547 runs.
- **Unexpanded range rules:** 686, from 1,586 in the last logged rebuild.
- **Labels are clean:** `I21` reads "068.1 Infarto agudo do miocárdio"; `A09`
  reads, in ICSAP, "2. Gastroenterites Infecciosas e complicações".
- **ICSAP leaves out codes the official list names only through a
  subcategory:** it lists `J18.1` and `N39.0`, not `J18` or `N39`.

**SIM-DO SE 2022** (14,791 deaths, 4.5 s).
- Every death resolves in `chapter`, `mortality_list`, `avoidable_0_4` and
  `avoidable_5_74`.
- Top items: chapter IX, circulatory, 3,463; "070 Doenças cerebrovasculares"
  1,041; "055 Diabetes mellitus" 958.

**Against TabNet** (`sim/cnv/obt10se.def`, `obtse22.dbf`, row "Causa -
CID-BR-10", deaths by residence). TabNet's total is 14,791, equal to ours.
- **Matched by label, 13,629 deaths are in items whose counts equal
  TabNet's.**
- **The rest is hierarchy level:**
  - TabNet's parent rows are subtotals. "Doenças isquêmicas do coração" is
    936 in TabNet; in the dimension, 114 are left at the parent and the rest
    sit under 068.x.
  - Single-item chapters appear in TabNet with no leaf row.
- **One real version difference: the kit's list is older than TabNet's.**
  - The kit numbers pregnancy 088–091 ("089 Outras mortes obstétricas
    diretas", O10–O92). TabNet numbers it 088–092, with O95 and O96–O97 as
    separate items.
  - Every item number from 089 on is therefore one lower in the dimension
    than in TabNet. TabNet's "103 Rest sint…" is the kit's 102, and the
    counts per cause agree.
  - The pregnancy chapter's 33 deaths split 1/17/8/7 here, against
    1/16/9/2/5 in TabNet.

**SIH-RD SE 2022-01** (8,512 AIH, 1.8 s).
- `DIAG_PRINC.chapter` resolves every row.
- ICSAP flags 1,115 AIH (13.1%): "15. Infecção no rim e trato urinário"
  154, "12. Doenças cerebrovasculares" 138, "11. Insuficiência cardíaca"
  113.
