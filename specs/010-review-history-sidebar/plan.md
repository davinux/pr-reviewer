# Implementation Plan: Review History in the Sidebar

**Branch**: `010-review-history-sidebar` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-review-history-sidebar/spec.md`

## Summary

Surface every review a request has, and its result, in the sidebars. Storage
gains an uncapped per-request review list and a cross-request "recent reviews"
list that carries the owning request's identity; `app.py` labels each review's
status and verdict and exposes the cross-request list over a small JSON
endpoint; the request page's right-hand sidebar and the dashboard's left sidebar
render the lists, the dashboard one refreshing by polling. No provider or agent
code changes, and no schema change — the `reviews` table already holds
everything needed.

## Technical Context

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`; the existing
`reviews` table is reused unchanged.

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI

**Project Type**: Single-project web application

**Performance Goals**: Two indexed reads (`reviews` by `pr_id`; the newest `N`
reviews joined to requests). No provider calls. The dashboard list polls the
same lightweight endpoint the existing sidebar already polls, on the same
interval.

**Constraints**: No new services, no build step, no new settings, no schema
change.

**Scale/Scope**: Tens of repositories, hundreds of requests; a handful of
reviews per request.

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | yes | Reads existing local rows only; no new outbound call and no new stored data. |
| II. Provider-Agnostic | yes | Reviews are stored provider-neutrally; the lists read storage, never a host. |
| III. Agent-Agnostic | yes | Only reads a review's recorded agent/model strings; no agent code touched. |
| IV. No Surprise Actions | yes | Read-only lists; nothing is started, cloned or posted. |
| V. Spec-First, Test-Supported | yes | Adds `tests/test_review_history.py`; the spec ships with the code. |
| VI. Simple, Migratable Storage | yes | No schema change; the existing `reviews` table and `idx_reviews_pr` index are reused. |
| VII. Small Modules | yes | Helpers stay in `storage.py` (data) and `app.py` (labels, route); no new module. |

No violations. *Complexity Tracking* is empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-review-history-sidebar/
├── spec.md              # the feature specification
├── plan.md              # this file
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
storage.py             # uncapped list_reviews; new list_recent_reviews
app.py                 # verdict/status labelling; GET /api/reviews; template data
templates/index.html   # "Reviews" section in the main sidebar + polling
templates/pr_detail.html  # "Reviews" panel in the request page sidebar
README.md              # document the review lists
specs/README.md        # add this feature to the index
tests/test_review_history.py  # storage, payload, endpoint and render tests
```

**Structure Decision**: The concern already has a home in each module:
`storage.py` owns reading reviews, `app.py` owns the display labels and the
route that feeds the dashboard list, and the two templates own presentation.
This mirrors how the "AI Reviewed" list (spec 006) is split, so no new module is
needed.

## Design

- **Storage**:
  - `list_reviews(pr_id, limit=None)` — drop the fixed 20 cap by defaulting to no
    limit, so the request page can show every review. Ordering (newest first) is
    unchanged.
  - `list_recent_reviews(limit=50)` — new: the newest reviews across all requests,
    joined to `pull_requests` for the request identity (`pr_number`, `pr_title`,
    `pr_full_name`, `pr_slug`). Built on `_review_dict` plus those extra keys, so
    its shape is a superset of a review's.
- **App**:
  - Extract the status/verdict labelling already used by
    `reviewed_prs_payload` into `_label_review(item)`; reuse it in a new
    `review_history_payload(items)`.
  - `index` passes `recent_reviews=review_history_payload(storage.list_recent_reviews())`.
  - `pr_detail` passes `reviews=review_history_payload(storage.list_reviews(pr["id"]))`,
    keeping the `r.agent`/`r.model`/`r.status` fields the history selector reads.
  - New `GET /api/reviews` returns `{"reviews": review_history_payload(...)}` for
    the dashboard sidebar poll. It is distinct from the existing
    `GET /api/reviews/<id>` and stays in the open (non-token) app UI, matching
    `/api/reviewed`.
- **Dashboard sidebar (`index.html`)**: a "Reviews" section under "AI Reviewed"
  renders `recent_reviews` with the existing `.reviewed-*` styles (status dot,
  title, sub-line of repo · status · verdict); an empty-state paragraph sits
  below. A poller (`refreshReviewHistory`) fetches `/api/reviews`, re-renders only
  when a signature of ids/statuses/verdicts changes, and updates the count badge.
- **Request page sidebar (`pr_detail.html`)**: a "Reviews" panel in the metadata
  column lists each review (#id, status badge, verdict badge, and a compact
  agent/model/time line). Small local CSS gives the badges the app's colours.
  With no reviews, it shows an empty state. The existing History selector is
  unchanged and remains the way to read a review's output.

## Complexity Tracking

> No constitution violations.

| Violation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| *(none)* | | |

## Risks & Rollback

- **Risks**: an uncapped per-request list could grow large for a heavily
  re-reviewed request; reviews per request are small in practice and the query is
  indexed by `pr_id`. The dashboard list is deliberately bounded. Polling the new
  endpoint reuses the existing sidebar cadence and only re-renders on change.
- **Rollback**: revert the commit. No stored data changes, so rollback is
  lossless.
