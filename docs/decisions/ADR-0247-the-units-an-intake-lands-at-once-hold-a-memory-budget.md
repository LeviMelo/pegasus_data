## ADR-0247: The units an intake lands at once hold a memory budget

**Date:** 2026-11-28. **Status:** active. **Request:** the platform session, after landing SNGPC's industrialized
sales one unit per process by hand: "the intake has no option to bound units in flight"; ADR-0240's sense of bounded.

**Context.** `adaptive_map` chooses how many units land at once by the rate they give (ADR-0218's controller): it
starts at four and knows nothing of memory beyond not adding a task under the admission floor. Each landing opened a
connection allowed a decode slot's share of the machine (7 GB here), whatever its file. Four SNGPC months in flight
were therefore allowed 28 GB on a 32 GB machine; one month alone peaked 7.39 to 7.59 GB (it fills what it is given).
The bound has to hold for a 5.9-million-record month and still let ANS's 8,100 files of 340 KB land many at once.

**Decision.**
- `concurrency.MemoryBudget`: what the tasks in flight of one process may hold together, the free memory less the
  admission floor measured when nothing is held, never under one slot's share. A task takes its grant before it opens
  its connection and waits while there is no room; a grant larger than the budget runs alone.
- A landing's grant is its connection's memory limit, sized by what it reads: its records' cells for a unit derived
  again from the lake, its file's bytes for one read from the source (`intake._grant_gb`: 1 GB plus 45 bytes a cell,
  or plus 8 bytes a file byte, up to the slot's share; the whole share where neither is known).
- The figures only choose how many land at once. A landing that runs out of memory under its grant is run again
  holding the whole share (`intake._granted`, recorded as `granted_again_gb`), so a low figure costs time, never a
  failure and never the machine.

**Consequences.** Four stale industrialized months of 2019 landed in one process (scratch home, from the lake): one
at a time under a 5.0 GB grant each, 5.39 GB peak for the process, 85 s, the year's 75,450,371 rows and no
unallocated row; the same four were allowed 28 GB before. A month given a 0.5 GB grant on purpose ran out, was run
again with 7 GB and landed its 6,574,501 rows. Small units keep landing side by side (a 340 KB file is granted 1 GB).
Not covered: the API landings and `land_snapshot` open their connection with the whole share outside the budget (one
at a time by construction); several processes are bounded by what starts them.
