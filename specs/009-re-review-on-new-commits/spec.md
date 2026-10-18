# Feature Specification: Re-review Watched Requests on New Commits

**Feature Branch**: `009-re-review-on-new-commits`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "When refreshing the PRs, if a PR has the watching
icon and there are new commits from the latest review, launch another review
automatically."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Re-review when a watched request gets new commits (Priority: P1)

A user watches a repository (the 🔔 bell) and reviews one of its open requests.
The author pushes more commits. On the next sync — the manual **Sync PRs**
button or the background watcher — the app notices the request's head has moved
past the commit it last reviewed and starts a fresh review on its own.

**Why this priority**: This is the whole feature. A review of an outdated head
gives false confidence; re-reviewing automatically keeps the tracking list
honest without the user noticing and re-clicking each time.

**Independent Test**: Watch a repository, review an open request, then sync it
again with a new head commit and confirm exactly one new review is started.

**Acceptance Scenarios**:

1. **Given** a watched repository and a previously reviewed open request,
   **When** a sync sees the request's head commit changed, **Then** a new review
   is started automatically for it.
2. **Given** the same request with the head commit unchanged, **When** a sync
   runs, **Then** no new review is started.
3. **Given** the re-review is started, **When** the sync completes, **Then** the
   request is **not** announced as a new request (no notification, no chime).

---

### User Story 2 - Conservative triggering (Priority: P2)

Automatic re-reviews happen only where the user has opted in and where the app
can be sure the commits are new: the repository is watched, the request is open,
it has a previous review with a known head commit, and no review is already
running for it.

**Why this priority**: Protects the "no surprise actions" promise — a wrong
trigger would clone and run an agent (real cost) without the user asking.

**Independent Test**: Exercise each blocking condition (unwatched, closed, no
previous review, unknown prior head, review in progress) and confirm the sync
starts no re-review.

**Acceptance Scenarios**:

1. **Given** an **unwatched** repository, **When** a reviewed request gets new
   commits, **Then** no review is started.
2. **Given** a **closed or merged** request, **When** its head changes, **Then**
   no review is started.
3. **Given** a request with **no previous review**, **When** its head changes,
   **Then** nothing new is started (the existing new-request rule still applies).
4. **Given** a previous review that recorded **no head commit** (a review that
   predates this feature), **When** its request's head is checked, **Then** no
   re-review is started.
5. **Given** a review already running for the request, **When** a sync triggers a
   re-review, **Then** the duplicate is skipped.
6. **Given** a repository's own agent/model overrides, **When** a re-review
   starts, **Then** the overrides are used, exactly as for a new request.

---

### User Story 3 - See which requests will be kept current (Priority: P3)

A user can tell, from the request list itself, that a request's repository is
watched, so the automatic re-review behaviour is discoverable rather than
hidden.

**Why this priority**: A convenience and trust affordance on top of the working
behaviour; the feature is useful without it.

**Independent Test**: Watch a repository and confirm its requests carry the
watch indicator in the list; unwatch and confirm it disappears.

**Acceptance Scenarios**:

1. **Given** a watched repository, **When** its request list is shown, **Then**
   each request shows the watch indicator.
2. **Given** an unwatched repository, **When** its request list is shown,
   **Then** no watch indicator is shown.

### Edge Cases

- **Force-push / rewritten history**: the head commit is a different SHA, so a
  re-review is triggered the same as an added commit.
- **New commits while a review runs**: the running review holds the request, so
  the re-review is skipped; once it finishes, the next sync still sees the head
  ahead and re-reviews then.
- **A prior review that failed or errored**: it recorded the head it ran
  against, so there is no automatic retry until the head advances again.
- **A provider that supplies no head commit**: the request is never re-reviewed
  (no false positives from missing data).
- **First sync of a repository**: still a silent baseline; nothing is re-reviewed
  because nothing was known before.
- **Interval between syncs**: several commits pushed between two syncs produce a
  single re-review of the latest head, not one per commit.
- **Provider head vs checked-out head**: a review records the commit it actually
  checked out, and the provider reports the same commit (GitHub `pull.head.sha`,
  GitLab `sha` — the source-branch tip `refs/merge-requests/<iid>/head` resolves
  to), so the baseline converges after one re-review and later syncs stop
  triggering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each provider MUST expose the request's current head commit
  identifier, and storage MUST keep it on the stored request.
- **FR-002**: A review MUST record the head commit it was started against.
- **FR-003**: On a sync, the system MUST start a new review for an **open**
  request in a **watched** repository when the request's current head differs
  from the head recorded by the request's **latest** review.
- **FR-004**: The system MUST NOT start a re-review when any of these hold: the
  repository is unwatched; the request is closed or merged; the request has no
  prior review; the latest review has no recorded head; the head is unchanged;
  or a review is already running for the request.
- **FR-005**: A re-review MUST NOT create a notification and MUST NOT be counted
  or displayed as a new request.
- **FR-006**: A re-review MUST use the repository's effective settings (its own
  overrides, or the global ones) and the same agent-selection rules as other
  automatic reviews.
- **FR-007**: A request whose repository is watched MUST show a watch indicator
  in the request list; an unwatched request MUST NOT.
- **FR-008**: The sync summary MUST report the number of automatically started
  reviews — new requests and re-reviews together — under `auto_reviewed`.
- **FR-009**: Head-commit comparison MUST be exact: differing, non-empty values
  compare as new; equal, empty or missing values never trigger.

### Key Entities

- **Head commit**: the request's current top commit, supplied by the provider and
  stored on the request.
- **Recorded review head**: the head commit a review was started against, stored
  with the review so later syncs can tell whether the request moved on.
- **Watch flag**: the existing per-repository opt-in (the 🔔 bell) that gates all
  automatic work.

## Success Criteria *(mandatory)*

- **SC-001**: For a watched, previously reviewed open request, a new commit
  produces exactly one additional review on the next sync.
- **SC-002**: Syncs with no head change never start additional reviews.
- **SC-003**: After upgrading, reviews that predate this feature trigger zero
  re-reviews until the user reviews again.
- **SC-004**: An unwatched or finished request with new commits triggers zero
  re-reviews.

## Assumptions

- Watching stays **per repository**, toggled by the existing sidebar bell; "a PR
  has the watching icon" means its repository is watched.
- "New commits" are detected by comparing head commit identifiers, not by the
  request's `updated_at` (which also moves for comments and labels).
- Only requests that already have a review are re-reviewed; a request with no
  review is the existing new-request auto-review's job.
- The re-review uses the latest review's recorded head as its baseline, so a
  request reviewed again by hand adopts the new head.
- Existing reviews without a recorded head are treated as "no baseline": the app
  never guesses, so the upgrade surprises no one.
