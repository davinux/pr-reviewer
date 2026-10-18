# Feature Specification: Multi-Host Repositories

**Feature Branch**: `001-multi-host-repositories`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Add repositories from GitHub or GitLab, including
self-hosted GitLab, and keep the same `owner/repo` on two hosts distinct."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add a repository from either host (Priority: P1)

A user adds a repository by typing a reference into the sidebar and choosing a
provider. For example `owner/repo`, `gitlab:group/project`,
`gitlab.com/group/sub/project` or `https://gitlab.example.com/team/app`.

**Why this priority**: Nothing works until a repository can be registered. This
is the entry point for every other feature.

**Independent Test**: Add a repository with each accepted input form and confirm
it appears in the sidebar with the right provider and host.

**Acceptance Scenarios**:

1. **Given** no repositories, **When** the user adds `owner/repo` with GitHub
   selected, **Then** a repository is stored for `github.com/owner/repo`.
2. **Given** GitLab selected, **When** the user adds `group/sub/project`,
   **Then** the full namespace including the subgroup is stored.
3. **Given** a self-hosted GitLab, **When** the user adds
   `https://gitlab.example.com/team/app`, **Then** the provider is GitLab and
   the host is `gitlab.example.com`.
4. **Given** a reference ending in `.git`, **When** it is added, **Then** the
   `.git` suffix is stripped from the stored name.
5. **Given** several references at once, **When** one is malformed, **Then** the
   valid ones are stored and the malformed one is reported as an error.

---

### User Story 2 - The same path on two hosts stays distinct (Priority: P2)

A user works with `owner/repo` on GitHub and `owner/repo` on GitLab. The two
must never be confused: settings, requests and reviews stay separate.

**Why this priority**: Colliding identities silently corrupt data — the wrong
repository is read, or one repository's settings leak onto another.

**Independent Test**: Add `acme/api` on both hosts, change one's settings, and
confirm the other is untouched.

**Acceptance Scenarios**:

1. **Given** `github.com/acme/api` and `gitlab.com/acme/api` both exist,
   **When** the user looks up `acme/api`, **Then** it is not resolvable (the
   bare name is ambiguous).
2. **Given** both exist, **When** the user changes the timeout for
   `github.com/acme/api`, **Then** `gitlab.com/acme/api` is unchanged.

---

### User Story 3 - Remove a repository and its data (Priority: P3)

A user removes a repository they no longer care about, and its stored requests,
comments and reviews go with it.

**Why this priority**: Keeps local state tidy, but the app is usable without it.

**Independent Test**: Add a repository with stored requests, remove it, and
confirm its rows are gone.

**Acceptance Scenarios**:

1. **Given** a repository with stored requests, **When** it is removed, **Then**
   its pull requests, comments and reviews are deleted too.
2. **Given** a repository that does not exist, **When** removal is requested,
   **Then** the app reports it was not found.

### Edge Cases

- An empty reference, or one without a `/`, is rejected with a clear message.
- An unknown provider id yields `Unknown provider` rather than an exception.
- A reference that names a host without a provider hint (`gitlab.example.com/x/y`)
  is resolved to GitLab by the host name.
- A database created before multi-host support is backfilled to
  `github`/`github.com` on start.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a repository as `owner/repo`,
  `provider:owner/repo`, `host/owner/repo` or a full `http(s)://` URL, with an
  optional trailing `.git`.
- **FR-002**: The system MUST identify each repository by a `slug` of
  `<host>/<owner>/<repo>`.
- **FR-003**: The slug MUST be unique, and lookups that must be unambiguous
  (settings, watch, removal) MUST key on the slug, not the bare `full_name`.
- **FR-004**: The system MUST support GitHub and GitLab, and MUST resolve a
  GitLab subgroup path (`group/sub/project`) in full.
- **FR-005**: The system MUST let the default host per provider come from the
  configured provider URLs.
- **FR-006**: The system MUST store repositories with their provider, host and
  slug, and MUST survive duplicate additions without erroring.
- **FR-007**: Removing a repository MUST cascade to its requests, comments and
  reviews.
- **FR-008**: Existing databases MUST be migrated on start: provider, host and
  slug are backfilled, defaulting to GitHub.

### Key Entities

- **Repository**: a tracked project — `full_name`, `provider`, `host`, unique
  `slug`, `watch` flag, per-repository `settings`.
- **Provider**: a host adapter (GitHub, GitLab) exposing request listing,
  comments/commits/diffs, clone URL and head-ref lookup.

## Success Criteria *(mandatory)*

- **SC-001**: Every documented input form resolves to the expected
  provider/host/name.
- **SC-002**: Two repositories sharing a `full_name` on different hosts never
  share settings, requests or reviews.
- **SC-003**: Removing a repository leaves no orphaned requests, comments or
  reviews.
- **SC-004**: An upgraded database keeps working with no manual step.

## Assumptions

- The user has a token for the host when the repository is private.
- Hosts are identified by their URL hostname; `gitlab` in the hostname implies
  GitLab, `github.com` implies GitHub.
- Only GitHub and GitLab are in scope; new hosts are added by implementing the
  provider surface.

## Implementation Notes

- **Modules**: `providers.py` (`parse_repo`, `provider_hosts`, `token_for`,
  `get_provider`, the `GitHub`/`GitLab` classes, `PROVIDERS`),
  `storage.py` (`repos` table, unique slug index, `add_repos`, `get_repo`,
  `remove_repo`, `_backfill_provider_columns`), `app.py` (`/api/repos`,
  `DELETE /api/repos/<slug>`).
- **Tests**: `tests/test_repo_settings.py`
  (`test_get_repo_matches_slug_only`, `test_set_repo_settings_touches_one_host_only`,
  `test_post_uses_slug_so_other_host_is_untouched`).
- **Known limitations**: only two providers ship; the slug is the sole identity
  used for per-repository operations.
