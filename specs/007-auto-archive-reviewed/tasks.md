---
description: "Task list for auto-archive reviewed requests"
---

# Tasks: Auto-Archive Reviewed Requests

**Input**: Design documents from `specs/007-auto-archive-reviewed/`

**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories)

**Tests**: Tests are part of the project's definition of done (Constitution
Principle V), so each story starts with a failing test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to (US1, US2)

## Path Conventions

Single project — modules at the repository root, tests under `tests/`.

---

## Phase 1: Setup

- [x] T001 Create the feature branch `007-auto-archive-reviewed` and the
  `specs/007-auto-archive-reviewed/` documents.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: storage helpers both stories and the sync use.

- [x] T002 Add `existing_pr_states()` (PR id → stored `state`) to `storage.py`.
- [x] T003 Add `archive_review(pr_id)` to `storage.py`: insert into
  `dismissed_reviews` only when the request has a review; return whether it
  archived.

**Checkpoint**: the storage surface exists; user stories can proceed.

---

## Phase 3: User Story 1 - Auto-archive requests that finish (Priority: P1) 🎯 MVP

**Goal**: A reviewed request that transitions open → closed/merged during any
sync leaves the AI Reviewed list, with its history intact.

**Independent Test**: Store an open reviewed request, sync with a fake provider
reporting it merged, and assert it is no longer in `storage.list_reviewed_prs()`.

### Tests for User Story 1

- [x] T004 [P] [US1] Create `tests/test_archive_reviewed.py` covering:
  `existing_pr_states`, `archive_review` (no review → False; with review →
  True and hidden), and the sync transition (open→merged archives,
  open→closed archives, already-closed is left alone, first sync archives
  nothing, review history survives).

### Implementation for User Story 1

- [x] T005 [US1] In `app.py:sync_repos`, capture the previous state from
  `storage.existing_pr_states()`, collect requests that go open →
  closed/merged, and call `storage.archive_review` for each.
- [x] T006 [US1] Report the archived count in the sync payload (`archived`).

**Checkpoint**: User Story 1 is testable on its own via the suite.

---

## Phase 4: User Story 2 - Confirm before removing a list item (Priority: P2)

**Goal**: Clicking × in the AI Reviewed list asks for confirmation first.

**Independent Test**: In the UI, click ×, cancel, and verify the entry stays and
no DELETE is issued.

- [x] T007 [US2] In `templates/index.html`, make `dismissReviewed` await
  `appConfirm` with a message naming the request, and return early on cancel.

**Checkpoint**: both stories work independently.

---

## Phase 5: Polish & Cross-Cutting

- [x] T008 [P] Update `README.md` (AI Reviewed notes, features) to describe
  auto-archive and the removal confirmation.
- [x] T009 [P] Update `specs/006-ai-reviewed-list/spec.md` (retrofitted baseline)
  to note the auto-archive behaviour and link to spec 007.
- [x] T010 [P] Add the feature to `specs/README.md` index.
- [x] T011 Run the full suite: `python3 -m unittest discover -s tests`.
- [x] T012 Set `spec.md` status to `Implemented` if the implementation matched
  the spec (update it if it diverged).

---

## Dependencies & Execution Order

- Setup → Foundational → User Stories → Polish.
- US1 depends on T002/T003; US2 is independent of the storage work.
- T011 depends on T004–T007.

### Within a story

- Tests before implementation.
- Storage before the sync that reads it.
