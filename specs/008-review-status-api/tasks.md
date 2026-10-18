---
description: "Task list for the review status API and Swagger docs"
---

# Tasks: Review Status API & Swagger Docs

**Input**: Design documents from `specs/008-review-status-api/`

**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories)

**Tests**: Tests are part of the project's definition of done (Constitution
Principle V), so each story starts with a failing test in `tests/test_api.py`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to (US1–US4)

## Path Conventions

Single project — modules at the repository root, tests under `tests/`.

---

## Phase 1: Setup

- [x] T001 Create the feature branch `008-review-status-api` and the
  `specs/008-review-status-api/` documents.
- [x] T002 Add `flask-swagger-ui` to `requirements.txt` and install it.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the verdict pipeline and storage helpers every story reads.

- [x] T003 In `storage.py`, add the `verdict` column to `SCHEMA`, add
  `_EXTRA_REVIEW_COLUMNS = {"verdict": "TEXT"}`, apply it in `init_db` via
  `_ensure_columns`, and include `verdict` in `REVIEW_FIELDS` and
  `_review_dict`.
- [x] T004 In `storage.py`, add `get_pr_by_number(slug, number)`,
  `latest_review(pr_id)`, `count_reviews(pr_id)` and
  `list_review_statuses(repo=None, verdict=None, limit=50)`; add `verdict` to the
  `list_reviewed_prs` select.
- [x] T005 In `reviewer.py`, add `VERDICT_INSTRUCTION`, append it in
  `build_prompt`, add `parse_verdict(output)`, and store the parsed verdict (or
  `unknown`) on a successful run.
- [x] T006 In `storage.py`/`app.py`, add the `api_token` setting
  (`DEFAULT_SETTINGS` + `TEXT_SETTINGS`) and mask it in `settings_payload`.

**Checkpoint**: verdicts are produced, stored and settings-ready.

---

## Phase 3: User Story 1 - Ask whether a request passed (Priority: P1) 🎯 MVP

**Goal**: `GET /api/v1/reviews/status` answers by slug+number or `pr_id`.

**Independent Test**: store a request, attach reviews with PASS/FAIL/no-marker
verdicts, and assert `passed`/`verdict` and the 400/404 cases.

### Tests for User Story 1

- [x] T007 [P] [US1] `tests/test_api.py`: `parse_verdict` (PASS/FAIL/last-wins/
  Markdown-tolerant/absent) and the status endpoint (passed true/false/null,
  running review, no review, latest wins, 404 unknown, 400 missing params).

### Implementation for User Story 1

- [x] T008 [US1] Create `api.py` with the `/api/v1` blueprint and
  `_result(pr)` building the FR-004 shape; add `GET /api/v1/reviews/status`.
- [x] T009 [US1] Register the blueprint from `app.py` (`api.register(app)`).
- [x] T010 [US1] Surface the verdict in the UI: verdict indicator in the AI
  Reviewed list (`templates/index.html`), `/api/reviewed` payload, and a badge on
  `templates/pr_detail.html`.

**Checkpoint**: the status endpoint works and is testable on its own.

---

## Phase 4: User Story 2 - Swagger UI (Priority: P1)

**Goal**: `/api/docs` shows and executes the API; `/api/v1/openapi.json` serves
the spec.

**Independent Test**: fetch `/api/docs` and `/api/v1/openapi.json` and assert the
200s plus the described paths.

- [x] T011 [US2] Write `openapi.json` describing `/api/v1/reviews/status`,
  `/api/v1/reviews` and the optional bearer auth.
- [x] T012 [US2] In `api.py`, serve `openapi.json` at `/api/v1/openapi.json` and
  register the Swagger UI blueprint at `/api/docs`.
- [x] T013 [P] [US2] Test the docs and spec endpoints in `tests/test_api.py`.

**Checkpoint**: the API is browsable and try-able.

---

## Phase 5: User Story 3 - Optional token (Priority: P2)

**Goal**: when `api_token` is set, data endpoints require it; the docs stay open.

**Independent Test**: set/clear the token and assert 401/200 and the bearer and
`X-API-Token` headers.

- [x] T014 [US3] Add `require_token` to `api.py` and apply it to the data
  endpoints (docs/spec exempt).
- [x] T015 [US3] Add the API token field to the Settings → Server tab in
  `templates/index.html`.
- [x] T016 [P] [US3] Test auth in `tests/test_api.py` (no token open; token set →
  401 without, 200 with either header; wrong token → 401; docs reachable).

**Checkpoint**: US1–US3 work independently.

---

## Phase 6: User Story 4 - List endpoint (Priority: P3)

**Goal**: `GET /api/v1/reviews` lists results, filterable by repo and verdict.

**Independent Test**: store several reviewed requests and assert the filters.

- [x] T017 [US4] Add `GET /api/v1/reviews` to `api.py` on top of
  `storage.list_review_statuses`.
- [x] T018 [P] [US4] Test the list endpoint and its filters in
  `tests/test_api.py`.

**Checkpoint**: all four stories work.

---

## Phase 7: Polish & Cross-Cutting

- [x] T019 [P] Update `README.md` (features, settings reference, API reference,
  Swagger link, data-storage table).
- [x] T020 [P] Update `specs/README.md` index and cross-link spec 006's
  Implementation Notes.
- [x] T021 Run the full suite: `python3 -m unittest discover -s tests`.
- [x] T022 Set `spec.md` status to `Implemented` (or update it if the
  implementation diverged).

---

## Dependencies & Execution Order

- Setup → Foundational → User Stories → Polish.
- US1 depends on T003–T006; US2 depends only on T008; US3 depends on T014 (and
  T006 for the key); US4 depends on T004/T008.
- T021 depends on T007–T018.

### Within a story

- Tests before implementation.
- Storage before the endpoints that read it.
