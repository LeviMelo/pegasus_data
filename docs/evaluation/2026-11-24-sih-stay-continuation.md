# Which SIH discharge reasons continue a stay: 51 does, 18 and 25 partly (2026-11-24)

Regime: pegasus_data 0da8018e; home `C:\Users\Galaxy\pegasus_core_data`; SIH-RD 2019, BR, IDENT 1, persons keyed by
birth date, sex and residence CEP (the stay chain's key).

**What was counted.** For each discharge reason (COBRANCA) with over 500 AIHs, the share whose person has another AIH
starting -1..1 days after the discharge: at the same CNES (the chain's continuation) and at another CNES (a transfer).
This is the declaration's own window (core.yml, stay chain). The independent reference is the reasons the chain
already declares: 22, 26, 27, 28 and 31.

| reason | AIHs | next AIH, same CNES | next AIH, other CNES |
|---|---:|---:|---:|
| 12 alta melhorado | 7,118,632 | 0.8% | 0.5% |
| 18 alta outros motivos | 50,452 | 13.9% | 2.6% |
| 21 perm. características da doença | 95,984 | 44.7% | 0.1% |
| 22 perm. intercorrência | 93,667 | 89.0% | 0.2% |
| 23 perm. impossibilidade sócio-familiar | 9,131 | 1.3% | 0.1% |
| 25 perm. doador morto | 24,915 | 22.9% | 20.8% |
| 26 perm. mudança de procedimento | 151,007 | 92.9% | 0.2% |
| 27 perm. reoperação | 167,002 | 94.6% | 0.2% |
| 28 perm. outros motivos | 23,712 | 85.2% | 0.3% |
| 31 transferência | 410,296 | 1.4% | 41.1% |
| 41 óbito com DO | 486,301 | 2.0% | 0.5% |
| 51 encerramento administrativo | 129,979 | 78.7% | 0.5% |

- **51 continues a stay** like the 2x reasons: now declared (0da8018e, DECISIONS of the ABNc line D-6). It was missed
  until t08 found deaths on the continuation AIH.
- **25 (deceased donor) continues across hospitals in a fifth of cases.** The next AIH is the donation, on a person
  already dead, so leaving it unchained changes no patient's outcome. Not declared.
- **18 continues at the same CNES in 13.9%:** mostly an end, a minority behaving like 51. Not declared. A study whose
  cohort holds many 18 discharges should check by state.
- **23 is declared a continuation but rarely has a next AIH (1.3%).** Harmless: the chain only joins an AIH that
  exists.
