## 2026-08-21 — Identifiers and re-identification risk in public SIASUS files

*Split from docs/history/FINDINGS.md §3j on 2026-09-28; text unchanged.*

## 3j. Identifiers and re-identification risk in public SIASUS files (2026-08-21)

**This section is the reason the personal-identifier detector exists, and it is
the one finding here that is not about data engineering.**

An earlier draft of this section (2026-08-20) claimed that CPFs were published
alongside HIV results. **That claim was wrong and has been withdrawn.** It was
drawn from column *names* and value *shapes* without testing either. Both are
now tested, and what is actually there is set out below. The correction is kept
in view rather than quietly edited away, because the difference between the two
readings is exactly the difference between a credible referral and one that
falls apart on first inspection.

### Method

Two things make these claims decidable rather than a matter of appearance:

- **CPF, CNPJ and CNS all carry check digits.** A value either satisfies its
  algorithm or it does not. A random 11-digit string passes the CPF check about
  1% of the time, so a 0% or 100% rate over hundreds of values is not chance.
- **The join can be executed** rather than inferred from two columns happening
  to hold values of the same width.

Everything below is measured on the files, not on the catalogue's metadata.

### Finding 1 — patient identifiers are obfuscated, not published

Measured on `SIASUS/APAC/2002/acac0201.exe` (Acre, January 2002) and on four
2008-schema `.dbc` files (16,918 rows):

| column | values | distinct | pass check digit |
|---|---:|---:|---:|
| `PAC_CPFPCN`, `EXA_CPFPCN` | 52 each | 52 | **0 (0%)** |
| `APA_CPFPCN` | 305 | 117 | **0 (0%)** |
| `COB_CPFPCN` | 485 | 119 | **0 (0%)** |
| `PAF_CPFPCN` | 98 | 98 | **0 (0%)** |
| `OPC_CPFPCN` | 155 | 1 | **0 (0%)** |
| `AP_CNSPCN` | 16,918 | ~93% distinct | **0 (0%)** |

Every column whose name ends `PCN` — *paciente* — fails. `AP_CNSPCN` fails
harder than that: its values contain **no digits at all** (`é{~…|{{`,
`âäâ{{|{|äü}Çââ}`), fifteen characters of transformed bytes. They stay highly
distinct, so they still function as a per-patient pseudonym that links a
person's records to each other — but they are not a readable CNS, and they do
not identify anyone outside DATASUS.

**There is no evidence in this data that DATASUS publishes patient CPFs or
CNSs in the clear.** The apparent CPFs in the 2002 files are eleven digits that
are not CPFs.

### Finding 2 — professional and director CPFs *are* real, and are published

The same file, same test, opposite result:

| column | whose | values | distinct | pass check digit |
|---|---|---:|---:|---:|
| `APA_CPFRES` | responsible professional | 305 | 42 | **305 (100%)** |
| `APA_CPFDIR` | clinic director | 305 | 4 | **305 (100%)** |
| `UDI_NFRCPF` | nurse | 2 | 2 | **2 (100%)** |
| `UDI_DIRCPF` | director | 2 | 2 | **2 (100%)** |

100% validity over 612 values is not an accident of formatting. These are real
CPFs of identifiable individuals, in an unauthenticated FTP directory. The
distinct counts are small — **four** directors, forty-two responsible parties —
so each value maps to one named professional at a known clinic in a known
municipality, which is what makes it identifying rather than merely sensitive.

`AP_CNPJCPF` also validates 100% (16,918/16,918) but as **CNPJ**, with 3–62
distinct values per file: those are establishments, not people. It does not
belong on a list of personal identifiers, and the earlier draft was wrong to
put it there.

### Finding 3 — the patient record is re-identifiable, and carries serology

This is the finding that survives, and it is the serious one.

`EXAC0201.DBF` holds `EXA_HIV`, `EXA_HBSAG`, `EXA_HEPAT` and `EXA_HLA` **in the
same table** as the patient block's key. The join to `PCAC0201.DBF` was executed,
not assumed: `PAC_NUM` ↔ `EXA_NUM`, 52 rows against 52 rows, 52 distinct keys
each, **52/52 matching, one to one**. `EXA_HIV` over those rows: 51 `N`, 1 `P`.

