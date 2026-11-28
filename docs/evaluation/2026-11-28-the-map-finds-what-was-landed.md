# The map finds what was landed; an archive is opened in one place (2026-11-28)

Regime: the working tree on 04990c91, the one home (`C:\Users\Galaxy\pegasus_core_data`), Windows 11. ADR-0241, ADR-0242.

**What was counted, and why.** Whether a person who asks `search` for a source that is held is told so: three sources
landed on 27 November were not found a day later, and a study asked for them again.

| Step | Result |
|---|---|
| `search frota`, `fleet`, `sub-registro`, `pareamento`, `death coverage` on the map of 23 November | no hit for any of the three sources ("nothing matches" for four of the five) |
| The stored rebuild log | `PermissionError` on `os.replace` of the staging file onto `compendium.sqlite` (22 November); eight staging files left |
| A rebuild started by `pegasus-data search`, watched | gone within the same shell call, before any output (the launcher's job) |
| `pegasus-data manual` in the foreground | 507 s, 1.57 GB peak: 190 datasets, 198 fields, 9,336 SIDRA tables |
| The same five searches after it | each finds the source (dataset, variables and fields); `info SENATRAN.FROTA` holds 668,569 rows, 2015-2024 |
| First rebuild under versioned names | wrote `compendium-b2decc229839330a.sqlite`; the old file and nine staging files removed |
| A rebuild started by `pegasus-data search` after the change | alive after the command returned and in a later shell call |
| `search` on a stale map | answers, and prints that the map is of a given time and the home has changed since |

**Archives (ADR-0242), in a scratch home, removed after.** `intake senatran_fleet --years 2015` (twelve RAR archives
through `ArchiveFile`): 66,840 rows; motorcycles 237,368,050 and scooters 44,789,015 summed over the months, equal to
the home's. `intake ibge_death_pairing --years 2024` (a zip): 14,690 registry only, 51,638 SIM only, 1,478,428 in both,
IBGE's Tabela 2.2. `tests/test_intake_excel.py` 12 pass.

Not measured: the WMI fallback (the launcher's job allowed the breakaway here).
