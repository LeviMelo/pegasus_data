# Response to review 2 - paper 3, `black_category/`

New analyses: `analysis/mechanism.py` (key `black`), `mechanism2.py` (keys `filler`, `movers`), `physician.R`, and
`counts.py mechanism`, which adds the delivery records with `TPFUNCRESP`, the mother's birth date and her parity. The
ledger is `black_category/ledger.md`; the paper's Table 2 sets readings against tests.

| Review item | Done |
|---|---|
| Top 1: movers (person against hospital) | Done. Mothers with two births in municipalities under 1,600 births a year were paired by the mother's birth date and residence, with parity rising. A one-day shifted-date control gives 34.5% chance pairs; every estimate subtracts the control pairs. In the same hospital, a mother recorded Black is recorded Black again 0.92; in another hospital, 0.58. When she changes hospital her record moves by 1.01 (SE 0.03; 1.16 corrected) of the practice difference. The hospital sets the level; the paper says so. |
| Top 2: physician, establishment, copying | Done. Crossed variance (Laplace, 2014-2018): physician 0.29, establishment 0.42, municipality 0.21. Copying: within the establishments of death, OR 1.98 for infants who died where delivered and 1.75 (1.25; 2.44) for those who died elsewhere. Not done: the infant's own SIH record (needs the neonatal admission link run for 2013-2023); investigation by source is in paper 1. |
| Top 3: the reference, newborn colour, wording | Who filled the birth record: within hospitals, the Black share of declarations differs by -0.7 (physician) and -1.0 (other staff) points against nursing. The declaration is not stable: of mothers declaring Black, 0.52 do so again at the next birth (White 0.75, Brown 0.87), and the paper states this. The newborn colour cannot be used (212 records). The title and unit are now "infants of Black mothers", and "undercount Black infants" is now a count ratio. |
| Top 4: facility model | Practice is now leave-one-out and shrunk by a beta prior, clustered by hospital: 1.33 alone, 1.20 with composition, region and year, 1.10 beside the mother's record (OR 1.89). Blanks are bounded at 0.28-0.50. Not done: CNES ownership and teaching status as moderators. |
| Top 5: time decomposition, cut overlap | The rise standardised to the mothers of 2013 runs 0.155 to 0.233. A joint model on the same infants shows the hospital rising 0.37 log-odds a decade less (SE 0.09). The 2023 jump in the hospital series is explained: SIH filled race from 2023, with blanks at 21.5% in 2022 and 2.8% in 2023. Cut: the map, state against composition, adult women and the 5-9 row from Table 1, Figure 1 and the Abstract. |
| 4.3 MH heterogeneity, adjusted | Breslow-Day p = 0.003, stated. Conditional logit adjusted for schooling, age, birth weight, year and age at death: 2.01 (1.77; 2.28). |
| 4.5 net intervals | Hospital 0.74 (SE 0.03, bootstrap over hospitals); certificate 0.34 (SE 0.009, over municipalities). |
| 4.9 multilevel | The physician model is Laplace; the full model remains nAGQ = 0, as stated in the figure note. |
| 5 claims | Rewritten as proposed: title, abstract, "associated with" where an association is meant, the copying sentence, and the commissions sentence deleted. |
