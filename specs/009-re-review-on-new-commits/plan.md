# Implementation Plan: Re-review Watched Requests on New Commits

**Branch**: `009-re-review-on-new-commits` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-re-review-on-new-commits/spec.md`

## Summary

Let a watched repository's already-reviewed open requests be re-reviewed
automatically when they gain new commits. The provider surface gains the
request's head commit id; storage keeps it on the request and records it on
each review; `sync_repos` compares the two during a sync and queues a review
through the existing auto-review path. The request list shows the watch
indicator so the behaviour is discoverable.

## Technical Context

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI

**Project Type**: Single-project web application

**Performance Goals**: No extra provider calls; the head comparison is in-memory
over entries the sync already fetched plus one lookup of the request's latest
review, and only for requests whose `updated_at` moved.

**Constraints**: No new services or build step; no new settings.

**Scale/Scope**: Tens of repositories, hundreds of requests.

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | yes | Head SHAs are public identifiers stored in `DATA_DIR`; no new outbound call, no secrets touched. |
| II. Provider-Agnostic | yes | The head id is exposed through the one provider surface for both GitHub and GitLab; comparison is provider-neutral. |
| III. Agent-Agnostic | yes | Re-reviews reuse `auto_review_agent`/`start_auto_reviews`; no agent-specific code. |
| IV. No Surprise Actions | yes | Re-reviews only for watched repositories, only open requests already reviewed, only on a real head change, and never when a review is running. |
| V. Spec-First, Test-Supported | yes | Extends `tests/test_auto_review.py`; spec ships with the code. |
| VI. Simple, Migratable Storage | yes | Additive columns (`pull_requests.head_sha`, `reviews.head_sha`) via the existing self-healing migration; no backfill that could trigger work. |
| VII. Small Modules | yes | Changes stay in the existing modules; no new module needed. |

No violations. *Complexity Tracking* is empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-re-review-on-new-commits/
├── spec.md              # the feature specification
├── plan.md              # this file
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
providers.py    # expose `head_sha` on the request entry (GitHub + GitLab)
storage.py      # head_sha columns on pull_requests and reviews; carry it through
reviewer.py     # record the head the review runs against
app.py          # detect "head moved since latest review" during sync; watch indicator
templates/index.html  # watch indicator on request rows
tests/test_auto_review.py  # re-review trigger and its guards
README.md       # document re-review-on-new-commits
```

**Structure Decision**: All four concerns already have a home, so no new module.
`providers.py` owns fetching the head id; `storage.py` owns the two additive
columns and the request/review shapes; `reviewer.py` owns snapshotting the head
when a review starts; `app.py` owns the sync-time decision. This mirrors how the
existing watch-and-auto-review feature is split.

## Design

- **Provider surface**: add `head_sha` to the normalised request entry —
  `pull.head.sha` on GitHub, `mr["sha"]` on GitLab — using the existing
  `_safe`/`.get` tolerance so a missing value is `None`, never an error.
- **Storage**:
  - `pull_requests.head_sha TEXT` (SCHEMA + `_EXTRA_PR_COLUMNS`), written by
    `save_pr` and returned by `_pr_dict`.
  - `reviews.head_sha TEXT` (SCHEMA + `_EXTRA_REVIEW_COLUMNS`), written by
    `create_review` and returned by `_review_dict`.
  - No backfill: existing rows stay `NULL`, which the trigger reads as "no
    baseline".
- **Reviewer**: `start_review` passes `pr.get("head_sha")` into `create_review`,
  so every new review records its baseline head.
- **Sync trigger** (`sync_repos`): for an existing request whose stored
  `updated_at` changed (so it was re-fetched), when the repository is watched,
  the request is open, and the latest review's recorded head is a non-empty
  value that differs from the entry's head, queue `(pr_id, repo)` through
  `start_auto_reviews`. New requests keep their existing path
  (notification + review); re-reviews never notify. `start_auto_reviews`
  already skips requests with a running review and with no usable agent.
- **UI**: pass `watched_slugs` to `index.html`; render the 🔔 next to a request
  whose slug is watched.

## Complexity Tracking

> No constitution violations.

| Violation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| *(none)* | | |

## Risks & Rollback

- **Risks**: a provider that reports a spurious head (e.g. a divergent SHA) could
  cause an extra review; guarded by requiring a previously recorded head and by
  the running-review skip. Two additive columns are invisible to older code.
- **Rollback**: revert the commit. Old rows with the extra columns are ignored by
  the previous version; the columns are additive and cause no data loss.
