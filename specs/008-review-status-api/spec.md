# Feature Specification: Review Status API & Swagger Docs

**Feature Branch**: `008-review-status-api`

**Created**: 2026-10-18

**Status**: Implemented

**Input**: User description: "Create an API to be exposed so other services can
query whether a PR passed the review. Also add a Swagger interface so the user can
test it and see the interfaces."

## Clarifications

Settled during clarification (2026-10-18):

- **What "passed" means** — *Agent verdict, parsed.* The review prompt asks the
  agent to end with a machine-readable marker; the app parses it into a stored
  verdict. When the marker is absent the verdict is `unknown`. (Not derived from
  the run status, and no manual UI verdict.)
- **How a caller identifies a request** — by repository **slug + number**
  (`<host>/<owner>/<repo>` + number), with the internal `pr_id` accepted as an
  alternative.
- **Authentication** — an optional shared **API token**. When set, callers must
  present it; when empty, the read-only API is open (local-first default).
- **Swagger delivery** — add the small `flask-swagger-ui` dependency and serve a
  hand-written OpenAPI 3 document. Assets are served locally, not from a CDN.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask whether a request passed its review (Priority: P1) 🎯 MVP

Another service (a CI job, a merge gate, a dashboard) asks PR Reviewer for the
outcome of a pull/merge request's latest review and gets a machine-readable
answer it can act on, without reading the free-form review text.

**Why this priority**: This is the whole point of the feature — an external,
automatable pass/fail signal.

**Independent Test**: Store a request, run a review whose output ends with
`REVIEW_VERDICT: PASS`, call the status endpoint with the repo slug and number,
and confirm `passed` is `true`. Repeat for `FAIL` and for a review with no marker.

**Acceptance Scenarios**:

1. **Given** a request whose latest review finished with a PASS verdict, **When**
   a caller asks for its status, **Then** `passed` is `true` and `verdict` is
   `passed`.
2. **Given** a request whose latest review finished with a FAIL verdict, **When**
   a caller asks for its status, **Then** `passed` is `false` and `verdict` is
   `failed`.
3. **Given** a request whose latest review finished without a verdict marker,
   **When** a caller asks for its status, **Then** `passed` is `null` and
   `verdict` is `unknown`.
4. **Given** a request with a review still running, **When** a caller asks for
   its status, **Then** `passed` is `null` and the review's run `status` is
   reported (`pending`/`preparing`/`running`).
5. **Given** a request that has never been reviewed, **When** a caller asks for
   its status, **Then** the call succeeds with `passed` `null` and no review.
6. **Given** a request with several reviews, **When** a caller asks, **Then**
   only the most recent review decides the verdict.
7. **Given** an unknown request, **When** a caller asks, **Then** the response is
   `404`.

---

### User Story 2 - Browse and try the API in a browser (Priority: P1)

A user opens a Swagger page, sees every published endpoint with its parameters
and response shape, and executes a request from the browser to try it out.

**Why this priority**: The user explicitly asked for an interactive interface to
inspect and test the API; without it the API is hard to discover.

**Independent Test**: Open `/api/docs`, confirm the status endpoint is listed
with its `repo`/`number` parameters, and use **Try it out** to call it.

**Acceptance Scenarios**:

1. **Given** the app is running, **When** the user visits `/api/docs`, **Then**
   an interactive Swagger UI loads (assets served locally).
2. **Given** the Swagger page, **When** the user expands the status endpoint,
   **Then** its query parameters and the response schema are shown.
3. **Given** the Swagger page, **When** the user executes a request, **Then**
   the real response is displayed.
4. **Given** a machine, **When** it fetches `/api/v1/openapi.json`, **Then** it
   receives the OpenAPI 3 document.

---

### User Story 3 - Protect the API with a shared token (Priority: P2)

An operator who exposes the app beyond their own machine can require a shared
token, so only callers that know it can read review results.

**Why this priority**: The data is read-only but private; guarding it matters
once the app is reachable on a network, but it is not needed for local use.

