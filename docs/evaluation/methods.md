# How measurements are made here

Derived from the August 2026 record (`docs/history/FINDINGS.md`,
`docs/history/pegasus_data_ARCHITECTURE.md` §17, §21, §22,
`docs/history/HANDOFF.md` §6) and from the rules in `CLAUDE.md` §5.

## Where a number comes from

1. **The live FTP tree, not a snapshot.** Facts about DATASUS are measured
   against `ftp.datasus.gov.br/dissemin/publicos` (and, for the secondary
   sources, `apidadosabertos.saude.gov.br`, `ftp2.datasus.gov.br`,
   `servicodados.ibge.gov.br`) on a stated date. The server reorganises without
   notice, so a count about the tree is true of one crawl, not of DATASUS in
   general (ARCH §22.5). The prior scan (`datasus_compendium.sqlite`, 124,810
   files) was treated as evidence about an earlier attempt, never as ground
   truth (ARCH §1).
2. **A header read before a decode.** A DBF declares its whole schema in a
   header of a few hundred bytes, and a `.dbc` stores that header
   uncompressed. A ranged fetch of the first KB answers any question about
   columns (the header census, FINDINGS §3g). It says nothing about values: a
   census stratum is marked `sample_status = 'header'`, never `'ok'`. Questions
   about values need a full decode of the payload, and they are the expensive
   ones.
3. **A real fetch, written to disk and read.** Labelling and rendering are
   verified by running `fetch()` or `query()` against the live tree, writing the
   file and reading the values in it. Six defects in August were invisible to a
   green suite and visible in the first CSV anyone opened (FINDINGS §3k).
4. **At the scale the component is for.** A layer that exists to be fast is
   measured on a national artifact, not on a fixture: three of August's defects
   passed every test at 2,417 cells and failed at 133,680 or 422,203 (FINDINGS
   §3q second, §3t).

## What "ground truth" means here

There is no labelled truth for DATASUS. What exists, in decreasing strength:

- **The file's own arithmetic.** DBF field widths must sum to the declared
  record length (100% of catalogued schemas did, FINDINGS §3g); a DBF header's
  record count is compared with the records the file holds (it errs high,
  DEFECTS HI-23).
- **Check digits.** CPF, CNPJ and CNS carry them, so an identifier's validity
  rate over hundreds of values decides whether a column is real or obfuscated
  (FINDINGS §3j).
- **An independent computation on the same rows.** An aggregate artifact is
  compared cell by cell with a direct `GROUP BY` over the microdata it was
  built from, and its totals with the file row count (FINDINGS §3o second).
- **A published figure.** TabNet's tabulation for the same query, or a
  national statistic (low birth weight at 9.5% of births, FINDINGS §3w). A
  roll-up that does not reconcile with TabNet is suspect first.
- **A second institution.** IBGE's territorial divisions against DATASUS's
  codelists, compared as partitions, never as label strings (FINDINGS §3p
  second).

## Rules for reading a result

- **Compare structure before strings.** Three apparent disagreements (311,844
  codelist contradictions, 295 health-region conflicts, 14.3% label agreement
  with IBGE) were manufactured by the comparison (FINDINGS §3e, §3n second,
  §3p second).
- **Name the denominator.** "Catalogued" columns are a moving denominator: the
  census grows (ARCH §21). A decode rate measured on 4 systems and the 200
  commonest values is a rate on that sample (ARCH §22.3).
- **Missing is not zero.** A file that would not open is a recorded
  `coverage_gaps` row; a structurally absent column is `absent`, not null
  data (ARCH §14.7).
- **A number found wrong is corrected where it was written, saying so.** The
  2026-08-20 CPF claim was withdrawn in place (FINDINGS §3j).

## The regime to record

Every entry names the command or script, the data home (a fresh one for live
checks; the repository's `pegasus_data_home/` hides fresh-install defects),
the commit, the date, and the artifact under `data/probes/`. August entries
predate `data/probes/` and name their commands and files inline.
