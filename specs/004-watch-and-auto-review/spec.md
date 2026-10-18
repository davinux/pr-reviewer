# Feature Specification: Watch and Automatic Review

**Feature Branch**: `004-watch-and-auto-review`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Optionally watch individual repositories; new
pull/merge requests show a notification, play a short sound, and are reviewed
automatically."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Watch a repository for new requests (Priority: P1)

A user clicks the bell next to a repository. From then on, the app re-checks
that repository every *Watch interval*, and when a new open request appears, the
dashboard shows a toast linking to it and plays a short chime.

**Why this priority**: This is the core value — noticing new work without
polling by hand.

**Independent Test**: Watch a repository, introduce a new open request, and
confirm a notification appears and links to it.

**Acceptance Scenarios**:

1. **Given** a watched repository, **When** a new open request appears, **Then**
   a notification is stored and surfaced to the dashboard.
2. **Given** an unwatched repository, **When** a new request appears, **Then**
   nothing is announced.
3. **Given** a notification shown once, **When** it is marked seen, **Then** it
   is not shown again.
4. **Given** watching is off by default, **When** a repository is added, **Then**
   it is not watched until the bell is clicked.

---

### User Story 2 - Automatic review of new open requests (Priority: P2)

When watching is on, a new **open** request is reviewed automatically, using the
repository's own settings or the global ones.

**Why this priority**: Turns a notification into something actionable, but the
notification alone is already useful.

**Independent Test**: Watch a repository, add a new open request, and confirm a
review is queued with the expected agent and model.

**Acceptance Scenarios**:

1. **Given** a watched repository and an installed agent, **When** a new open
   request appears, **Then** a review is queued for it.
2. **Given** a repository that overrides agent and model, **When** a new request
   appears, **Then** the override is used.
3. **Given** no runnable agent, **When** a new request appears, **Then** it is
   announced but not reviewed.
4. **Given** a new request that is closed or merged, **When** it appears,
   **Then** it is stored but neither announced nor reviewed.

---

### User Story 3 - Baseline and safe concurrency (Priority: P3)

A repository's first sync establishes a baseline without flooding the user, and
reviews in the same repository never check out on top of each other.

**Why this priority**: Prevents the feature from being unusable or unsafe the
first time it is switched on.

**Independent Test**: Enable watching on a repository with existing requests and
confirm none are announced or reviewed; queue several reviews for one repository
and confirm they run one at a time.

**Acceptance Scenarios**:

1. **Given** a repository being synced for the first time, **When** its history
   is fetched, **Then** requests are stored without notifying or reviewing.
2. **Given** two new requests in one repository, **When** both are reviewed,
   **Then** they run one at a time in the shared workspace.
3. **Given** a request already under review, **When** an auto-review is
   triggered for it, **Then** the duplicate is skipped.

### Edge Cases

- The watcher never polls faster than the minimum interval, whatever the setting
  says.
- A background sync that fails does not stop the loop.
- Manual sync and the background watcher never fetch the same providers at once.
- Detailed and repeated failures are logged, not raised into the watcher thread.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Watching MUST be per repository, off by default, and toggled from
  the sidebar.
- **FR-002**: While running, the app MUST re-check watched repositories every
  *Watch interval* seconds, never faster than a fixed minimum.
- **FR-003**: A new **open** request in a watched repository MUST create a
  notification; closed and merged requests MUST NOT.
- **FR-004**: The first sync of a repository MUST be a silent baseline.
- **FR-005**: A new open request in a watched repository MUST start a review
  using the repository's effective settings when an agent can run.
- **FR-006**: No review MUST be queued when no agent can run, and a request
  already being reviewed MUST be skipped.
- **FR-007**: Notifications MUST be readable (all or unseen only) and markable
  as seen (specific ids or all).
- **FR-008**: Syncs MUST be serialised so the watcher and a manual sync cannot
  overlap, and reviews sharing one repository workspace MUST be serialised.
- **FR-009**: The watch interval MUST default to 60 seconds and be floored at
  15.

### Key Entities

- **Watch flag**: a per-repository boolean; the sole opt-in for automatic work.
- **Notification**: a record of a new request in a watched repository —
  repository, number, title, URL, seen flag.
- **Watch interval**: the number of seconds between background checks.

## Success Criteria *(mandatory)*

- **SC-001**: Enabling watching on a repository with history announces nothing.
- **SC-002**: A new open request in a watched repository produces exactly one
  notification and one review.
- **SC-003**: No review is ever queued for a repository with no runnable agent.
- **SC-004**: Watched repositories are the only ones the background loop touches.

## Assumptions

- Automatic reviews need an agent that can actually run; the configured agent, or
  the first installed one.
- The notification chime requires a user interaction with the page first
  (a browser autoplay rule), which is expected and acceptable.
- Only open requests are news; a first fetch surfaces closed and merged history
  that is not.

## Implementation Notes

- **Modules**: `app.py` (`sync_repos`, `start_auto_reviews`,
  `auto_review_agent`, `_watch_interval`, `_watch_loop`, `start_watcher`,
  `WATCH_MIN_INTERVAL`, `POST /api/repos/<slug>/watch`,
  `/api/notifications`, `/api/notifications/seen`, `bootstrap`),
  `storage.py` (`set_repo_watch`, `add_notification`, `list_notifications`,
  `mark_notifications_seen`, `NOTIFICATION_LIMIT`), `reviewer.py`
  (`_workspace_lock`), `templates/index.html` (bell, toast, chime).
- **Tests**: `tests/test_auto_review.py` — which requests trigger a review, the
  baseline rule, agent selection, skipped reviews with no agent, per-repository
  overrides and the per-slug workspace lock.
- **Known limitations**: the watcher is in-process, so it only polls while the
  app is running; there is no push/webhook path.
- **Extended by** [009-re-review-on-new-commits](../009-re-review-on-new-commits/spec.md):
  watching also re-reviews a request that was already reviewed and whose head
  gained commits since the latest review.
