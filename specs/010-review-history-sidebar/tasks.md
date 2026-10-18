---
description: "Task list for the review history sidebars"
---

# Tasks: Review History in the Sidebar

**Input**: Design documents from `specs/010-review-history-sidebar/`

**Prerequisites**: `plan.md`, `spec.md`

**Tests**: Part of the definition of done (Constitution Principle V). Test tasks
are included below.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to (e.g. US1, US2)
- Include exact file paths in descriptions.

## Path Conventions

Single project — modules at the repository root, tests under `tests/`.

## Phase 1: Setup

- [x] T001 Create `specs/010-review-history-sidebar/` with `spec.md` and `plan.md` (done)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The storage reads and the display labelling every story depends on.

- [x] T002 [P] In `storage.py`, default `list_reviews(pr_id, limit=None)` to no cap so all reviews are returned
- [x] T003 [P] In `storage.py`, add `list_recent_reviews(limit=50)` joining reviews to their request's identity
- [x] T004 In `app.py`, extract `_label_review(item)` and add `review_history_payload(items)` reusing the existing status/verdict labels

**Checkpoint**: storage can return both lists; the app can label them.

---

## Phase 3: User Story 1 - Every review of a request on its page (Priority: P1) 🎯 MVP

**Goal**: The request page's sidebar lists all of the request's reviews with
their status and verdict.

**Independent Test**: Open a request with several reviews and confirm the sidebar
lists every one with the correct labels.

### Tests for User Story 1

- [x] T005 [P] [US1] In `tests/test_review_history.py`, test that `list_reviews` returns more than the old 20-review cap, newest first
- [x] T006 [US1] Test that `GET /pr/<id>` renders every review in the sidebar and shows an empty state when there are none

### Implementation for User Story 1

- [x] T007 [US1] Pass labelled reviews to `pr_detail.html` in `app.py:pr_detail`
- [x] T008 [US1] Add the "Reviews" panel to `templates/pr_detail.html` with status/verdict badges and an empty state

**Checkpoint**: User Story 1 works on its own.

---

## Phase 4: User Story 2 - Recent reviews in the main sidebar (Priority: P2)

**Goal**: The dashboard sidebar lists the newest reviews across requests.

**Independent Test**: Review requests in two repositories and confirm both
appear, newest first, with correct labels and links.

### Tests for User Story 2

- [x] T009 [P] [US2] Test that `list_recent_reviews` returns reviews across requests newest first with the request identity and respects its limit
- [x] T010 [US2] Test that `GET /api/reviews` returns the labelled list and that `GET /` renders the sidebar section

### Implementation for User Story 2

- [x] T011 [US2] Add the `GET /api/reviews` endpoint in `app.py`
- [x] T012 [US2] Pass `recent_reviews` to `index.html` in `app.py:index`
- [x] T013 [US2] Add the "Reviews" section to `templates/index.html`

**Checkpoint**: User Stories 1 and 2 both work.

---

## Phase 5: User Story 3 - Live status without a reload (Priority: P3)

**Goal**: The dashboard list updates as reviews progress or finish.

**Independent Test**: Start a review with the dashboard open and confirm its
entry changes state without reloading.

- [x] T014 [US3] In `templates/index.html`, poll `/api/reviews`, re-render on change and update the count badge

**Checkpoint**: All three stories work.

---

## Phase 6: Polish & Cross-Cutting

- [x] T015 [P] Document the review lists in `README.md`
- [x] T016 Update the spec index in `specs/README.md` and set the feature status to `Implemented`
- [x] T017 Run the full suite: `python3 -m unittest discover -s tests`

---

## Dependencies & Execution Order

- **Foundational** (T002–T004) before any user story.
- **US1** (T005–T008) after Foundational; it is the MVP.
- **US2** (T009–T013) depends on T003/T004 and can follow immediately.
- **US3** (T014) depends on US2's endpoint and template section.
- **Polish** (T015–T017) last.

### Within a story

- Tests before implementation.
- Storage before the code that reads it (T003→T004→T011/T012).

## Notes

- `[P]` marks tasks on different files with no dependencies.
- `storage.py` changes (T002, T003) touch the same file and run in order.
- No schema change: the `reviews` table and `idx_reviews_pr` index already exist.
