# Feature Specification: Review Timer and Live Logs

**Feature Branch**: `011-review-timer-and-logs`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "The review is running for 10 minutes. I need to have
a proper timer on the details to see how long is taking to run, and also I should
be able to see the logs while running."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A live timer while a review runs (Priority: P1)

A user starts a review that takes several minutes. On the request page a timer
ticks up from the moment the review was queued, so they can see how long it has
been running without guessing. When the review finishes, the timer stops at the
total duration.

**Why this priority**: The immediate ask: a long-running review with no visible
clock leaves the user unsure whether it is progressing or stuck.

**Independent Test**: Start a review whose agent sleeps for a few seconds and
confirm the timer counts up and then freezes on completion.

**Acceptance Scenarios**:

1. **Given** a review just queued, **When** the details page is open, **Then** a
   timer starts at `00:00` and increases every second without a reload.
2. **Given** a running review, **When** the page is reloaded mid-run, **Then**
   the timer resumes at the correct elapsed time.
3. **Given** a finished review, **When** its details are shown, **Then** the
   timer shows the total time the review took and stops.

---

### User Story 2 - Streaming logs while a review runs (Priority: P1)

The agent's output is visible as it is produced, so the user can watch progress
instead of staring at a static "Running…" label for ten minutes.

**Why this priority**: Equally requested and the reason a run "feels" stuck.

**Independent Test**: Run an agent that prints lines over a few seconds and
confirm the log grows live and the finished log is retained.

**Acceptance Scenarios**:

1. **Given** a running review that prints output, **When** the page polls,
   **Then** the new output appears in the logs area before the review finishes.
2. **Given** a review that fails or times out, **When** it ends, **Then** the
   output produced up to that point is still shown.
3. **Given** a completed review, **When** its details are shown later, **Then**
   its logs are still available.

---

### User Story 3 - Logs are safe and bounded (Priority: P2)

Logs never leak a provider token and cannot grow without limit, so a chatty or
misbehaving agent does not corrupt the database or expose a secret.

**Why this priority**: Required by the local-first, private-by-default principle;
the feature is otherwise complete without it.

**Independent Test**: Run a review with a token in the environment and verbose
output; confirm the token is absent from the stored log and the log is capped.

**Acceptance Scenarios**:

1. **Given** an agent whose output contains the configured token, **When** the
   log is stored, **Then** the token is redacted.
2. **Given** an agent that prints far more than the cap, **When** the log is
   stored, **Then** it is truncated (keeping the most recent output).

### Edge Cases

- **No output yet**: the timer runs and the logs area shows a placeholder.
- **Timeout**: the agent is killed; the log keeps everything printed until then
  and a note records the timeout.
- **Crash / non-zero exit**: partial output is kept, as for any completed run.
- **Very long output**: only a bounded tail is kept as the live log, but the
  final review output is stored in full, as before.
- **Review with no duration recorded** (predates the finish bookkeeping): the
  timer falls back to the record's timestamps.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every review MUST record the moment it was created; a finished
  review MUST keep its finish time and duration (already stored).
- **FR-002**: The request page MUST show a live timer for a review that is
  queued, preparing or running, starting from the review's creation time and
  updating at least once per second without a page reload.
- **FR-003**: When a review finishes, the timer MUST show the total duration and
  stop ticking.
- **FR-004**: The system MUST capture the agent's standard output and standard
  error incrementally, storing the combined stream as the review's log while the
  run is in progress.
- **FR-005**: The request page MUST show the review's log, updating while the run
  is in progress and following the newest output.
- **FR-006**: The log MUST remain available after the run finishes, including
  for a review selected from the request's history.
- **FR-007**: Provider tokens MUST be redacted from the stored log.
- **FR-008**: The stored log MUST be bounded; when it exceeds the cap, the oldest
  output is dropped and the newest kept.
- **FR-009**: The existing final review output, error and verdict behaviour MUST
  be unchanged; streaming MUST NOT alter the verdict parsing.

### Key Entities

- **Review log**: the combined stdout/stderr of an agent run, streamed as it is
  produced and kept (bounded) with the review.
- **Review timing**: the creation time (when queued), finish time and duration of
  a review, which drive the timer.

## Success Criteria *(mandatory)*

- **SC-001**: A running review shows an elapsed time that matches the wall clock
  within one second.
- **SC-002**: Output printed by an agent mid-run is visible on the request page
  before the review finishes.
- **SC-003**: A review that took N seconds shows a total of ~N seconds once done.
- **SC-004**: No stored log contains a configured provider token.

## Assumptions

- The timer measures from when the review was queued (the user's click), which is
  the number the user cares about; the finish duration remains the run duration.
- "Logs" means the agent's stdout and stderr; the app's own status transitions
  are already shown as the progress label.
- Logs are stored locally in the existing SQLite database, consistent with the
  rest of the review data.
- Streaming is line-oriented and flush-on-interval; sub-second latency is not
  required.
