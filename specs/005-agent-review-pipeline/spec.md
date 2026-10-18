# Feature Specification: Agent Review Pipeline

**Feature Branch**: `005-agent-review-pipeline`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Run a review from the request page; the app
prepares a checkout and captures the chosen agent's Markdown review, running in
the background with a live status."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a review with any installed agent (Priority: P1)

A user opens a request, chooses an agent (and optionally a model), clicks **Run
review**, and gets a Markdown review captured from the agent's output.

**Why this priority**: Producing a review is the reason the app exists.

**Independent Test**: On a request, run a review with each installed agent and
confirm output is captured and shown.

**Acceptance Scenarios**:

1. **Given** a request and an installed agent, **When** the user runs a review,
   **Then** a review row is created and run in the background.
2. **Given** no agent is chosen, **When** the user runs a review, **Then** the
   configured default, or the first installed agent, is used.
3. **Given** no installed agent, **When** the user runs a review, **Then** the
   app explains that none is available.
4. **Given** a successful run, **When** it finishes, **Then** the agent's
   Markdown output is stored and shown.

---

### User Story 2 - Background run with live status (Priority: P2)

The review runs without blocking the page, and the UI can follow its progress.

**Why this priority**: Reviews are slow (clone, checkout, model run); a blocking
request would be unusable.

**Independent Test**: Start a review and poll its status until it reaches
`done` or `error`.

**Acceptance Scenarios**:

1. **Given** a started review, **When** it is polled, **Then** its status moves
   through `pending`, `preparing`, `running` to `done` or `error`.
2. **Given** a review in progress, **When** another is started for the same
   request, **Then** the second is refused as a conflict.
3. **Given** a review that times out, **When** the timeout elapses, **Then** it
   ends as `error` with a clear message.
4. **Given** an agent that exits non-zero *after* emitting a verdict marker
   (for example a non-fatal tool failure), **When** the run finishes, **Then**
   the review is recorded as `done` with that verdict, not `error`.

---

### User Story 3 - Reproducible checkout and prompt (Priority: P3)

Each review checks out the request's head in a per-repository workspace and runs
the agent with a prompt describing the change.

**Why this priority**: Determines the review's quality, but the pipeline is
demonstrable without tuning it.

**Independent Test**: Run a review and inspect the stored workspace, command and
prompt; confirm the head ref was checked out and the prompt rendered.

**Acceptance Scenarios**:

1. **Given** a first review of a repository, **When** it runs, **Then** the
   repository is cloned into the workspace and the head ref is checked out.
2. **Given** a later review, **When** it runs, **Then** the workspace is fetched
   and updated rather than re-cloned.
3. **Given** a review, **When** it runs, **Then** the prompt is rendered from the
   configured template with the request's details.

### Edge Cases

- A very long prompt is truncated before it reaches the OS argument limit.
- A very long description is truncated inside the prompt; `0` means no limit.
- A token appearing in a git error or command line is redacted before it is
  stored or shown.
- The base branch fetch is best-effort; the head ref is what matters.
- Different repositories review in parallel; the same repository serialises.
- An agent may exit non-zero after printing its review (a non-fatal tool error);
  the trailing verdict marker decides that the review completed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST detect the supported agents on `PATH` and let the
  user pick one per review.
- **FR-002**: Agents MUST be driven by command templates with `{prompt}` and
  `{model}` placeholders and optional `[...]` groups; templates and binaries
  MUST be overridable, and a `custom` command MUST cover other CLIs.
- **FR-003**: `{prompt}` MUST be appended automatically when a template omits it.
- **FR-004**: A review MUST run in a background thread, recording status
  `pending` → `preparing` → `running` → `done`/`error`.
- **FR-005**: Starting a review for a request already being reviewed MUST fail
  with a conflict.
- **FR-006**: The system MUST clone the repository into `workspaces/<slug>` on
  first use and fetch on later runs, then check out the request's head ref
  (GitHub `refs/pull/<n>/head`, GitLab `refs/merge-requests/<n>/head`).
- **FR-007**: The prompt MUST be rendered from a configurable template with the
  request's kind, host, repo, number, title, author, URL, branches and
  description, plus a ready-to-run diff command.
- **FR-008**: The prompt and the description MUST be truncated per the configured
  limits.
- **FR-009**: Reviews MUST be bounded by a timeout after which the agent is
  killed and the review ends as `error`.
- **FR-010**: Tokens MUST be redacted from stored commands and error messages.
- **FR-011**: The system MUST keep a per-request review history and expose the
  latest status and output.
- **FR-012**: The app MUST list the models an agent reports and cache the result
  briefly, with a way to force a refresh.

### Key Entities

- **Agent**: a supported CLI (OpenCode, pi, Claude Code, Copilot, or custom)
  with a command template, binaries and an optional model-listing command.
- **Review**: a run for one request — agent, model, status, prompt, command,
  workspace, output, error, timing.
- **Workspace**: `DATA_DIR/workspaces/<slug>`, the shared checkout for a
  repository.

## Success Criteria *(mandatory)*

- **SC-001**: A review completes end to end with each installed agent.
- **SC-002**: The page reflects progress without a full reload.
- **SC-003**: No stored command or error leaks a provider token.
- **SC-004**: A second review of a running request is refused, not duplicated.

## Assumptions

- The user's chosen agent is installed and authenticated as it would be in their
  shell; the app inherits the environment.
- One checkout per repository is acceptable; reviews of the same repository run
  one at a time.
- Agents are non-interactive and print a review to stdout.

## Implementation Notes

- **Modules**: `agents.py` (`AGENTS`, `detect_agents`, `available_agents`,
  `agent_command`, `agent_binaries`, `render_command`, `resolve_command`,
  `run`, `list_models`, `parse_models`, model cache), `reviewer.py`
  (`start_review`, `_run_review`, `prepare_workspace`, `build_prompt`,
  `prompt_template`, `DEFAULT_REVIEW_PROMPT`, `_redact`, `_active_prs`,
  `_workspace_lock`), `providers.py` (`head_ref`, `clone_url`, commits/files),
  `app.py` (`POST /api/pr/<id>/review`, `/api/reviews/<id>`,
  `/api/pr/<id>/reviews`, `/api/agents`, `/api/agents/<id>/models`),
  `templates/pr_detail.html`.
- **Tests**: exercised indirectly by `tests/test_auto_review.py` (review start,
  per-slug lock) and `tests/test_repo_settings.py` (effective settings feed the
  review); `tests/test_reviewer.py` covers the `done`/`error` decision, including
  a non-zero exit that still carries a verdict.
- **Known limitations**: reviews are synchronous inside their thread (one agent
  process at a time per request); there is no cancellation beyond the timeout.
