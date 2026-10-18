---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `specs/[###-feature-name]/`

**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories)

**Tests**: Tests are part of the project's definition of done (Constitution
Principle V). Include test tasks unless a task explicitly notes why no test is
possible.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to (e.g. US1, US2)
- Include exact file paths in descriptions.

## Path Conventions

Single project — modules at the repository root, tests under `tests/`.

<!--
  Replace every task below with the real ones derived from spec.md and plan.md.
  Group tasks by user story so each story can be implemented, tested and
  delivered on its own.
-->

## Phase 1: Setup

**Purpose**: Anything needed before the feature work starts.

- [ ] T001 [e.g. "Add settings keys to DEFAULT_SETTINGS in storage.py"]

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Shared infrastructure every user story depends on.

**⚠️ CRITICAL**: no user story work starts until this phase is complete.

- [ ] T002 [e.g. "Add the column to SCHEMA and _EXTRA_* in storage.py"]

**Checkpoint**: foundation ready — user stories can now proceed.

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [What this story delivers.]

**Independent Test**: [How to verify it on its own.]

### Tests for User Story 1

> Write these first and confirm they fail before implementing.

- [ ] T003 [P] [US1] Add a test for [behaviour] in `tests/test_[name].py`

### Implementation for User Story 1

- [ ] T004 [US1] Implement [behaviour] in `[module].py`
- [ ] T005 [US1] Surface it in `[route/template]`

**Checkpoint**: User Story 1 works and is testable on its own.

---

## Phase 4: User Story 2 - [Title] (Priority: P2)

**Goal**: [What this story delivers.]

**Independent Test**: [How to verify it on its own.]

- [ ] T006 [P] [US2] Add a test for [behaviour] in `tests/test_[name].py`
- [ ] T007 [US2] Implement [behaviour] in `[module].py`

**Checkpoint**: User Stories 1 and 2 both work independently.

---

[Add more user-story phases as needed, following the same pattern.]

---

## Phase N: Polish & Cross-Cutting

- [ ] TXXX [P] Update `README.md` (features, settings, API reference)
- [ ] TXXX Run the full suite: `python3 -m unittest discover -s tests`
- [ ] TXXX Update this feature's `spec.md` if the implementation diverged

---

## Dependencies & Execution Order

- **Setup** before everything.
- **Foundational** before any user story; it blocks all of them.
- **User stories** depend on Foundational, then run in parallel or in priority
  order (P1 → P2 → P3).
- **Polish** depends on the stories it touches.

### Within a story

- Tests before implementation.
- Storage/schema before the code that reads it.
- Core behaviour before the UI that surfaces it.

## Notes

- `[P]` marks tasks on different files with no dependencies.
- Keep each task small enough to finish and commit on its own.
- Stop at a checkpoint to validate the story independently before moving on.
- Avoid vague tasks and cross-story dependencies that break independence.
