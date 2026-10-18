# Implementation Plan: Review Status API & Swagger Docs

**Branch**: `008-review-status-api` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-review-status-api/spec.md`

## Summary

Give every completed review a machine-readable **verdict** parsed from the
agent's output (`REVIEW_VERDICT: PASS|FAIL`), store it on the `reviews` row, and
expose a small read-only **v1 API** (`GET /api/v1/reviews/status`,
`GET /api/v1/reviews`) that reports whether a request passed its latest review.
Document the API with a hand-written OpenAPI 3 file served through a locally
bundled **Swagger UI** at `/api/docs`, and gate the data endpoints behind an
optional shared **API token**.

The work is split so the verdict pipeline (prompt + parse + column) is the
foundation, the status endpoint is the MVP, and the docs, token and list endpoint
layer on top.

## Technical Context

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard) plus
`flask-swagger-ui` (new; serves the Swagger UI assets locally)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`; one additive
`verdict` column on `reviews`, no other schema change

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI + JSON API

**Project Type**: Single-project web application

**Performance Goals**: The status endpoint is a couple of indexed lookups
(`pull_requests` by slug+number, `reviews` by `pr_id`); it must answer in
milliseconds and never touch the network.

**Constraints**: No build step; no external service; the API is read-only; the
server keeps running with `debug=False`.

**Scale/Scope**: Tens of repositories, hundreds of requests, a handful of reviews
each; the list endpoint is bounded by `limit`.

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | yes | The API reads local SQLite only; it never calls a provider. `api_token` lives in `DATA_DIR`, is masked in the UI and redacted from logged text. Swagger assets are served locally (no CDN). |
| II. Provider-Agnostic | yes | The lookup keys on the host-agnostic `slug` (`<host>/<owner>/<repo>`) and the normalised fields already stored for GitHub and GitLab; no provider branching. |
| III. Agent-Agnostic | yes | The verdict is parsed from whatever agent ran through the existing command templates; no agent is privileged and the marker is appended to the prompt for all agents. |
| IV. No Surprise Actions | yes | The API is strictly read-only (FR-007); it starts no work. Auth is opt-in; the token is off (open) by default. |
| V. Spec-First, Test-Supported | yes | A new `tests/test_api.py` covers parsing, the endpoints, auth and the migration; the spec ships with the code. |
| VI. Simple, Migratable Storage | yes | One additive `verdict` column applied through the existing `_ensure_columns` self-healing path; old rows read back as no-verdict. |
| VII. Small Modules | yes | The new surface is its own module, `api.py` (blueprint + auth + OpenAPI serving); verdict parsing stays in `reviewer.py`, storage helpers in `storage.py`. |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/008-review-status-api/
├── spec.md              # the feature specification
├── plan.md              # this file
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
api.py                 # NEW: /api/v1 blueprint, token auth, Swagger UI + OpenAPI
openapi.json           # NEW: hand-written OpenAPI 3 description of the API
reviewer.py            # append the verdict instruction; parse the verdict from output
storage.py             # verdict column + migration; lookup/latest-review helpers; settings key
app.py                 # register the Blueprint; api_token setting (masked); expose verdict
templates/index.html   # API token field (Server tab) + verdict indicator in AI Reviewed list
templates/pr_detail.html  # verdict badge on the review panel
requirements.txt       # + flask-swagger-ui
tests/test_api.py      # NEW: parsing, endpoints, auth, list, migration
README.md              # features, settings, API reference, docs link
```

**Structure Decision**: The public API is a new concern (its own routes, auth and
documentation), so it gets its own module, `api.py`, registered onto the existing
Flask app — matching Principle VII (a new concern gets a module rather than
growing `app.py`). Verdict parsing belongs to the review pipeline
(`reviewer.py`), and persistence to `storage.py`, both of which already own those
concerns.

### Design notes

- **Verdict marker**: `reviewer.VERDICT_INSTRUCTION` is appended to every rendered
  prompt in `build_prompt`, so a custom `review_prompt` cannot accidentally drop
  it. The default prompt is left unchanged.
- **Parsing**: `reviewer.parse_verdict(output)` looks only at the **final content
  line** (skipping trailing blanks, fences and rules), tolerating surrounding
  Markdown; `PASS` → `passed`, `FAIL` → `failed`, anything else → `None`. This
  stops diff content or a quoted example after the verdict from flipping it. On a
  successful run, `_run_review` stores the parsed value or `unknown` when there is
  no marker; failed runs store nothing.
- **Storage**: `reviews.verdict TEXT` is added to `SCHEMA` for new databases and
  to `_EXTRA_REVIEW_COLUMNS`, applied in `init_db` via `_ensure_columns` for
  existing ones, followed by `_backfill_review_verdicts` so completed reviews that
  predate the column read as `unknown`. `verdict` joins `REVIEW_FIELDS` and
  `_review_dict`. New helpers: `get_pr_by_number(slug, number)` (slug-only),
  `latest_review(pr_id)`, `count_reviews(pr_id)` and
  `list_review_statuses(repo, verdict, limit)`.
- **Read model**: `api._result(pr)` builds the single result shape from the
  request plus its latest review; `passed` is derived exactly per FR-005.
- **Auth**: `api.require_token` checks `api_token` from settings; empty means
  open. Comparison uses `hmac.compare_digest`. The docs page and OpenAPI file are
  exempt so the token can be entered in Swagger UI.
- **Swagger**: `flask_swagger_ui.get_swaggerui_blueprint("/api/docs",
  "/api/v1/openapi.json", ...)` serves the bundled UI; `/api/v1/openapi.json`
  returns the checked-in `openapi.json`. A `persistAuthorization` hint lets the
  token survive reloads within the browser session.
- **Settings**: `api_token` joins `TEXT_SETTINGS` in `app.py` and
  `DEFAULT_SETTINGS` in `storage.py`; `settings_payload` masks it like the
  provider tokens, and the UI only sends it when non-empty (same rule as tokens).

## Complexity Tracking

> No constitution violations; nothing to justify.

## Risks & Rollback

- **Risks**: A new runtime dependency (`flask-swagger-ui`). The verdict hinges on
  the agent emitting the marker; absence is handled as `unknown`, never as a
  false failure. The status endpoint is public by default — documented, and
  guarded by the optional token.
- **Rollback**: revert the commit and drop `flask-swagger-ui` from
  `requirements.txt`. The additive `verdict` column is simply ignored by the
  previous version, so no database rollback is needed.
