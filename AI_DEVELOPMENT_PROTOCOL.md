# Master AI Development Protocol — Thai Minishop POS

This repository is developed primarily with AI. The goal is not merely to
write code: every session must leave the repository maintainable, documented,
easy for a future AI session to understand, and economical in context usage.

## General rules

- Think and understand the architecture before modifying files.
- Documentation is part of the deliverable and must not be left outdated.
- Start every session with only `AI_CONTEXT.md`, `PROJECT_MAP.md`,
  `FEATURE_STATUS.md`, `DECISIONS.md`, `CODING_RULES.md`, and
  `DESIGN_RULES.md`.
- Do not inspect the whole repository. If more context is needed, identify the
  exact files and why. Do not open unrelated modules.

## Product goals

The system is offline-first, Flask, SQLite, vanilla JavaScript, HTML, CSS,
Windows/LAN, Thai-first, touch-friendly, fast, simple, maintainable, deployable
without Docker/Node/React, and easy to move to another PC.

## Token-saving rules

- Minimize context and inspect only files related to the requested feature.
- Reuse existing code and components.
- Do not rewrite completed modules.
- Review the entire repository only when explicitly requested.

## New feature analysis

Before implementation, explain:

1. where the feature belongs;
2. affected modules;
3. files requiring modification;
4. whether the database changes;
5. whether a migration is required;
6. potential risks.

## Change rules

- Modify the minimum number of files.
- Avoid unrelated refactoring/formatting, renames, moves, or architecture
  changes.
- Never change business logic, completed workflows, or existing screen design
  unless requested.
- Never modify the schema unless required; never delete existing columns or
  tables; always preserve data and explain migrations.

## UI rules

Thai first, touch friendly, large controls, fast cashier workflow, no
unnecessary animations, desktop/tablet/mobile compatibility, and receipt
printer compatibility.

## Documentation rules

Keep `AI_CONTEXT.md`, `PROJECT_MAP.md`, `FEATURE_STATUS.md`,
`MODULE_DEPENDENCIES.md`, `DATABASE_OVERVIEW.md`, and `CHANGELOG.md` current,
updating only documents affected by the change. Correct outdated documentation
immediately; treat it as source code.

## Completion rules

Verify no broken routes, duplicated/dead code, outdated docs, broken
references, unnecessary files, or architecture violations. Split oversized
tasks into phases and seek confirmation before significant architecture
changes.

Final reports must contain: summary, modified files and reasons, documentation
updated, future considerations, risks, and testing performed.

Every session should leave the repository cleaner, better documented, easier
for future AI, more token efficient, and more maintainable without sacrificing
maintainability for short-term speed.
