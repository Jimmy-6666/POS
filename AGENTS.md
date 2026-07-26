# Thai Minishop POS — AI Working Contract

This repository is maintained with AI assistance. Preserve accepted behavior and
make every change easy for a later session to understand.

## Required first read

At the start of a task, read only these files:

1. `AI_CONTEXT.md`
2. `PROJECT_MAP.md`
3. `FEATURE_STATUS.md`
4. `DECISIONS.md`
5. `CODING_RULES.md`
6. `DESIGN_RULES.md`

Do not scan the whole repository unless the user explicitly requests a full
audit. After the first read, name the additional files needed and why before
opening them. Ignore generated/runtime directories during normal discovery.

## Requirement protection

Never remove or reinterpret an accepted requirement silently. Use this source
order when information differs:

1. the user's current explicit instruction;
2. `REQUIREMENTS_V1.0.md` for the original accepted product contract;
3. `RELEASE_2.0.md`, `VERSION_2.1.md`, and `CHANGELOG.md` for accepted later
   additions and presentation changes;
4. tests and current code for implemented behavior;
5. compact context documents for navigation and summaries.

The compact documents do not replace the original requirement files. If a
requested change conflicts with an accepted business rule, identify the
conflict and obtain confirmation before changing it.

The complete process policy is retained in `AI_DEVELOPMENT_PROTOCOL.md`.

## Task workflow

1. Read the six context files.
2. Classify the task by feature area using `PROJECT_MAP.md`.
3. Open the smallest relevant scope packet: route/service, template/JS/CSS,
   schema only if data changes, and focused tests.
4. Before a feature change, state its location, affected modules/files,
   database and migration impact, and risks.
5. Make the minimum cohesive change. Do not refactor unrelated code.
6. Run focused tests, then the full suite when shared business logic, schema,
   authentication, sales, inventory, or reconciliation is affected.
7. Update only affected context/status/decision/database documents and
   `CHANGELOG.md`.
8. Report summary, modified files and reasons, documentation, future
   considerations, risks, and tests.

## Verification baseline

The last verified baseline is recorded in `FEATURE_STATUS.md`. Run the focused
tests for every change and the full suite for shared or release-critical work.
Never carry an old pass count forward without rerunning it.
