## ADR-0241: The home's map is one file per version, rebuilt outside the launcher's job, and a stale map says so

**Date:** 2026-11-28. **Status:** active. **Amends** ADR-0216 (the compendium is the one map; `search` and `info` read it).
**Request:** the author, after a study session searched for data that had been landed hours before and was told
"nothing matches" (abnc2027_neuro `papers/TRIAL_t06b.md`, W9).

**Context.** On 2026-11-27 three sources were landed (`senatran_fleet`, `ibge_death_pairing`, `ibge_death_coverage`).
`pegasus-data search frota`, `fleet`, `sub-registro` and `pareamento` found none of them; the home's manual dated from
23 November. A study that asks "is this held?" and hears no asks for the data again. Three faults, each enough alone:
- **A rebuild could not replace the map while anyone read it.** The map was one file, `compendium.sqlite`. On Windows
  `os.replace` onto a file another process has open is refused (`PermissionError`), and every `search` and `info` opens
  it. The rebuild of 22 November ended there; eight staging files of 6 to 27 MB were left behind.
- **A rebuild that hung blocked every later one.** Its marker named a live process, so no other was started: one hung
  from 22 November until the machine was restarted on the 27th.
- **A rebuild started from the command line died with the command.** `pegasus-data` is a console-script launcher that
  runs Python inside a job object killing every process in it when the command returns. `DETACHED_PROCESS` does not
  leave a job. A rebuild started by `pegasus-data search` lived under a second (measured: gone within the same shell
  call), so a home used through the command line, as study sessions use it, never got a new map.
And nothing said so: the stale map answered as if current.

**Decision.**
1. **One file per version.** The map of a fingerprint is `compendium-<fingerprint>.sqlite` (`versioned_path`). A rebuild
   writes a name nobody has open; `current` serves the file of the home's fingerprint, or the newest older one while
   the new is built. Older versions and the staging files of dead rebuilds are pruned where free (`persist.kept`).
2. **A rebuild is alive for 30 minutes** (`REBUILD_LIMIT_S`; it takes 1 to 11). Past that its marker is ignored and
   another is started.
3. **The rebuild leaves the launcher's job** (`CREATE_BREAKAWAY_FROM_JOB`); where the job forbids that, the WMI service
   starts it (`Win32_Process.Create`), which is in no job of ours.
4. **A stale map says so.** `stale_since` is when the served map was built, if the home has changed since: `search`
   prints it with every answer, "nothing matches" included, and the overview opens with it.

**Consequences.** After a foreground rebuild (`pegasus-data manual`, 507 s, 1.57 GB) the four searches find the three
sources, the manual lists them, and `info SENATRAN.FROTA` reports 668,569 rows held. The first rebuild under the new
names wrote `compendium-b2decc229839330a.sqlite` and removed the old file and the nine staging files. Bringing a
source in ends with the map rebuilt and the search that had failed run again (abnc2027_neuro, research-workflow).
