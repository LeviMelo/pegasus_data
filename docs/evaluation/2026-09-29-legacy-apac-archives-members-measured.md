## 2026-09-29 — SIA's 2001–2007 APAC archives: members measured by ranged header reads, and their establishments named by state

**Question.** Which tables does each of SIA's 1,723 legacy APAC archives
really contain? Can their establishment codes be named, given that the codes
are unique only within a state?

**Regime.**
- Maintainer home, branch `redesign`, commits `7769588`, `a9a57ca` and
  `767333e`.
- `pegasus-data schemas --all-files -s SIASUS` (the archive member census),
  then `inventory`, `schemas`, `families` and `scripts/build_resources.py`
  (`data/logs/rebuild-members.ps1`).
- Checked on a new home, `~/pegasus_fresh3`.

**What was counted, and why.**
- **Archives listed, and bytes read to list them.** Bytes on the wire are the
  scarce resource (CLAUDE.md §3).
- **Archives per component per year**, before and after. A component that
  reaches no archive cannot be queried; one assumed in an archive that lacks
  it makes an answer look short.
- **Undecoded establishment codes** on a real month.

**Result.**
- **Census:** 1,721 of 1,723 archives listed, 6,051 members. One 886 KB
  archive took 8 ranged reads (45 KB). Before the fix, 624 archives over
  512 KB failed: the first header was validated against the prefix.
- **Membership, archives per component:**

| component | 2003 | 2004 | 2005 | 2006 |
|---|---|---|---|---|
| EX | 0 → 266 | 0 → 281 | 0 → 323 | 0 → 310 |
| PC | 0 → 266 | 0 → 281 | 0 → 323 | 0 → 310 |
| AC | 275 → 273 | 297 → 283 | 0 → 323 | 0 → 311 |
| CO | 275 | 297 → 133 | 324 → 58 | 324 → 264 |

- **SIASUS-AC/EX/PC/CO, AC 2005-01, new home:** every component answers, and
  `*_CODUNI` reads "FUNDACAO HOSPITAL ESTADUAL DO AC (200158)" with 0
  undecoded. Before, EX, PC and AC refused `geography=`, and the codes were
  bound to nothing.
- **National SIASUS-CO 2005-01**, before the membership fix: 22 of 27 archives
  lack a CO table. They are now `members_absent`, not a short answer.

**Open.**
- 2 archives are unlisted (a connect failure, and an unknown LHA method).
- One stratum sample (`acal0302.exe`) fails the header read with an
  `IndexError`.