What sits on the joined record, all of it real and unobfuscated:

```
PAC_NASCPC  19351014   full date of birth
PAC_SEXOPC  M          sex
PAC_MUNPCN  120040     municipality
PAC_CEPPCN  69900000   postcode
PAC_UFNASC  AC         state of birth
PAC_DIAGPR  N189       CID-10 primary diagnosis
PAC_DIAGSE  N189       CID-10 secondary diagnosis
```

The modern schema is no better on this axis: in `ADGO1403.dbc`, `AP_CEPPCN`
holds full eight-digit postcodes with 2,484 distinct values over 5,670 rows,
beside age, sex, race, municipality and CID-10.

Date of birth, sex and postcode are the classic quasi-identifier triple, and in
Brazil an eight-digit CEP frequently resolves to a single street segment. Fifty-two
dialysis patients in one small municipality, each with an exact birth date, is not
an anonymous population. **No direct identifier is needed to re-identify these
people, and an HIV result is attached to the record.**

### And it is data the earlier scan never saw

The 2002 files are self-extracting `.exe` archives. The prior scanner excluded
them by extension — defect D1 — so 1,723 APAC files were absent from its
inventory entirely. Recovering them was a correctness win for coverage (§1) and
is *also* what surfaced this.

### What this module does, and deliberately does not do

Every one of these columns **passes through unmodified**. Nothing is masked,
hashed, truncated or dropped, and that is a decision rather than an omission:

- Masking in a library would destroy the evidence that the data was published.
  A researcher receiving a masked extract cannot tell whether the Ministry
  publishes these columns or whether a tool removed them.
- The remedy is not a client-side transformation. It is a decision about what
  DATASUS publishes, and that requires the Ministry to see the finding.
- Deciding what may be disclosed about a named person is not a call a data
  library is entitled to make.

What the module does instead is **make it impossible to miss**: the detector
flags the columns, the ledger raises an open question, the generated
documentation carries the warning, and this section records the measurement.

### What is NOT established

Stated plainly, so that nobody carries these forward as though they were:

1. **Whether the patient pseudonyms are reversible.** They are stable and highly
   distinct. Whether the transformation is recoverable was not investigated, and
   deliberately so — that work would itself be an attempt at re-identification.
2. **Whether `CNS_PAC` in PAINEL_ONCOLOGIA and CMD behaves like SIASUS's.** It
   appears in 11,628 files across two systems and was **not** tested; the
   obfuscation measured here is a SIASUS result and must not be generalised to
   it. The curation note on that column is marked unverified.
3. **Whether the 2002 pattern holds across all 1,723 APAC files.** One file was
   joined. The schema is shared, so the structure almost certainly is, but
   "almost certainly" is not a measurement.
4. **Actual re-identification was not attempted.** Finding 3 is an argument from
   the quasi-identifiers present, not a demonstration.

### For whoever takes this forward

The column-name census (this counts *names in DBF headers*, not verified values
— all 144 `AP_CNSPCN` strata are `sample_status='header'`):

```sql
SELECT sp.field_name, SUM(s.file_count) AS files
  FROM schema_presence sp
  JOIN strata s ON s.schema_signature = sp.schema_signature
 WHERE sp.field_name LIKE '%CPF%' OR sp.field_name LIKE '%CNS%'
 GROUP BY 1 ORDER BY files DESC;
```

The claims that matter are the value-level ones, and they are reproduced by
reading `SIASUS/APAC/2002/acac0201.exe`, running each identifier column through
its check-digit algorithm, and joining `PAC_NUM` to `EXA_NUM`.

**The referral should lead with Findings 2 and 3.** Finding 1 is exculpatory and
should be stated in the same breath: DATASUS is already protecting the patient
CPF and CNS, which is evidence that the omission in Findings 2 and 3 is an
oversight in the same system rather than indifference.

Open question: `V.pii_disclosure`. It is not resolvable by this project — it
closes when the Ministry answers, and until then it stays open on purpose.
