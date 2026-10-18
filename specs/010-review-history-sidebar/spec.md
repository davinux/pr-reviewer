# Feature Specification: Review History in the Sidebar

**Feature Branch**: `010-review-history-sidebar`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "The user should be able to see all the reviews done
in a PR in the side bar, and see all the reviews results."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every review of a request on its page (Priority: P1)

A user opens a pull/merge request that has been reviewed several times. In the
request page's sidebar they see the whole review history at a glance: each run's
agent, model, when it ran, its status and, when it has one, its verdict. No
output is dumped into the sidebar — just the results.

**Why this priority**: This is the core request. The page currently hides earlier
runs behind a dropdown that shows one review's output at a time, so there is no
single place to see how many reviews exist and how each one turned out.

**Independent Test**: Open a request with several reviews and confirm the sidebar
lists every one of them with the correct status and verdict.

**Acceptance Scenarios**:

1. **Given** a request with three reviews (passed, failed, running), **When** its
   page is opened, **Then** the sidebar lists all three with their status and
   verdict.
2. **Given** a request with no reviews, **When** its page is opened, **Then** the
   sidebar shows an empty state.
3. **Given** a review that errored, **When** its request's page is shown, **Then**
   the review appears in the history with its failed status and no verdict.

---

### User Story 2 - Recent reviews across requests in the main sidebar (Priority: P2)

From the dashboard, a user sees the most recent reviews across every repository
in the main sidebar, newest first. Each entry names the request it belongs to and
shows its status and verdict, and links to that request.

**Why this priority**: Extends the at-a-glance view to the whole app, so a run
finishing in any repository is visible without opening that repository first.

**Independent Test**: Review requests in two repositories and confirm both
reviews appear in the dashboard sidebar, newest first, with correct labels.

**Acceptance Scenarios**:

1. **Given** reviews for requests in two repositories, **When** the dashboard is
   opened, **Then** the sidebar lists them newest first with repository, number,
   status and verdict.
2. **Given** an entry, **When** it is clicked, **Then** the request's page opens.
3. **Given** more reviews than the list shows, **When** the dashboard is opened,
   **Then** the newest are shown.

---

### User Story 3 - Live status without a reload (Priority: P3)

The two lists update on their own while a review is running, so a queued run
becomes running and then reviewed in place.

**Why this priority**: Reviews are slow; a list frozen at page load would be
misleading. The existing "AI Reviewed" list already refreshes; this keeps the
review lists consistent with it.

**Independent Test**: Start a review with the dashboard open and confirm its
entry changes state without reloading.

**Acceptance Scenarios**:

1. **Given** the dashboard open while a review runs, **When** the review
   finishes, **Then** its entry's status and verdict update without a reload.
2. **Given** the lists unchanged, **When** they are polled, **Then** they are not
   needlessly re-rendered.

### Edge Cases

- **A request with no reviews**: the page sidebar shows an empty state; the
  dashboard list is unaffected.
- **A review with no verdict yet** (queued, preparing, running or errored): the
  entry shows the status and omits the verdict.
- **A completed review with no machine-readable verdict**: it shows the
  `No verdict` label, matching the rest of the app.
- **A request removed from the "AI Reviewed" list**: its reviews remain in the
  review lists; dismissal hides the request from that one list only.
- **A very long history**: the request page lists every review; the dashboard
  list is bounded to the most recent reviews so it stays readable.
- **A request is deleted**: its reviews cascade away and leave both lists.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Storage MUST return **all** of a request's reviews, newest first,
  with no fixed cap.
- **FR-002**: Storage MUST return reviews across requests, newest first, joined
  with the owning request's identity (its id, number, title and repository), with
  a bounded window (a sensible default).
- **FR-003**: The request page MUST show all of its reviews in the page sidebar,
  each with its agent, model, status and verdict (when one exists).
- **FR-004**: The dashboard's main sidebar MUST show the most recent reviews
  across requests, each naming its repository and request number and linking to
  the request, with its status and verdict.
- **FR-005**: Status and verdict MUST be presented with the app's existing human
  labels (Queued, Preparing, Running, Reviewed, Failed; Passed, Needs work, No
  verdict).
- **FR-006**: The lists MUST include reviews that are still running and reviews
  that failed, not only completed ones.
- **FR-007**: The dashboard review list MUST refresh without a full page reload.
- **FR-008**: A JSON endpoint MUST expose the cross-request review list for the
  dashboard sidebar.
- **FR-009**: Sidebar entries MUST show results (status and verdict) only; the
  full review output stays in the existing review panel and its history selector.

### Key Entities

- **Review**: one agent run for a request — agent, model, status, verdict, and
  timing. A request has zero or more, newest last.
- **Request identity**: the fields the dashboard list needs to name and link a
  review's request — its id, number, title and repository slug/full name.

## Success Criteria *(mandatory)*

- **SC-001**: Opening a request with N reviews shows all N in the page sidebar.
- **SC-002**: The dashboard sidebar lists the newest reviews across requests with
  the correct status and verdict labels.
- **SC-003**: A review that finishes while a page is open updates its entry
  without a reload.
- **SC-004**: No sidebar entry exposes an agent's review output.

## Assumptions

- "Side bar" means the request page's right-hand metadata column and the
  dashboard's left sidebar; both show a per-review list.
- The dashboard list is global (all repositories) and shows a recent window
  (the newest 50) rather than every review ever run.
- Entries show a summary only; reading a review's output continues to use the
  request page's review panel and its history selector.
- Dismissal via the "AI Reviewed" list is scoped to that list; review history is
  kept and still appears in the review lists.
- Every stored review is part of the history, including failed and in-progress
  runs.
