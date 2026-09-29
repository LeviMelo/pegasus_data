## 2026-08-18 — V3: the .CNV and .DEF grammars

*Split from docs/history/FINDINGS.md §1 V3 on 2026-09-28; text unchanged.*

### V3 — `.CNV` and `.DEF` grammars · **resolved**

Learned from the 79 uncompressed files under `PNI/AUXILIARES/` and the 177 `.CNV` members of
`TAB_SIH_199201-199712.zip`.

**`.CNV`:**

```
<n_categories> <code_width>
<seq:right-aligned><spaces><label:padded><spaces><match-expression>
```

The match expression is a single code, a comma-separated list, a range, or a mixture. The
expression column is 60 in most files and 64–66 in others, so it is inferred per file rather than
hard-coded.

Two properties a naive reading gets wrong:

- **Last match wins.** `SEXO.CNV` lists `Ignorado → 0-9` *first*, covering the whole domain, then
  overrides it with `Masculino → 1` and `Feminino → 2,3`. First-match-wins would label every
  record "Ignorado". The idiom recurs — `IDADE18.CNV` opens with `Ign → 000-999`.
- **A `.CNV` is a codelist, not a column.** It never says which field uses it, and one codelist
  serves several fields. The binding comes from `.DEF`.

**`.DEF`:**

```
;comment (the first one is the title)
A..\DADOS\RD_AIH_Reduzida\RD*.DBC      the data glob this tabulation reads
?\TAB\RD.HLP                           help file
IValor Total       ,VAL_TOT            Incremento — an additive measure
LRegião int        ,MUNIC_MOV ,1  ,REGIAO.CNV     Linha
CRegião int        ,MUNIC_MOV ,1  ,REGIAOC.CNV    Coluna
SUF - ZI           ,UF_ZI     ,1  ,UFALFA.CNV     Seleção
XCapital int       ,MUNIC_MOV ,1  ,CAPITAL.CNV    all three
LHospital BR (CNES),CNES  ,RAZAO ,TCNESBR.DBF     DBF lookup, label column named
```

`RD.DEF` has 547 lines: 199 `L`, 176 `S`, 73 `X`, 52 `;`, 25 `C`, 20 `I`, 1 `A`, 1 `?`.

The `I` prefix is worth more than it looks: it is **the Ministry's own statement that a variable is
summable**. `IValor Total,VAL_TOT`, `IÓbitos,MORTE`, `IPermanência,DIAS_PERM` — exactly what
`ledger.aggregation` needs, sourced rather than inferred.

The `A` line binds a dictionary to the data files it describes, so a `.DEF` attaches to a family
instead of being guessed at.
