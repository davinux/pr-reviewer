# Implementation Plan: Auto-Archive Reviewed Requests

**Branch**: `007-auto-archive-reviewed` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-auto-archive-reviewed/spec.md`

## Summary

When a sync detects that a request which is tracked in the **AI Reviewed** list
has *changed* from open to closed or merged, the app archives it — the same
"dismissal" that the sidebar's × already performs, so the review history is kept
and starting a new review brings it back. This happens inside the one sync code
path, so both the **Sync PRs** button and the background watcher get it.

Separately, removing an entry from the sidebar now asks for confirmation through
the existing `appConfirm` dialog before calling the API.

## Technical Context

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`; reuses the
existing `dismissed_reviews` table, no schema change

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI

**Project Type**: Single-project web application

**Performance Goals**: Archiving adds one small indexed lookup per changed
request during a sync; it must not change the sync's shape or block the UI

**Constraints**: No new dependency, no build step, no new setting

**Scale/Scope**: Tens of repositories, hundreds of requests; a handful of
state transitions per sync

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | yes | State stays in the existing `dismissed_reviews` table in `DATA_DIR`; no new data leaves the machine. |
| II. Provider-Agnostic | yes | Driven by the normalised `state` (`open`/`closed`/`merged`) already produced for GitHub and GitLab; no provider branching. |
| III. Agent-Agnostic | no | No agent involvement; archiving is independent of reviews' content or agent. |
| IV. No Surprise Actions | yes | Archiving only mirrors an upstream state change the user can already see on the **Closed**/**Merged** tabs; removal stays reversible and manual deletion is now confirmed. |
| V. Spec-First, Test-Supported | yes | New `tests/test_archive_reviewed.py` covers the storage helper, the sync transition rule and the API; spec ships with the code. |
| VI. Simple, Migratable Storage | yes | Reuses `dismissed_reviews`; no column or migration. |
| VII. Small Modules | yes | Two small helper functions in `storage.py`, the transition check in `app.py`'s existing sync loop, and a JS guard in `index.html`. |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/007-auto-archive-reviewed/
├── spec.md              # the feature specification
├── plan.md              # this file
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
app.py          # sync_repos: detect open→closed/merged transitions, archive
storage.py      # existing_pr_states(); archive_review(pr_id)
templates/index.html  # confirm before the sidebar × removes an entry
tests/test_archive_reviewed.py  # new coverage
```

**Structure Decision**: The behavior belongs to the existing sync loop in
`app.py` and the existing dismissal storage in `storage.py`; the confirmation is
a small guard around the existing `dismissReviewed` call in `index.html`. No new
module is warranted — this is a refinement of the AI Reviewed list (spec 006),
not a new concern.

### Design notes

- **Detecting the transition**: `sync_repos` already loads `existing_pr_meta()`
  (id → `updated_at`). Add `storage.existing_pr_states()` (id → `state`) and read
  the previous state before `save_pr` overwrites it. A request that was `open`
  and is now `closed`/`merged` is a candidate.
- **Archiving only list members**: `storage.archive_review(pr_id)` inserts into
  `dismissed_reviews` only when the request has at least one review, so a request
  that was never in the list stays out of it, and the rule is idempotent.
- **First sync / failed fetch**: `existing_pr_states()` returns no entry for a
  request that was not stored yet (first sync), so no transition is detected; a
  provider error skips the repository's entries entirely. Both match the spec.
- **Observability**: the sync payload gains an `archived` count when anything was
  archived, mirroring `auto_reviewed`.
- **Confirmation**: `dismissReviewed` becomes async and awaits
  `appConfirm({ title, message, okText })`; the message names
  `repo #number — title`. Cancel returns before any `fetch`.

## Complexity Tracking

> No constitution violations; nothing to justify.

## Risks & Rollback

- **Risks**: A request merged while its review is still running is hidden; this is
  intended (the request is finished) and the review still completes and stays in
  the history.
- **Rollback**: revert the commit. The `dismissed_reviews` rows it wrote are the
  same ones manual removal writes, so a reverted build simply shows the affected
  entries again; nothing else changes.
