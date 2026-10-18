# Feature Specification: AI-Reviewed Tracking List

**Feature Branch**: `006-ai-reviewed-list`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "The sidebar tracks every reviewed pull/merge
request with its latest status, and you can clear the ones you are done with."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Track reviewed requests with live status (Priority: P1)

A user starts a review and the request appears in the **AI Reviewed** sidebar
list with a coloured status — **Queued**, **Preparing**, **Running**,
**Reviewed** or **Failed** — that updates on its own.

**Why this priority**: The list is the single place to follow review progress
without hunting for each request.

**Independent Test**: Start a review and watch the list entry advance from
queued to reviewed without reloading.

**Acceptance Scenarios**:

1. **Given** a request with no reviews, **When** a review is started, **Then**
   the request appears in the list immediately as **Queued**.
2. **Given** a running review, **When** the list refreshes, **Then** the entry
   shows the current status.
3. **Given** a completed review, **When** the list refreshes, **Then** the entry
   shows **Reviewed**.
4. **Given** a failed review, **When** the list refreshes, **Then** the entry
   shows **Failed**.

---

### User Story 2 - Clear entries you are done with (Priority: P2)

A user removes an entry from the list once finished with it, without deleting the
review.

**Why this priority**: Keeps the list actionable, but the list is useful before
any clearing.

**Independent Test**: Dismiss an entry and confirm it disappears and its review
history survives.

**Acceptance Scenarios**:

1. **Given** an entry, **When** the user removes it, **Then** it disappears from
   the list.
2. **Given** a dismissed request, **When** a new review is started for it,
   **Then** it reappears in the list.
3. **Given** a dismissed request, **When** its review history is read, **Then**
   the reviews are still there.

### Edge Cases

- Requests reviewed before the list existed show up automatically.
- Removing a repository, or deleting a request, removes its list entries.
- The list is bounded, newest first.
- An unknown status falls back to a sensible label.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Membership of the list MUST be derived from the review history, so
  existing reviews appear without extra bookkeeping.
- **FR-002**: Each entry MUST show the request's latest review status, mapped to
  a human label (**Queued**, **Preparing**, **Running**, **Reviewed**,
  **Failed**).
- **FR-003**: The list MUST refresh on its own (the UI polls it) so status
  changes appear without a manual reload.
- **FR-004**: A user MUST be able to remove an entry, which hides it without
  deleting the review.
- **FR-005**: Starting a review for a dismissed request MUST make it visible
  again.
- **FR-006**: Removing a repository or request MUST cascade to its list
  membership.

### Key Entities

- **Reviewed entry**: a request with at least one review, plus its latest status
  and agent/model.
- **Dismissal**: a record that a request was cleared from the list; separate from
  the reviews themselves.

## Success Criteria *(mandatory)*

- **SC-001**: A new review appears in the list within one refresh interval.
- **SC-002**: The status shown matches the latest review for that request.
- **SC-003**: Dismissing hides the entry but preserves the review history.
- **SC-004**: A request reviewed before the feature existed is still listed.

## Assumptions

- "Latest review" means the most recent row for the request.
- The UI polls the list, so near-real-time is enough; no push channel is needed.

## Implementation Notes

- **Modules**: `storage.py` (`list_reviewed_prs` — latest review per request via
  a `MAX(id)` join, `dismiss_review`, `dismissed_reviews` table, cascade),
  `app.py` (`REVIEW_STATUS_LABELS`, `reviewed_prs_payload`, `/api/reviewed`,
  `DELETE /api/reviewed/<id>`), `templates/index.html` (sidebar list, 15s
  refresh, pulsing running state).
- **Tests**: exercised indirectly through the review lifecycle in
  `tests/test_auto_review.py`.
- **Known limitations**: the list is a fixed-size, newest-first window of
  reviewed requests.
