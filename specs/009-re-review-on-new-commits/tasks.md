---
description: "Task list for re-reviewing watched requests on new commits"
---

# Tasks: Re-review Watched Requests on New Commits

**Input**: Design documents from `specs/009-re-review-on-new-commits/`

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

- [ ] T001 Create `specs/009-re-review-on-new-commits/` with `spec.md` and `plan.md` (done)

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The head-commit baseline every story depends on.

- [ ] T002 [P] Add `head_sha` to the provider request entry in `providers.py` (`_github_entry` from `pull.head.sha`, `_gitlab_entry` from `mr["sha"]`)
- [ ] T003 [P] Add `head_sha` columns in `storage.py`: `pull_requests` (SCHEMA + `_EXTRA_PR_COLUMNS`) and `reviews` (SCHEMA + `_EXTRA_REVIEW_COLUMNS`)
- [ ] T004 [US1] Persist and expose `head_sha` in `storage.save_pr`/`_pr_dict` and `storage.create_review`/`_review_dict`
- [ ] T005 [US1] Record the head a review starts against in `reviewer.start_review` (`create_review(..., head_sha=pr.get("head_sha"))`)

**Checkpoint**: a review now stores its baseline head; the sync can compare.

---

## Phase 3: User Story 1 - Re-review on new commits (Priority: P1) 🎯 MVP

**Goal**: A sync starts a fresh review when a watched, previously reviewed open
request's head moves on.

**Independent Test**: Watch a repo, review an open request, sync with a new head
SHA, and confirm exactly one review starts.

### Tests for User Story 1

- [ ] T006 [P] [US1] In `tests/test_auto_review.py`, add `head_sha` to the `_pr` helper and a helper that stores a request with a completed review at a given head
- [ ] T007 [US1] Test: new head triggers one re-review; unchanged head triggers none; the sync payload counts it in `auto_reviewed`; no notification is created

### Implementation for User Story 1

- [ ] T008 [US1] In `app.py:sync_repos`, for existing open requests in watched repos, compare the latest review's head with the entry's head and queue a re-review via `start_auto_reviews`

**Checkpoint**: User Story 1 works on its own.

---

## Phase 4: User Story 2 - Conservative triggering (Priority: P2)

**Goal**: No re-review when the user did not opt in or the change is uncertain.

**Independent Test**: Block each condition and confirm zero re-reviews.

- [ ] T009 [US2] Tests in `tests/test_auto_review.py`: unwatched repo, closed/merged request, no prior review, prior review with no head, and a request already under review all yield no re-review
- [ ] T010 [US2] Ensure the guards live in `app.py:sync_repos` (watch + open + prior review with head + running-review skip in `start_auto_reviews`)

**Checkpoint**: User Stories 1 and 2 both hold.

---

## Phase 5: User Story 3 - Watch indicator on request rows (Priority: P3)

**Goal**: The list shows which requests belong to a watched repository.

**Independent Test**: Watch a repo → its requests show 🔔; unwatch → they do not.

- [ ] T011 [US3] Pass `watched_slugs` to the template in `app.py:index`
- [ ] T012 [US3] Render the 🔔 on watched request rows in `templates/index.html`

**Checkpoint**: All three stories work.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T013 [P] Document re-review-on-new-commits in `README.md`
- [ ] T014 Update the spec index in `specs/README.md` and set the feature status to `Implemented`
- [ ] T015 Run the full suite: `python3 -m unittest discover -s tests`

---

## Dependencies & Execution Order

- **Foundational** (T002–T005) before any user story.
- **US1** (T006–T008) after Foundational; it is the MVP.
- **US2** (T009–T010) refines the US1 guards and can follow immediately.
- **US3** (T011–T012) is independent of the trigger and can run in parallel.
- **Polish** (T013–T015) last.

### Within a story

- Tests before implementation.
- Storage before the code that reads it (T003→T004→T008).

## Notes

- `[P]` marks tasks on different files with no dependencies.
- `storage.py` changes (T003, T004) touch the same file and run in order.
- Keep the trigger in `app.py`, matching the existing watch-and-auto-review split.
