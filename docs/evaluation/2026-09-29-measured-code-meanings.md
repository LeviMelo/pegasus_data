# Measured code meanings: SIH secondary-diagnosis type, SIH-SP travel flags, SIA residence and occurrence codes

**Date:** 2026-09-29. **Regime:** commit after 9679c8a (ADR-0105), new data
home `~/pegasus_fresh`, live FTP.

**What was run.** `p.query(...)` in the default (labelled) profile on SIA-PA AC
2023-01 and 2012-01, SIH-RD AC 2023-01 and SIH-SP AC 2023-01; each column's five
commonest rendered values counted. The meanings themselves were measured before
this run, against another column of the same record (ADR-0105's table).

**Why these counts.** A label written from a measurement must decode every
value it claims and must not hide the kit's table behind it; the check is that
no value renders as "(?)" and that the counts match the measurement.

**Counted.**

| dataset | column | rendered |
|---|---|---|
| SIA-PA AC 2023-01 (95,414) | `PA_CODOCO` | APROVADO TOTALMENTE (K) 93,863; TETO FINANCEIRO (R) 1,245; ULTRAPASSOU TETO FINANCEIRO (O) 216 |
| | `PA_UFDIF` | Mesma UF 72,654; Município de residência ignorado 21,398; UF diferente 1,362 |
| | `PA_MNDIF` | Mesmo município 62,786; ignorado 21,398; município diferente 11,230 |
| | `PA_TIPPRE` | Não preenchido 95,414 |
| SIA-PA AC 2012-01 | `PA_TIPPRE` | Esfera Estadual (40) 46,935; Esfera Municipal (50) 22,404; Estabelecimento Privado com Fins Lucrativos (20) 259 |
| SIH-RD AC 2023-01 (4,165) | `TPDISEC1` | Sem diagnóstico secundário 3,793; Preexistente 355; Adquirido 17 |
| SIH-SP AC 2023-01 (46,933) | `SP_DES_HOS` | Mesma UF 44,642; UF diferente 2,291 |
| | `SP_DES_PAC` | Mesmo município 32,700; município diferente 14,233 |
| | `SP_U_AIH` | Registro que conta a AIH 4,165; adicional 42,768 |

**Findings.**
- The first run left `PA_UFDIF`/`PA_MNDIF` 0 and 1 as "(?)": inline codes
  dropped the curated fallback (fixed in `label_bindings.decide`). After the
  fix, 2012's `PA_TIPPRE` falls through to the kit's tables.
- `SP_U_AIH` = 1 on 4,165 rows equals SIH-RD's 4,165 AIHs for AC 2023-01, an
  independent count.
- Labels carried TabWin's order marks ("02 ..APROVADO…", "5 ..Estabelecimento…");
  now stripped at render (100,243 pack labels match, 0 emptied).

**Artifact:** `data/probes/live/2026-09-29-measured-codes.txt`.
