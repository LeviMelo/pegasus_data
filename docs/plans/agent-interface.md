# Plan: pegasus_data as an encyclopedia for agents (2026-11-21)

The author asked for an interface through which an LLM agent working under a harness (Claude Code, Codex, a CI agent)
knows everything this install holds and can do, and left the design to me. Their earlier idea was all the data in one
SQLite database. This plan replaces it.

## What an agent under a harness is good at

- It has a shell and file tools. It greps, reads files and runs commands.
- Its context is the scarce resource. A 17k-token dump read on every task costs more than any download.
- It reads a reference as text, and loses track in a schema it must query blind.
- It trusts what it reads. A stale or contradictory description misleads it silently.

So the interface is **text it can grep**, **in tiers it can descend**, **generated from the one map** (the compendium),
so it is never out of date. A database the agent must query with SQL is the wrong layer. The compendium stays a
database because the generator and `search` need one; agents get its text.

## The design

1. **A generated manual in the data home** (`<home>/manual/`), rebuilt with the map:
   - `INDEX.md`: under 2k tokens. What kinds of data exist (records, aggregates, registries, links, products, extracts),
     the counts, and the commands that descend. It is the only page an agent reads unasked.
   - One page per system and per dataset, column, link, product and SIDRA table. Each page carries what `info <name>`
     prints, plus its meaning, years held, what each year lacks, the evidence and the commands that read it.
   - The pages live in plain directories (`datasets/SIH-RD.md`, `columns/SIH-RD/DIAG_PRINC.md`, `links/<name>.md`), so
     `grep -r "thrombectomy" manual/` finds the code, the column and the link at once.
2. **The CLI keeps parity**, with `--json` on every reading command. `info` alone prints `INDEX.md`'s tier. The 67 KB
   overview moves to `info --all`.
3. **The skill** (`~/.claude/skills/pegasus-data`) points at `manual/INDEX.md` and the rules (never hand-roll a reader,
   query through the library), nothing more. Its facts move to the manual, where they cannot drift.
4. **No MCP server now.** A harness agent already has the shell. An MCP wrapper becomes worth it only for an agent
   without one (a chat client), and then it is a thin layer over these same commands.

## Units

| Unit | Done when |
|---|---|
| M1 manual generator from the compendium, rebuilt with the map | `manual/` exists in the home; `INDEX.md` is under 2k tokens; every dataset, column, link and product has a page; the map's latency does not grow by more than its write time |
| M2 `info` tiers (`info` = index, `info --all` = today's overview) | an agent's first read is under 2k tokens; nothing the overview says is lost |
| M3 the skill points at the manual | the skill holds no fact the manual holds |
| M4 live check: a fresh agent answers five real questions from the manual alone (thrombectomy codes by year, SIH–SIM linked mortality, tract income, CNES months held, TISS) | each answer is right and cites its page; tokens read are recorded |

Map latency (OQ #100) comes first: a manual rebuilt with a 6-minute map is rebuilt rarely.