**Independent Test**: Set an API token, call the status endpoint without it
(expect `401`) and with it (expect `200`); clear the token and confirm the call
works without authentication.

**Acceptance Scenarios**:

1. **Given** no token is configured, **When** a caller asks without credentials,
   **Then** the request succeeds.
2. **Given** a token is configured, **When** a caller asks without it, **Then**
   the response is `401`.
3. **Given** a token is configured, **When** a caller presents it in the
   `Authorization: Bearer` header or the `X-API-Token` header, **Then** the
   request succeeds.
4. **Given** a token is configured, **When** the user opens `/api/docs`, **Then**
   the documentation still loads so the token can be entered there.
5. **Given** a saved token, **When** the user clears it in Settings, **Then**
   calls succeed without credentials again.

---

### User Story 4 - Scan many requests at once (Priority: P3)

A service that tracks many repositories lists the reviewed requests and their
verdicts in one call, optionally filtered to one repository or one verdict.

**Why this priority**: A convenience over the single lookup; useful for bulk
polling but not required for the core gate.

**Independent Test**: Store several reviewed requests with different verdicts,
call the list endpoint with a `repo` and with a `verdict` filter, and confirm the
filtered set.

**Acceptance Scenarios**:

1. **Given** several reviewed requests, **When** a caller lists them, **Then**
   each carries the same result fields as the single lookup.
2. **Given** a repository filter, **When** a caller lists, **Then** only that
   repository's requests are returned.
3. **Given** a verdict filter, **When** a caller lists, **Then** only requests
   with that latest verdict are returned.

### Edge Cases

- A marker that is **not** the final content line — a line quoted from the diff,
  or the prompt's own instruction text — is ignored, so trailing content cannot
  flip the result; a review whose last content line is not a marker reads as
  `unknown`.
- A final marker wrapped in Markdown (`**REVIEW_VERDICT: PASS**`), written as a
  bullet, or inside a code fence is still recognised; trailing blank lines, code
  fences and horizontal rules after it are ignored.
- A review that **errored** (the agent crashed or timed out) has no verdict; the
  status reports `passed: null` with the run `status` of `error`.
- A request missing both `repo`/`number` and `pr_id`: `400`.
- `repo` given without `number`, or `number` without `repo`: `400`.
- A stored request whose slug uses a non-default host is matched on the full slug.
- Unknown query parameters are ignored.
- The verdict column is added to existing databases without a manual step.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For every review that completes successfully, the app MUST record a
  verdict of `passed` or `failed`, parsed from a machine-readable marker in the
  agent's output; when the marker is absent it MUST record `unknown`. The marker
  MUST be the **final content line** of the output, so text that follows the
  agent's own verdict cannot change the result. Reviews that do not complete
  (error or still running) MUST NOT record a verdict.
- **FR-002**: The app MUST ask the agent, in **every** review prompt (the default
  template and any custom override), to end its review with a line of the form
  `REVIEW_VERDICT: PASS` or `REVIEW_VERDICT: FAIL`.
- **FR-003**: The app MUST expose a read-only endpoint
  `GET /api/v1/reviews/status` that returns the review result for one request
  identified by `repo` (slug) **and** `number`, or by `pr_id`.
- **FR-004**: The status response MUST include the request identity (`repo`
  slug, `number`, `pr_id`, title, state, url), a `passed` field
  (`true`/`false`/`null`), a `verdict` field
  (`passed`/`failed`/`unknown`/`null`), the latest review's run `status`, a
  summary of that review, and the total number of reviews.
- **FR-005**: `passed` MUST be `true` only when the latest review's verdict is
  `passed`, `false` when it is `failed`, and `null` otherwise (no review, review
  not finished, errored, or `unknown`).
- **FR-006**: An unknown request MUST return `404`. A request that omits the
  identifying parameters, supplies only one of `repo`/`number`, or passes a
  non-integer `number`/`pr_id` MUST return `400` with a JSON error.
- **FR-007**: The API MUST be read-only: it MUST NOT start, cancel or modify
  reviews, and MUST NOT contact any hosting provider.
