# Implementation Plan: Review Timer and Live Logs

**Branch**: `011-review-timer-and-logs` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/011-review-timer-and-logs/spec.md`

## Summary

Give a running review a visible clock and a live log. The agent is run through a
new streaming executor that reads stdout and stderr line by line and flushes the
combined stream into a new bounded `reviews.log` column while the run is in
progress; the request page's review panel shows a live timer driven from the
review's `created_at` and a "Logs" area fed by the existing two-second poll. No
change to how the final output and verdict are decided.

## Technical Context

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`; one additive
column on `reviews`.

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI

**Project Type**: Single-project web application

**Performance Goals**: Line-oriented reads; a log flush at most ~once a second
(not per line) so a chatty agent does not hammer SQLite. The existing poll is
unchanged.

**Constraints**: No new services or build step; no new settings; no new module.

**Scale/Scope**: One review at a time per request, a few repositories in parallel;
log capped at ~200 KB.

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | yes | Logs stay in `DATA_DIR`; they are token-redacted before being stored, and nothing is sent anywhere. |
| II. Provider-Agnostic | yes | Streaming is agent-side, not provider-side; no provider code touched. |
| III. Agent-Agnostic | yes | Streams any CLI's stdout/stderr; no agent-specific behaviour. |
| IV. No Surprise Actions | yes | Presentation of an already-requested review; nothing new is started. |
| V. Spec-First, Test-Supported | yes | Adds `tests/test_review_logs.py`; the spec ships with the code. |
| VI. Simple, Migratable Storage | yes | One additive `reviews.log` column via the existing self-healing migration; no backfill needed. |
| VII. Small Modules | yes | Streaming lives in `agents.py` (it owns process execution); logging/timer support stays in `reviewer.py` and the templates. |

No violations. *Complexity Tracking* is empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-review-timer-and-logs/
├── spec.md              # the feature specification
├── plan.md              # this file
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
agents.py              # run_streaming: Popen + reader threads + timeout kill
reviewer.py            # bounded, redacted log writer; use the streaming runner
storage.py             # reviews.log column, in REVIEW_FIELDS and _review_dict
templates/pr_detail.html  # live timer + Logs area + per-review elapsed in the sidebar
README.md              # document the timer and logs
specs/README.md        # add this feature to the index
tests/test_review_logs.py  # streaming, redaction, cap, storage and render tests
```

**Structure Decision**: `agents.py` already owns running a CLI, so the streaming
executor goes there; `reviewer.py` owns the review lifecycle and the log policy
(redaction, cap, flush cadence); `storage.py` owns the one additive column. This
mirrors the existing split and needs no new module.

## Design

- **Streaming executor (`agents.run_streaming`)**:
  - `subprocess.Popen` with separate stdout/stderr pipes, text mode, line
    buffering, the same hardened environment as `run`.
  - One reader thread per stream appends lines to its buffer and calls
    `on_output(stream_name, line)` (guarded by a lock).
  - The main thread waits with `timeout`; on `TimeoutExpired` it kills the
    process, waits for it, joins the readers and re-raises `TimeoutExpired`, so
    partial output stays available.
  - Returns a `subprocess.CompletedProcess` (stdout, stderr, returncode) so the
    existing decision logic is untouched. `agents.run` stays for completeness.
- **Log writer (`reviewer._ReviewLog`)**:
  - Holds the chunks in memory, capped at `MAX_LOG_CHARS` (drop oldest chunks),
    and flushes the joined, token-redacted text to `storage.update_review(...,
    log=...)` at most every `LOG_FLUSH_SECONDS` (plus a forced flush at the end).
  - Thread-safe, because two reader threads append concurrently.
  - The review's rendered command and short status notes (preparing, workspace
    ready, finished) are appended too, so the log reads as a transcript.
- **Reviewer (`_run_review`)**: build the log writer early; use `run_streaming`
  with `on_output` appending to it; keep `output = proc.stdout`, `error =
  redacted(proc.stderr)` and `parse_verdict(output)` exactly as today. The
  final `finish(...)` includes the full log.
- **Storage**: `reviews.log TEXT` in `SCHEMA` and `_EXTRA_REVIEW_COLUMNS`; `log`
  in `REVIEW_FIELDS`; `_review_dict` returns it. No backfill (`NULL` renders as
  an empty log).
- **Request page (`pr_detail.html`)**:
  - A `#reviewTimer` badge in the review panel header: while the run is
    queued/preparing/running, a one-second interval computes `now - created_at`;
    when finished it shows `finished_at - created_at` (falling back to
    `duration_ms`).
  - A `#reviewLog` `<pre>` with a show/hide toggle; `renderReview` writes
    `review.log` and follows the tail while running. Selecting a past review from
    **History** shows its retained log.
  - Each review row in the page sidebar shows an elapsed time, ticking for a
    running review and static once it has a duration.

## Complexity Tracking

> No constitution violations.

| Violation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| *(none)* | | |

## Risks & Rollback

- **Risks**: a reader thread that never reaches EOF (a child that re-parents its
  output) could stall a join; joins are bounded, the process is killed on
  timeout, and threads are daemons. Frequent storage writes are throttled, and
  the log is capped. Redaction covers the configured token for the request's
  provider.
- **Rollback**: revert the commit. The extra column is ignored by older code and
  no existing data is rewritten.
