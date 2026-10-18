# Feature Specification: Per-Repository Settings

**Feature Branch**: `003-per-repository-settings`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Override the review prompt, agent, model and
limits for individual repositories; anything left alone falls back to the global
Settings."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Override and clear settings for one repository (Priority: P1)

A user opens a repository's settings dialog, sets a review timeout of 120
seconds and picks an agent, and sees those take effect for that repository only.
Clearing a field restores the global value.

**Why this priority**: This is the whole feature — differences between
repositories are the reason it exists.

**Independent Test**: Set an override for one repository, change it, clear it,
and confirm the value each time.

**Acceptance Scenarios**:

1. **Given** global defaults, **When** the user sets a repository's timeout to
   `120`, **Then** that repository's effective timeout is `120` and the global
   timeout is unchanged.
2. **Given** a repository with an override, **When** the user clears the field,
   **Then** the repository inherits the global value again.
3. **Given** a repository, **When** the user enters a value equal to the global
   value, **Then** it is stored as "no override" (the repository inherits).
4. **Given** the built-in prompt, **When** the user sets the repository prompt
   back to the built-in default, **Then** the override is dropped.

---

### User Story 2 - Overrides stay on one host (Priority: P2)

Because identity is the slug, overriding settings on one host never touches the
same path on another host.

**Why this priority**: Without it, a per-repository feature silently becomes a
cross-repository one.

**Independent Test**: Override `github.com/acme/api` and confirm
`gitlab.com/acme/api` is unchanged.

**Acceptance Scenarios**:

1. **Given** `acme/api` on GitHub and GitLab, **When** the user overrides the
   GitHub copy, **Then** the GitLab copy keeps the global values.
2. **Given** only the bare `acme/api`, **When** an update is attempted, **Then**
   it does not match any repository.

---

### User Story 3 - Reject invalid input (Priority: P3)

Input the UI could not produce is rejected rather than stored.

**Why this priority**: Protects stored configuration from typos and bad clients;
the feature works without it.

**Independent Test**: Post a non-numeric limit and an unknown agent and confirm
both are rejected and nothing is stored.

**Acceptance Scenarios**:

1. **Given** a repository, **When** a non-numeric timeout is posted, **Then** the
   request fails with an error and no override is stored.
2. **Given** a repository, **When** an unknown agent id is posted, **Then** the
   request fails with an error.
3. **Given** a repository, **When** a timeout below `1` is posted, **Then** it
   is floored to `1`.
4. **Given** a repository, **When** unknown keys (e.g. a token) are posted,
   **Then** they are ignored.

### Edge Cases

- A value that is corrupt in storage is ignored during merge, not fatal.
- An empty stored override is ignored, so clearing restores the global value.
- The **Custom command** agent can be chosen per repository, but its command
  template stays global.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A repository MUST be able to override `review_prompt`,
  `default_agent`, `default_model`, `review_timeout`, `max_prompt_chars` and
  `max_description_chars`.
- **FR-002**: A field with an empty value, or one equal to the global value,
  MUST be dropped so the repository inherits.
- **FR-003**: Numeric overrides MUST be validated as whole numbers and floored
  (`review_timeout` at 1; the character limits at 0, where 0 means no limit).
- **FR-004**: An unknown agent id MUST be rejected; unknown keys MUST be ignored.
- **FR-005**: Overrides MUST be stored on the repository row, keeping only
  known keys with a non-empty value that differs from the global value.
- **FR-006**: The effective settings for a repository MUST be its overrides
  merged onto the global settings, preferring the override.
- **FR-007**: Read and write of a repository's settings MUST key on the slug.
- **FR-008**: The dialog MUST show the global value as a fallback hint and offer
  shortcuts back to the global or built-in prompt.

### Key Entities

- **Override**: a single key/value on a repository that differs from the global
  setting; stored as JSON in `repos.settings`.
- **Global settings**: the defaults every repository inherits.

## Success Criteria *(mandatory)*

- **SC-001**: An override changes only the target repository's effective review.
- **SC-002**: Clearing a field restores the global value.
- **SC-003**: Invalid input is rejected and never persisted.
- **SC-004**: Overriding one host never affects the same path on another host.

## Assumptions

- Global settings are edited in the main Settings dialog and act as defaults.
- The review-related keys are the only ones worth varying per repository.

## Implementation Notes

- **Modules**: `storage.py` (`REPO_SETTINGS`, `REPO_INT_SETTINGS`,
  `set_repo_settings`, `_load_repo_settings`), `app.py`
  (`_coerce_repo_setting`, `_repo_global_value`, `_clean_repo_overrides`,
  `effective_repo_settings`, `repo_settings_payload`,
  `GET/POST /api/repos/<slug>/settings`), `templates/_dialogs.html`.
- **Tests**: `tests/test_repo_settings.py` — the inherit/override/clear round
  trip, multi-host isolation, validation, flooring and tolerance of bad data.
- **Known limitations**: choosing the **custom** agent per repository still uses
  the global custom command.