- **FR-008**: `GET /api/docs` MUST serve an interactive Swagger UI, and
  `GET /api/v1/openapi.json` MUST serve the OpenAPI 3 document. Swagger UI assets
  MUST be served by the app itself, with no external network request.
- **FR-009**: The OpenAPI document MUST describe every `/api/v1` endpoint,
  its parameters, response schemas and the optional bearer authentication.
- **FR-010**: When `api_token` is configured, every `/api/v1` data endpoint MUST
  require it — accepted in `Authorization: Bearer <token>` or `X-API-Token:
  <token>` — and MUST return `401` when it is missing or wrong. A malformed or
  non-ASCII credential (header or configured token) MUST also yield `401`, never
  a `500`. The Swagger UI page and the OpenAPI document MUST remain reachable
  without the token. The token scopes to `/api/v1` only; the app MUST NOT imply
  it protects the other (mutating) routes, and the UI MUST say so.
- **FR-011**: When `api_token` is empty (the default), the API MUST be reachable
  without authentication. A user MUST be able to clear a saved token from the UI
  to return to this state.
- **FR-012**: The API token MUST be stored only in `DATA_DIR`, MUST be masked
  wherever settings are displayed, and MUST be redacted from any captured
  command line or error text (like the provider tokens).
- **FR-013**: The app MUST expose `GET /api/v1/reviews` listing reviewed requests
  with the same result fields as FR-004, filterable by `repo` (using the same
  slug-only matching as FR-003) and by `verdict`, and bounded by a `limit`. A
  non-integer `limit` MUST return `400`; a numeric one is clamped to `1`–`500`.
- **FR-014**: The verdict MUST be added to storage additively, so an existing
  database keeps working after an upgrade without a manual migration. Completed
  reviews stored before the verdict existed MUST read as `unknown` (backfilled),
  not as no verdict.
- **FR-015**: The verdict MUST be visible in the app's own UI: the AI Reviewed
  sidebar list and the request page MUST show a passed/failed/unknown indicator,
  and `GET /api/reviewed` MUST include the verdict.
- **FR-016**: The documentation MUST state that `passed` is the reviewing agent's
  *opinion*, not a verified or security-grade signal, because the agent reads
  request content the author controls; it MUST NOT be presented as a merge
  control on its own.

### Key Entities

- **Review verdict**: the outcome parsed from a completed review's output —
  `passed`, `failed` or `unknown` — stored alongside the review.
- **Review result**: the API's view of one request: its identity, the `passed`
  flag, the `verdict`, the latest review's run status and summary.
- **API token**: an optional shared secret (`api_token`) that gates the
  `/api/v1` endpoints when set.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller can obtain a boolean pass/fail for a synced request in a
  single HTTP request by slug + number.
- **SC-002**: The reported verdict always matches the request's most recent
  completed review.
- **SC-003**: The Swagger page lists every published endpoint and executes at
  least the status endpoint successfully from the browser.
- **SC-004**: With a token configured, an unauthenticated call is rejected
  (`401`) and an authenticated call succeeds; with no token configured, calls
  succeed without credentials.
- **SC-005**: A database created by an earlier version opens and serves request
  data unchanged, with `unknown` verdicts until requests are re-reviewed.
- **SC-006**: The full `unittest` suite passes with `DATA_DIR` pointed at a
  throwaway directory and no network access.

## Assumptions

- "The review" means the request's **most recent** review; older reviews do not
  affect the current verdict.
- A request is looked up from **stored** data, so it must have been synced at
  least once before the API can report on it.
- The repository slug is the canonical `<host>/<owner>/<repo>` identity.
- The verdict depends on the agent honouring the instruction; `unknown` is a
  normal, expected outcome rather than an error.
- The API is served by the same Flask app and port as the web UI.

## Out of Scope

- Starting, cancelling or re-running reviews through the v1 API.
- Posting the verdict back to GitHub/GitLab (commit statuses, checks, comments).
- Editing or overriding a verdict by hand.
- Pagination beyond a bounded `limit`.
