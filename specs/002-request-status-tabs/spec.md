# Feature Specification: Request List and Status Tabs

**Feature Branch**: `002-request-status-tabs`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Split the request list into Open, Closed, Merged
and All tabs so finished requests no longer clutter the ones still needing
attention, and keep the states accurate on sync."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Filter requests by state (Priority: P1)

A user opens the dashboard and sees only the requests that are still open by
default, then switches tabs to look at closed or merged ones, or all of them.

**Why this priority**: The dashboard's primary job is showing what still needs
attention; the extra tabs are a refinement of that.

**Independent Test**: With requests in all three states, open each tab and
confirm the list and counts match.

**Acceptance Scenarios**:

1. **Given** stored requests in open, closed and merged states, **When** the
   dashboard loads, **Then** the **Open** tab is selected and only open requests
   are listed.
2. **Given** the same data, **When** the user selects **Merged**, **Then** only
   merged requests are listed.
3. **Given** the same data, **When** the user selects **All**, **Then** every
   stored request is listed.
4. **Given** a selected repository, **When** the user switches tabs, **Then**
   the counts and list are scoped to that repository.

---

### User Story 2 - Counts and captions on the tabs (Priority: P2)

Each tab shows a live count, and the list header summarises the current
selection.

**Why this priority**: Counts make the tabs useful at a glance rather than a
guessing game; the layout works without them.

**Independent Test**: Compare each tab's count against the number of stored
requests in that state.

**Acceptance Scenarios**:

1. **Given** stored requests, **When** the dashboard renders, **Then** each of
   the four tabs shows the number of matching requests.
2. **Given** the **Open** tab, **When** it is shown, **Then** the header reads
   like `2 open · 5 total`.

---

### User Story 3 - States stay accurate after sync (Priority: P3)

A request closed or merged upstream is updated locally instead of lingering as
open.

**Why this priority**: The tabs are only trustworthy if the stored state tracks
the host.

**Independent Test**: Sync a repository whose request has been closed upstream
and confirm it moves out of the Open tab.

**Acceptance Scenarios**:

1. **Given** an open request that is merged upstream, **When** the user syncs,
   **Then** the stored state becomes `merged`.
2. **Given** a request closed upstream, **When** the user syncs, **Then** the
   stored state becomes `closed`.

### Edge Cases

- An unrecognised state is folded into its own count key rather than dropped.
- A repository with no requests shows zero counts and an empty list.
- Requests stored before states were tracked default to `open` on migration.
- A `state` query value outside the known set falls back to `open`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer four tabs — Open, Closed, Merged and All —
  with a per-tab count.
- **FR-002**: The system MUST default to **Open** when no state is given.
- **FR-003**: The system MUST normalise provider states into `open`, `closed`
  and `merged`, distinguishing a merged GitHub pull request (reported as closed)
  from a merely closed one.
- **FR-004**: Sync MUST fetch all states so closed and merged requests are
  updated in place.
- **FR-005**: The list, its counts and the header caption MUST respect both the
  selected repository and the selected state.
- **FR-006**: Existing rows without a state MUST be backfilled to `open`.
- **FR-007**: Tab selection MUST be expressible in the URL (`?repo=…&state=…`)
  so a view can be linked to and reloaded.

### Key Entities

- **Request state**: one of `open`, `closed`, `merged`; `all` is a view, not a
  stored state.

## Success Criteria *(mandatory)*

- **SC-001**: Each tab lists exactly the requests in that state, and its count
  matches the list length.
- **SC-002**: A request closed or merged upstream no longer appears under Open
  after a sync.
- **SC-003**: Counts stay correct when filtered by repository.

## Assumptions

- GitHub reports a merged pull request with `state == "closed"` plus a merged
  flag; GitLab reports `opened`, `closed` or `merged`.
- "All" is a convenience view over the same stored rows.

## Implementation Notes

- **Modules**: `app.py` (`PR_STATE_TABS`, `_selected_state`, `_state_summary`,
  `index`, `/api/prs`), `storage.py` (`list_prs`/`count_prs` state filter,
  `pr_state_counts`, `save_pr`), `providers.py` (`_github_state`, `STATE_MAP`,
  `state="all"` fetches), `templates/index.html`.
- **Tests**: covered indirectly by `tests/test_auto_review.py` (state drives
  auto-review) and exercised by the storage state filters.
- **Known limitations**: additions/deletions totals are only shown when the host
  provides them (GitLab lists them per file, not per request).
