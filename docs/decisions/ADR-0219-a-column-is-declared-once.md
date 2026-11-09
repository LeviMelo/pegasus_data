# ADR-0219: A column is declared once; linkage reads how it compares from the roles file

2026-11-09. Status: active. Amends ADR-0109 (where linkage roles are declared); closes defect 2 of the 2026-11-08
principles audit.

## Context

A column was declared up to three times. `curation/roles/<dataset>.yml` gave every column its role, kind and model
(11,003 columns). `curation/roles.yml` declared 108 linkage roles again, each naming a column, and 106 of them named
the role the roles file already gave that column (the other two: SINASC's `mother.birth_year` read from `DTNASCMAE`,
and TOXC's `patient.birth_date` fixed from `NU_IDADE_N`). The intake's per-column `role:` was a free-text description
under the name of the typed concept.

## Decision

- **Linkage compares what the roles file declares.** A compared column carries `compare:` (role -> type, format,
  categories, `also`), and the file carries `setting:`. `linkage.roles.load_roles` reads them; `roles.yml` is deleted,
  and its type documentation is now the module's docstring.
- **A role table's key** hashes the roles in name order, so where a role is declared does not change it.
- **The intake's `role:` is `description:`**, which is what it was (477 entries). It lands nothing again.

## Evidence

`load_roles()` before and after: the same 10 datasets, and every `Role` equal (column, type, format, categories,
`also`), settings equal. SIASUS-PS's record word is now its roles file's `care` (was `care_episode`). The intake's
served descriptions: 1,080 before and after.

## Consequences

Cached role tables are recomputed once: their key changed with the order rule and, for SIASUS-PS, the record word.
