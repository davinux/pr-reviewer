# Feature Specification: Auto-Archive Reviewed Requests

**Feature Branch**: `007-auto-archive-reviewed`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "When the PRs of a project are reloaded, auto
archive the ones in review when they are merged or closed. Also ask for
confirmation when the user deletes a review item from the sidebar."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Auto-archive requests that finish (Priority: P1)

A user tracks several reviews in the **AI Reviewed** sidebar list. A request they
reviewed is later merged (or closed) upstream. The next time the requests are
reloaded, that request leaves the list on its own, so the list only keeps work
that is genuinely still in flight.

**Why this priority**: The list exists to follow active work. Without automatic
cleanup the user has to clear finished requests by hand every time, which is the
main reason the list stops being useful.

**Independent Test**: Give a request a review, store it as open, reload while the
provider reports it merged, and confirm it is gone from the list while its review
history survives.

**Acceptance Scenarios**:

1. **Given** a request in the AI Reviewed list that is open, **When** a reload
   finds it merged, **Then** it is archived (hidden) from the list.
2. **Given** a request in the AI Reviewed list that is open, **When** a reload
   finds it closed, **Then** it is archived from the list.
3. **Given** a request that is archived, **When** its review history is read,
   **Then** every review is still there.
4. **Given** a request with no reviews, **When** it is merged or closed, **Then**
   nothing is archived for it (it was never in the list).
5. **Given** a request already closed or merged when it is first synced, **When**
   it is reloaded, **Then** it is not auto-archived because of a later sync.

---

### User Story 2 - Confirm before removing a list item (Priority: P2)

A user goes to remove an entry from the **AI Reviewed** sidebar list and is asked
to confirm first, so a stray click does not make the entry disappear.

**Why this priority**: Removal is easy to trigger by accident and an accidental
click is confusing; a confirmation is a small but meaningful guardrail.

**Independent Test**: Click the remove control on a list entry, confirm the
dialog appears, choose Cancel and verify the entry remains.

**Acceptance Scenarios**:

1. **Given** an entry in the list, **When** the user clicks its remove control,
   **Then** a confirmation dialog appears naming the request.
2. **Given** the confirmation dialog, **When** the user cancels, **Then** the
   entry stays in the list and nothing is sent to the server.
3. **Given** the confirmation dialog, **When** the user confirms, **Then** the
   entry is removed as before.

### Edge Cases

- A request whose review is still running when it is merged: it is archived when
  the reload sees the state change; the running review finishes and stays in the
  history.
- A request archived automatically, then explicitly re-reviewed: it returns to
  the list (starting a review already clears its archive).
- A request closed and reopened between reloads: it is open at reload time, so it
  is not archived.
- The very first sync of a repository (baseline): no previous state is known, so
  nothing is auto-archived.
- A provider error for one repository: that repository's requests are left as
  they are; no archiving happens for a failed fetch.
- Removing a repository or request still cascades to its archive record.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: During a reload of a project's requests, the system MUST archive a
  request that is tracked in the **AI Reviewed** list (has at least one review,
  is not already archived) when its state changes from open to closed or merged.
- **FR-002**: Archiving MUST hide the request from the list without deleting its
  review history, using the same mechanism as a manual removal.
- **FR-003**: The system MUST only auto-archive on the open → closed/merged
  transition. A request that is already closed or merged when the reload sees it
  MUST NOT be auto-archived, so a review started on an already-finished request
  is not immediately hidden.
- **FR-004**: Auto-archiving MUST apply to every reload: the on-demand **Sync
  PRs** action and the background watcher for watched repositories.
- **FR-005**: A request MUST NOT be archived more than once, and an archived
  request stays archived across further reloads until a new review is started.
- **FR-006**: Requests without any review MUST be unaffected (there is nothing in
  the list to archive).
- **FR-007**: The behavior MUST be provider-agnostic, covering GitHub pull
  requests and GitLab merge requests through their normalised states.
- **FR-008**: The user MUST be asked to confirm before a request is removed from
  the AI Reviewed sidebar list; cancelling MUST leave the request in the list and
  MUST NOT contact the server.
- **FR-009**: The confirmation MUST identify the request being removed
  (repository and number/title).
- **FR-010**: The confirmation MUST use the application's themed dialog with its
  existing fallback, not a browser-native prompt on the normal path.
- **FR-011**: Auto-archiving MUST require no new configuration; it is always
  active.

### Key Entities *(include when the feature involves data)*

- **AI Reviewed entry**: a request with at least one review; it is visible in the
  sidebar list unless it has been archived.
- **Archive (dismissal)**: the existing record that a request was cleared from
  the list; auto-archiving and manual removal write the same record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a reload in which an open, reviewed request is merged or
  closed, the request is absent from the AI Reviewed list on the next refresh.
- **SC-002**: None of that request's reviews are lost (the count is unchanged).
- **SC-003**: A reviewed request that is already closed/merged when first tracked
  remains visible after a reload (no spurious archive).
- **SC-004**: Clicking the remove control always shows a confirmation; choosing
  Cancel leaves the list unchanged and sends no request.
- **SC-005**: Reviewing an archived request brings it back to the list (existing
  behavior preserved).

## Assumptions

- "The PRs of a project are reloaded" means any sync — the **Sync PRs** button or
  the background watcher — not only a manual action.
- "Auto archive" and the existing manual removal are the same operation: hide the
  request from the list, keep its reviews.
- Auto-archiving is always on and has no setting; the archive remains reversible
  by starting a new review.
- Only a state *change* to closed/merged triggers archiving; a request that is
  simply finished is left for the user to clear.
- The existing confirmation dialog (`appConfirm`) is reused; no native
  `window.confirm` on the normal path.
