## 2026-08-23 — Building the aggregate layer

*Split from docs/history/FINDINGS.md §3o (second) on 2026-09-28; text unchanged.*

## 3o. Building the aggregate layer (2026-08-23)

### The compression that justifies an artifact, and the limit on it

| measured | value |
|---|---|
| `fetch("SIH-RD", uf="AC", years=2022)` | 130 s, 49,547 admissions |
| the same rows at municipality × month × sex | 989 cells — **50×** |
| at municipality × month × sex × **race** | 2,417 cells — **20.5×** |
| the build, end to end | 199 s for one state-year |

The second and third rows are the design constraint, not a curiosity. **Each
retained dimension spends the compression that justifies the artifact.**
Adding race alone halved it. `DIAG_PRINC` has ~14,000 ICD codes and would
multiply cells by roughly a thousand, at which point the artifact is larger than
the microdata it replaces. Hence one artifact per (dataset, binding, dimension
set) rather than one universal cube.

### The artifact reproduces a direct GROUP BY exactly

Checked, not assumed: 2,417 cells against 2,417 from a direct `GROUP BY` on the
same microdata, **identical key sets, zero disagreeing cells**, and totals
reconciling to the row count (49,547 admissions, 1,706 deaths,
R$ 43,377,991.73).

### Marginalising an axis is the same operation as rolling one up

"Total" is the pushforward to a one-point space. On live data, Total over sex
was 49,547 and the sum of its two observed categories was 49,547 — not because
that is asserted anywhere but because both derive from one base cuboid by the
same merge. A table whose total is not the sum of its parts discredits
everything else on it, and deriving rather than recomputing makes that
consistency structural.

### The partial-map failure, in real numbers

Rolling municipality up to `metropolitan_region` over Acre data serves **70 of
49,547 admissions**. A naive implementation returns 70 and it reads as a
national figure. The pushforward is not total — that classification covers 1,325
of ~5,570 municipalities — so the layer reports **49,477 unmapped** and says the
result is a subset total.

Even `health_region`, which covers 5,680 municipalities, left 5 admissions
unmapped in this slice. Small, and not zero, and now visible.

### `query(select=[...])` raises on synthesised hidden dependencies — FIXED in §3q

Found while wiring the build. Recorded here as it stood; the fix is in §3q.

```
query("SIH-RD", period="2022-01", geography="AC",
      select=["ANO_CMPT", "MES_CMPT", "MUNIC_RES", "SEXO"])
-> MissingColumnError: column '_competencia' is not present in family
   SIHSUS_RD_e2f7244ae5 (also absent: _source_resolution, year)
```

The planner adds `_competencia`, `_source_resolution` and `year` as hidden
dependencies, and they reach the *source* projection — but they are synthesised
during normalisation and no DATASUS family carries them, so the read refuses. It
only bites when `select=` is given; the unprojected call works.

The aggregate build therefore does not pass `select=` and projects afterwards.
That is a workaround, not a fix, and the defect is recorded as open.
