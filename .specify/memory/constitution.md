# PR Reviewer Constitution

This document is the highest authority for how PR Reviewer is designed, built
and changed. Feature specs, plans and pull requests are expected to comply with
it; when a change must break a principle, the violation is recorded and
justified in the feature's `plan.md` (see *Governance*).

## Core Principles

### I. Local-First and Private by Default

The application runs on the user's own machine and keeps all of its state
there.

- All persistent data lives under a single `DATA_DIR` (default `./data`):
  `settings.json`, the SQLite database and the `workspaces/` checkouts.
- Nothing leaves the machine except the GitHub/GitLab API calls the user
  triggers and whatever the user-selected agent process does on its own.
- There is no telemetry, analytics or "phone home" of any kind.
- Secrets (provider tokens) are stored locally, never logged, and are redacted
  from any captured command line or error text before it is shown or saved.
- The `data/` directory is private and MUST stay gitignored.

**Rationale**: Users point this tool at private repositories with credentials
that grant broad read access. Trust depends on the data never leaving their
control.

### II. Provider-Agnostic

GitHub and GitLab are supported through one small, uniform provider surface.

- A provider exposes listing requests, fetching comments/commits/diffs,
  building a clone URL and locating a request's head ref; new hosts are added by
  implementing that surface and registering the provider.
- Every repository is identified by a `slug` of `<host>/<owner>/<repo>`, so the
  same `owner/repo` on two hosts never collides. Lookups and updates that must
  be unambiguous key on the slug, not the bare `full_name`.
- Provider differences are absorbed at the edge and normalised into one shape
  (states, draft flags, diff stats) before they reach storage or the UI.

**Rationale**: The tool's value is not being tied to one host. A narrow,
consistent interface keeps each provider honest and lets the rest of the app stay
host-agnostic.

### III. Agent-Agnostic

No single coding agent is privileged; any CLI the user has can drive a review.

- Agents are described by a command template with `{prompt}` and `{model}`
  placeholders and optional `[...]` groups; the built-ins are defaults, not
  requirements.
- The app detects agents that are installed but never hard-requires a specific
  binary, and a `custom` command covers anything unlisted.
- Automatic work (auto-reviews) only starts when an agent can actually run;
  a queued review that is doomed to fail MUST NOT be created.

**Rationale**: Users already have an agent they trust and pay for. The tool
should adapt to that choice rather than dictate it.

### IV. No Surprise Actions

The app does not act on the user's behalf without being asked.

- Reviews run only when requested, with one deliberate exception: repositories
  the user has explicitly *watched*. Watching is per repository and off by
  default; the first sync of a repository establishes a baseline and never
  alerts or reviews.
- Long-running work (reviews, syncs) runs asynchronously and its progress is
  observable (queued → preparing → running → done/error).
- Destructive or costly operations are scoped to what the user selected (one
  repository, one request) and reversible where practical.

**Rationale**: Autonomy that runs up compute, clones large repositories or
posts output without consent erodes trust quickly. Opt-in keeps the user in
control.

### V. Spec-First, Test-Supported

Behaviour is agreed in writing before it is coded, and shipped logic is covered
by tests.

- Every non-trivial feature starts as a specification under `specs/NNN-*/`,
  prioritised as independently deliverable user stories, before implementation
  begins.
- Feature logic (`app`, `providers`, `storage`, `agents`, `reviewer`) is covered
  by the `unittest` suite; bug fixes add or extend a test that fails first.
- Tests run with `python3 -m unittest discover -s tests` and must pass before a
  change is merged.
- Tests must not touch the network or the user's real `data/`; they point
  `DATA_DIR` at a throwaway directory.

**Rationale**: The spec is the contract; the tests are the proof. Both keep a
fast-moving, host-and-agent-agnostic app from regressing.

### VI. Simple, Migratable Storage

State lives in plain, inspectable storage that upgrades itself safely.

- Storage is SQLite (WAL mode) plus a JSON settings file, in one `DATA_DIR`;
  there is no external database or service to run.
- Schema changes are additive and self-healing: new columns are added on start
  and existing rows are backfilled with sensible defaults, so an old database
  keeps working.
- Removing a repository or request cascades to its dependent rows; nothing is
  orphaned.

**Rationale**: A local tool should be trivially resettable and should never
require a manual migration step to keep working after an upgrade.

### VII. Small Modules, Clear Boundaries

The code stays in a few focused modules with one job each.

- `app.py` (web routes, sync, background watcher), `providers.py` (hosts),
  `storage.py` (persistence), `agents.py` (agent registry), `reviewer.py`
  (checkout + orchestration).
- Shared helpers live beside the concern they serve; cross-module coupling is
  through those small surfaces, not shared globals.
- The UI is server-rendered templates plus dependency-free JavaScript; there is
  no build step.

**Rationale**: A small footprint is easier to review, test and keep
provider-agnostic. New concerns get their own module rather than bloating an
existing one.

## Additional Constraints

- **Language/runtime**: Python 3.9+; Flask for the web layer; `requests` and
  the GitHub SDK for provider access; SQLite via the standard library.
- **No build step**: templates are Jinja2 HTML and the front end is plain
  JavaScript/CSS served from `static/`.
- **Runs without reload**: the server is started with `debug=False`; developers
  restart it after editing source (`scripts/restart.sh`).
- **Configuration is data, not code**: user-facing options live in
  `data/settings.json` and the UI. `DATA_DIR` is the only environment variable
  read, and only to locate that file.

## Development Workflow

1. **Specify** — capture the feature as user stories, requirements and
   measurable success criteria in `specs/NNN-feature-name/spec.md`.
2. **Clarify** — resolve ambiguity before planning; no requirement is left
   with an unexplained placeholder.
3. **Plan** — record the technical approach, affected modules and any
   constitution violations in `plan.md`.
4. **Tasks** — break the plan into ordered, independently testable tasks in
   `tasks.md`.
5. **Implement** — work the tasks on a feature branch; add or extend tests for
   the behaviour; run the full suite.
6. **Ship** — once the suite passes and the work matches the spec, commit the
   branch and open a pull request. This is the default outcome of finished work,
   not a step to wait to be asked for.
7. **Review** — the pull request is checked against this constitution and
   against the feature's spec, and the spec is updated if the implementation
   diverged.

Feature work happens on a branch; the specification and the code ship
together in the same pull request.

## Governance

- This constitution supersedes any conflicting practice or precedent in the
  repository.
- Amendments are made by editing this file, include a version bump and an
  updated *Last Amended* date, and are reviewed like any other change.
- Versioning follows semantic versioning: **MAJOR** for backward-incompatible
  governance changes or principle redefinitions, **MINOR** for a new or
  materially expanded principle, **PATCH** for clarifications and wording.
- Every feature plan includes a *Constitution Check*; any principle that cannot
  be satisfied is recorded with the justification and the simpler alternative
  that was rejected.
- When guidance here is silent, prefer the option that best serves Principles
  I–IV (local, provider-agnostic, agent-agnostic, no surprises).

**Version**: 1.0.1 | **Ratified**: 2026-10-18 | **Last Amended**: 2026-10-18
