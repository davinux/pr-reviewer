# Tasks: Review Timer and Live Logs

**Feature**: `011-review-timer-and-logs` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Tasks are grouped by user story and ordered so each is independently testable.
`[P]` marks tasks that touch different files and can be done in parallel.

## Phase 1 — Setup

- [x] T001 Create branch `011-review-timer-and-logs` and write `spec.md`, `plan.md`, `tasks.md`.

## Phase 2 — Foundational (blocks every story)

- [x] T002 [P] In `storage.py`, add the `log` column to the `reviews` schema and to
      `_EXTRA_REVIEW_COLUMNS`, add `"log"` to `REVIEW_FIELDS`, and return it from
      `_review_dict`.
- [x] T003 [P] In `agents.py`, add `run_streaming(command, cwd, timeout, env,
      on_output)`: `Popen` with separate stdout/stderr pipes, one reader thread per
      stream calling `on_output(stream, line)`, a bounded join, and a
      `TimeoutExpired` after killing the process on timeout; returns a
      `subprocess.CompletedProcess` so the decision logic is unchanged.

## Phase 3 — User Story 1 (P1) — Live timer

- [x] T004 [US1] In `reviewer._run_review`, build a `_ReviewLog` early and append
      short status notes (preparing, workspace, running command, finished) so the
      run has a transcript from the moment it starts.
- [x] T005 [US1] In `templates/pr_detail.html`, add a `#reviewTimer` badge to the
      review panel header and tick it every second from `created_at` while the
      review is queued/preparing/running, freezing on
      `finished_at - created_at` (falling back to `duration_ms`) when done.
- [x] T006 [US1] Show a per-review elapsed time in the request-page sidebar and in
      the History entries, ticking while a review runs and static once it has a
      duration.
- [x] T007 [US1] Test: a running review renders the timer and elapsed elements; a
      finished review shows a fixed duration.

## Phase 4 — User Story 2 (P1) — Streaming logs

- [x] T008 [US2] In `reviewer._run_review`, run the agent through
      `agents.run_streaming` with `on_output` feeding the log (stderr lines
      prefixed), keeping `output = proc.stdout`, `error = redacted(proc.stderr)`
      and `parse_verdict(output)` exactly as before; include the full log in the
      final `finish(...)`.
- [x] T009 [US2] In `templates/pr_detail.html`, add a `#reviewLog` `<pre>` with a
      show/hide toggle, write `review.log` from `renderReview`, and follow the
      tail while running; keep it available for a past review chosen in History.
- [x] T010 [US2] Test: `agents.run_streaming` streams incrementally and returns the
      full output; `_run_review` stores a log containing the streamed output and
      keeps partial output on a timeout.

## Phase 5 — User Story 3 (P2) — Safe, bounded logs

- [x] T011 [US3] In `reviewer._ReviewLog`, redact the token on every flush and cap
      the retained log (drop the oldest chunks), flushing at most once a second
      plus a forced flush at the end.
- [x] T012 [US3] Test: a token in the streamed output is redacted from the stored
      log, and a log larger than the cap keeps the newest output.

## Phase 6 — Polish

- [x] T013 [P] Add `templates/pr_detail.html` styling for the timer badge and the
      log `<pre>` (monospace, scrollable, bounded height).
- [x] T014 [P] Document the timer and logs in `README.md` and add the feature to
      `specs/README.md`.
- [x] T015 Run the full suite (`python3 -m unittest discover -s tests`) and fix
      regressions (including the existing `tests/test_reviewer.py` stub moving to
      `run_streaming`).
- [x] T016 Commit on the branch and open a pull request.
