# Rendering past 2 GB of text (2026-10-24)

**Why.** `query('SNGPC-IND', period=2014, select=['TP_RECEITUARIO'], max_download=0)` crashed in rendering. Arrow's
`string` addresses 2 GiB of characters per array. The renderer flattened every chunked column (`combine_chunks`) and made
a label for every row with one `take`. SNGPC-IND 2014 is 58,625,324 rows read as 465 chunks; its labels are 2.3 GB of
characters and the `_source_path` column it carries is 5.4 GB. Three places failed in turn: `lookups._labels_for`
(`Take operation overflowed binary array capacity`), `view._render_table` on `_source_path` (`offset overflow while
concatenating arrays`), and `presentation._render_values` (the default "label (code)" cells, 3.1 GB).

**Change.** A column is read as the ChunkedArray it is and never flattened; a column built row by row is built in pieces
of at most `lookups.PIECE_BYTES` (1 GiB) of characters, cut so that even if every row took the longest value the piece
stays under the limit (`lookups.expand`; `joined` does the same for a composite key, `dictionary_of` encodes a chunked
column once, `contiguous` keeps a column that fits one array as one array). Types do not change with size: `X` and
`X_label` are `string` in ten rows and in 58 million; only the number of chunks grows, and `pa.concat_tables` in
`render_groups` appends chunks. The label decision still weighs the value counts of all the rows given; the labels are then
applied piece by piece. `presentation._render_values` no longer joins every row's code and label into a string to count
the distinct pairs (2.4 GB of characters made only to be counted): a pair is two integers. `query` no longer keeps the
reading's own table to its end (it held `_source_path`, 5.4 of the 6 GB, while the answer was presented).

**Regime.** Branch `worktree-agent-ae4e99940cc3e178d` from `ee434cc`; home `C:\Users\Galaxy\pegasus_core_data`, read with
`max_download=0`; 2026-10-24, on a machine shared with other jobs (times are of a loaded machine). The "before" code is
`ee434cc` exported to a scratch folder. Scripts are in the session's scratch folder; no artifact under `data/probes/`.

## The failing query

| | |
|---|---|
| rows | 58,625,324 |
| `present="analysis"` | `TP_RECEITUARIO` and `TP_RECEITUARIO_label`, both `string`; code 1 chunk (0.29 GB), label 4 chunks (2.84 GB) |
| code `5` / `1` / `2` / `3` / `4` | 39,538,457 / 12,987,501 / 3,993,323 / 1,721,438 / 384,605 (sum 58,625,324, no null) |
| label of each | Receita Antimicrobiano e GLP-1 em 2 vias / Receita de Controle Especial em 2 vias (Receita Branca) / Notificação de Receita B (Notificação Azul) / Notificação de Receita Especial (Notificação Branca) / Notificação de Receita A (Notificação Amarela), the same counts |
| default presentation | one `string` column "label (code)", 4 chunks (3.08 GB), the same five values and counts |
| wall, peak RSS | 66 s and 11.0 GB (analysis); 70 s and 11.8 GB (default) |

Before the change it failed after 14 s at 9.3 GB. Peak by stage (an earlier run, with the pairs still joined as strings):
reading 6.7 GB, render 9.8 GB, the executor's `_with_competence`/`_with_source_resolution` 12.7 GB, presentation 16.3 GB;
the pair counting and the executor release took presentation to 7.3 GB.

## Results that already worked, unchanged

Whole-table equality (`Table.equals`: schema, every value) between `ee434cc` and this change, on six real results, in the
default presentation and in `present="analysis"` (`X` and `X_label` separate):

| query | rows | columns (default / analysis) | paths it exercises |
|---|---|---|---|
| SIH-RD 2023-01 AC | 4,165 | 124 / 186 | derived columns, `label_via` (CNPJ_MANT through CNES) |
| SINAN-DENG 2024, SOROTIPO, CLASSI_FIN, CS_SEXO | 6,564,924 | 3 / 6 | three coded columns over 6.5 M rows |
| SIM-DO 2014, 7 columns | 1,227,039 | 7 / 14 | multi-valued `LINHAA` |
| SINASC-DN 2015, 6 columns | 3,017,668 | 6 / 12 | multi-valued `CODANOMAL` |
| CIHA-CIHA 2022-01 AC | 263 | 33 / 50 | composite key `COD_IDADE` + `IDADE` ("77 anos") |
| SIA-PS 2014 AC | 5,354 | 51 / 80 | `label_via` (CNPJMNT through CNES_EXEC), a 12-chunk read |

All twelve equal. With `PIECE_BYTES` forced down to 8 KiB (the small three) and 1 MiB (the large three) the same twelve
are equal again, now in 9 to 1,117 chunks per column, so the multi-piece paths of `expand`, `joined` and
`contiguous` ran on real codes and labels. The task's `SINAN-DENG ... select=[..., 'SEXO']` does not run before or after
(`MissingColumnError`: the column is `CS_SEXO`).

## Seen, not changed

* `_source_path` is 5.4 of the 6 GB the SNGPC-IND year is read as: plain strings, one path per row, where the lake holds
  it dictionary-encoded. Read as a dictionary (as `filters._per_path` already accepts) it would be about 0.3 GB, but a
  `provenance="all"` caller would then get another type, so it is the loader's decision (the planner fix, reading a month
  rather than the year, shrinks the rows anyway).
* Between the render and the presentation `query` spends 47 s and 3 GB on SNGPC-IND 2014 in `_with_competence` and
  `_with_source_resolution` (int64 temporaries, a `_per_path` pass over the path strings).
* `_query_engine/semantics._distinct` (dimensions) still flattens its joined key with `combine_chunks`; it is not on the
  rendering path and was not reached.
