# SIGTAP's registration instruments decide which datasets can hold a procedure (2026-10-11)

**Regime.** Branch `sigtap-instruments`, data home `pegasus_core_data`, SIGTAP export 202609 (`rl_procedimento_registro`, 7,767 rows
over 5,023 procedures; only the newest vintage is kept, like the other SIGTAP tables). Verbs `procedure_instruments`, `can_record`
(`concepts.py`); declarations are `instruments:` on a SIGTAP column in `curation/roles/<dataset>.yml`, each with its evidence.

**Why.** A study scope admitted every dataset whose code tree held a seed code; SIGTAP is the tree of all SIA, so the five toxoplasma
serology procedures built APAC lakes that cannot hold them (6,800 files decoded for no record).

**Declared.** APAC families (AB, ABO, ACF, AD, AM, AMP, AN, AQ, AR, ATD, and their DADOS_ABERTOS republications) `AP_PRIPAL` 06;
SIA-PA all of 01, 02, 06, 07, 08, 09 (`PA_DOCORIG` P, S, C, I, A, B); SIA-BI 02; SIA-PS and DADOS_ABERTOS APAC_PS 09; SIH-RD, -RJ,
BASE_AIH1 `PROC_REA`/`PROC_SOLIC` 03, 04; SIH-SP `SP_PROCREA` 03, 04 and `SP_ATOPROF` 03, 04, 05 (no lake to measure). Left undeclared,
so unrestricted (`None`): SIA-SAD (RAAS-AD, 08, which SIGTAP lists for no procedure; all but 1,494 of its 3.32 M rows with listed codes are on 02),
CIHA and CIH-CR (non-SUS: 280.9 M CIHA rows hold the serology codes), APAC AB/ABO's `AB_PROCAIH*`, SIH-MT. A column declaring an
instrument the export never lists answers `None`, not `False`, for a code that matches none (SIA-PA, 0101010222).
The instruction named SIA-AD as RAAS; SIA-AD is the APAC for diverse high-complexity procedures (06), and RAAS-AD is SIA-SAD.

**Serology.** 0202030768 and 0202030873: 01, 02, 05; 0202110150: 02; 0213010577: 01, 02; 0101010222: 10 only (e-SUS APS, no DATASUS
FTP dataset). `can_record` over the five: True for SIA-PA, SIA-BI and SIH-SP's `SP_ATOPROF`; False for every APAC family, SIA-PS, and
SIH-RD/-RJ/BASE_AIH1/SIH-SP's principal procedure.

**Counter-check, serology records (the five codes) in the built lakes.** Forbidden: SIASUS AM 0 of 40.0 M rows, AN 0 of 5.65 M, AR 0 of
3.75 M, ATD 0 of 15.6 M, SIH-RD `PROC_REA` and `PROC_SOLIC` 0 of 205.7 M. Allowed: the SIA-PA RS 2018 extract (the records the five
codes match) holds 0202030768 151,155, 0202030873 145,821 and 0213010577 3,516, all of them PA_DOCORIG C or I (01, 02), none P, S, A,
B; 0202110150 and 0101010222: 0. Undeclared: CIHA holds the same codes 276,000 times, CIH-CR 7, SIA-SAD 0.

**Counter-check, whole relation.** Rows whose code is listed and registered on none of the column's declared instruments: APAC AM, AN,
AR, ATD 0 of 65.0 M (358 listed codes, all on 06); SIH-RD `PROC_REA` 12,984 rows, one code of 1,772, 0303090200 (conservative
fracture treatment of a lower limb), all in 2009 and registered by 202609 on 01, 02, 05 only. A vintage effect, a finding about the
data: the relation is today's and a procedure's instruments change, so `False` is trustworthy for the APAC families and SIH-RD as a
filter on a procedure the table lists, not a proof for 2009. Codes absent from 202609 (AR 2.75 M of 3.75 M rows, SIH-RD 2.4 M)
answer `None`.

**Not done.** Earlier vintages (224 monthly exports) are not read; a CLI command (the sibling concept verbs have none).
