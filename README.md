# PR Reviewer

Review **GitHub pull requests** and **GitLab merge requests** with a local
coding agent. PR Reviewer lists the requests across the repositories you care
about — open, closed and merged — and on demand it clones the repository, checks
out the request, and runs an installed agent CLI
([opencode](https://opencode.ai), `pi`, Claude Code, GitHub Copilot, or a custom
command) to produce a review you can read in the browser.

There are no automatic reviews by default: reviews run only when you ask for
them. Watching a repository is the exception — new requests there are reviewed
automatically (see *Watching for new pull requests*). Data stays on your machine
except the GitHub/GitLab API calls and whatever your chosen agent does.

## Features

- **GitHub and GitLab** — add repositories from either host (including
  self-hosted GitLab). The same `owner/repo` on two hosts is kept distinct.
- **Any installed agent** — detects `opencode`, `pi`, `claude` and `copilot`,
  and lets you run whichever is present. A **custom command** option covers any
  other CLI.
- **Selectable repositories** — pick a repo from the sidebar to see just its
  requests, or "All repositories".
- **Per-repository settings** — override the review prompt, agent, model and
  limits for individual repositories; anything you leave alone falls back to the
  global Settings.
- **Status tabs** — the request list is split into **Open**, **Closed**,
  **Merged** and **All** tabs, each with a live count, so finished requests no
  longer clutter the ones still needing attention.
- **Rich request view** — Markdown description and comments, author, labels,
  draft status, branches, diff stats and metadata.
- **Commits & changes** — the request page lists the commits and shows a
  GitHub-style **Files changed** view with per-file unified or split diffs.
- **Agent reviews** — run a review from the request page; the app prepares a
  checkout and captures the agent's Markdown review.
- **Async with live status** — reviews run in the background and the page polls
  for progress (preparing → running → done/error).
- **Live timer & logs** — a running review shows a ticking timer and the agent's
  output as it is produced, so a long run never looks stuck; the log stays with
  the review afterwards.
- **AI Reviewed list** — the sidebar tracks every reviewed pull/merge request
  with its latest status; requests that are merged or closed are archived
  automatically, and you can clear the ones you are done with (after a
  confirmation).
- **Review status API** — every completed review carries a machine-readable
  verdict (pass/fail) that other services can query over a small read-only HTTP
  API, with interactive Swagger docs at <http://localhost:5000/api/docs>.
- **Local storage** — repositories, requests, comments and reviews live in
  SQLite under a single `data/` folder.
- **Sync on demand** — a button fetches requests from the hosts when asked,
  including their current open/closed/merged state.
- **Watch for new PRs** — optionally watch individual repositories; new
  pull/merge requests show a notification, play a short sound, and are reviewed
  automatically. Watched requests you have already reviewed are reviewed again
  when their branch gains new commits.
- **Light / dark theme** — a toggle in the navbar; it defaults to your system
  preference and remembers your choice.
- **Resizable sidebar** — drag the divider beside the sidebar to widen or narrow
  it (or focus it and use the arrow keys); the width is remembered per browser.

## How a review works

1. You click **Run review** on a pull/merge request.
2. The app clones (or refreshes) the repo into
   `data/workspaces/<host>__<owner>__<repo>`.
3. It fetches the request head and checks it out:
   - GitHub: `refs/pull/<n>/head`
   - GitLab: `refs/merge-requests/<n>/head`
   and fetches the target/base branch.
4. It runs your chosen agent in that checkout with a review prompt. The agent
   inspects the diff and surrounding code and prints a Markdown review.
5. The review is saved to the database and shown on the request page, with a
   history of previous reviews. While it runs, the page shows a live timer and
   the agent's output streaming into the **Logs** area.
6. The agent ends its review with a machine-readable verdict
   (`REVIEW_VERDICT: PASS` or `REVIEW_VERDICT: FAIL`) that PR Reviewer parses and
   stores, so the outcome can be read by other tools (see *Review status API*).

That final verdict is also how the app decides a run finished. If the agent's
CLI exits non-zero *after* printing the review — OpenCode does this, for example,
when its web-search tool is unavailable — the review is still saved as `done`
with its verdict instead of being discarded as a failure. A non-zero exit with no
verdict is still an error.

## Review timer and logs

A review that takes several minutes should not look stuck, so the request page's
**AI Review** panel shows two live aids while a run is in progress:

- **Timer** — a badge that counts up from the moment you clicked **Run review**,
  updating every second. It freezes on the total time when the review finishes,
  and the **History** entries and metadata show how long each past review took.
- **Logs** — the agent's standard output and standard error, streamed into a
  scrollable pane as they are produced (standard error lines are prefixed with
  `[stderr]`). While a run is in progress the pane follows the newest output;
  a **Show/Hide** button collapses it. The log is kept with the review, so you can
  reopen it later from **History**.

The log is stored locally in the same database as the rest of the review data. It
is redacted of your provider token before being stored, and it is **bounded** (the
oldest output is dropped once it grows past a fixed size), so a very chatty agent
cannot grow the database without limit. The final review output is stored in full
whether or not it was truncated from the live log.

## Requirements

- Python 3.9+
- `git` on the `PATH` (used to clone and check out requests)
- A GitHub and/or GitLab [personal access token](https://gitlab.com/-/user_settings/personal_access_tokens)
  with read access (needed for private repos and to avoid rate limits)
- At least one agent CLI installed and authenticated, e.g. `opencode`, `pi`,
  `claude` or `copilot`

## Installation

```bash
git clone <your-repo-url> pr-reviewer
cd pr-reviewer

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

## Running

```bash
python3 app.py
```

Then open <http://localhost:5000>.

### Using the scripts

For a background server (start / stop / restart), use the scripts in `scripts/`:

```bash
scripts/start.sh     # start in the background (writes data/pr_reviewer.pid + .log)
scripts/stop.sh      # stop it
scripts/restart.sh   # stop, then start
```

They prefer `.venv/bin/python` when present, otherwise `python3`, and honour
`DATA_DIR` (the pid file and log live there, alongside `settings.json`). The host
and port come from Settings.

`stop.sh` also finds a server you started by hand (e.g. `python3 app.py`), even
without a pid file — it looks for a Python process whose command line references
`app.py` and whose working directory is the project.

> **Note:** the app runs with `debug=False`, so it does **not** reload on code
> changes. Restart it after editing the source — with `scripts/restart.sh`, or
> manually:
>
> ```bash
> pkill -f "python3 .*app.py"   # stop an older instance
> python3 app.py
> ```

### Tests

A small `unittest` suite covers the per-repository settings (parsing, the
inherit/override/clear round trip, multi-host lookups and input validation), the
automatic review trigger for watched repositories (including re-reviews when a
reviewed request gains commits), the auto-archive of reviewed requests that
finish, the live timer and streaming logs (incremental output, token redaction and
the log cap), and the review-status API (verdict parsing, the status and
list endpoints, token authentication and the Swagger/OpenAPI endpoints). Run it
with:

```bash
python3 -m unittest discover -s tests
```

## Adding repositories

In the sidebar, choose **GitHub** or **GitLab**, then enter a repository. These
forms are all accepted:

| Input | Result |
| --- | --- |
| `owner/repo` | Uses the selected provider and its default host. |
| `gitlab:group/project` | GitLab, `gitlab.com` (or your configured GitLab URL host). |
| `github:owner/repo` | GitHub, `github.com`. |
| `gitlab.com/group/sub/project` | GitLab with a subgroup. |
| `https://gitlab.example.com/team/app` | Self-hosted GitLab. |
| `https://github.com/octocat/Hello-World` | GitHub. |

Internally each repository is identified by a **slug** of
`<host>/<owner>/<repo>` (for example `gitlab.com/group/project`), so repos with
the same path on different hosts never collide.

## Using the dashboard

1. Open **Settings**: paste your GitHub and/or GitLab token (and set URLs for
   self-hosted hosts), choose a default agent and model, tweak the review prompt,
   and set any limits. Everything is saved to `data/settings.json`.
2. Add a repository in the sidebar.
3. Click **Sync PRs** to fetch the pull/merge requests, including their current
   open/closed/merged state.
4. Select a repository to filter, then use the **Open**, **Closed**, **Merged**
   and **All** tabs to pick the requests you want; click one to open it.
5. On the request page use the **Conversation**, **Commits** and **Files
   changed** tabs: read the description and comments, browse the commits, and
   review the diffs (switch between **Unified** and **Split** layouts).
6. Choose an agent and click **Run review**. Watch the timer and the **Logs**
   area while it runs, then read the review when it finishes. Earlier reviews
   are under **History**.

The sidebar can be resized by dragging the divider on its right edge. Double-click
the divider to reset it to the default width; the choice is saved in the browser.

## Watching for new pull requests

By default the app only fetches requests when you click **Sync PRs**. To be
alerted about new ones:

1. Click the bell (🔔) next to a repository in the sidebar. It is per
   repository and **off by default**; the icon dims when watching is off.
2. While the app is running, it re-checks watched repositories every
   **Watch interval** (Settings → Watching, default 60 seconds) and stores the
   requests it finds.
3. When a new request appears in a watched repository, the dashboard shows a
   toast linking to it and plays a short chime.
4. Watching also **starts a review automatically** for each new open request,
   using the repository's own settings (agent, model and limits) or the global
   ones. The review appears in the **AI Reviewed** list while it runs.
5. Requests you have **already reviewed** are reviewed again when their branch
   gains **new commits**. The app records the head commit a review ran against,
   and the next sync (the button or the background watcher) starts a fresh
   review if the head has moved on. This is not a new request, so it is not
   announced.

A request row shows the bell (🔔) beside its title when its repository is
watched, so you can tell which requests are kept current automatically.

Notes:

- A repository's **first** sync only establishes a baseline — the requests that
  already existed are stored without notifying or reviewing, so you are not
  flooded when you enable watching.
- A re-review happens only when the head commit actually changed. Editing the
  description or adding a comment does not trigger one.
- Revising a request several times between two syncs produces one re-review of
  its latest head, not one per commit. A request already under review is skipped
  until the running review finishes.
- Reviews created before this feature have no recorded head commit, so they are
  never used as a baseline: re-reviewing starts once you run a review again.
- Only **open** requests are announced and reviewed. Closed and merged requests
  are still stored so their status stays accurate, but they never alert or
  trigger a review.
- Automatic reviews need an agent that can actually run: the repository's
  configured agent, or the first installed one. When none is available, watching
  still notifies, but nothing is reviewed.
- Reviews for the same repository run one request at a time, so a burst of new
  requests is queued rather than checking out the same workspace concurrently.
- Browsers block sound until you interact with the page. Click anywhere once and
  the notification chime will play for subsequent new requests.
- The background watcher only polls watched repositories; unwatched ones are
  untouched until you sync manually.
- To stop automatic reviews, click the bell again to unwatch the repository.
  Reviews you already started keep running.

## Tracking AI-reviewed requests

The **AI Reviewed** section of the sidebar lists every request that has an agent
review, so you can follow progress without hunting for it:

1. Start a review on a request page. It appears in the list immediately.
2. The coloured dot and label show the latest review status — **Queued**,
   **Preparing**, **Running**, **Reviewed** or **Failed** — and update on their
   own (the list refreshes every 15 seconds). Running reviews pulse.
3. Click **×** next to an entry to remove it once you are done with it; you are
   asked to confirm first.

Notes:

- Membership is derived from the review history, so requests you reviewed before
  this list existed show up automatically.
- When a request you are tracking is **merged or closed** upstream, the next
  reload archives it for you — it leaves the list on its own with its review
  history intact. This happens on any sync (the **Sync PRs** button or the
  background watcher). Only the change to closed/merged counts: a request that
  was already finished when you reviewed it stays until you remove it.
- Removing an entry only hides it from the list; the review history is kept. Run
  a new review on the request and it reappears.
- Removing a repository (or deleting a request) removes its entries too.

## Review status API

Every completed review ends with a machine-readable verdict that the app parses
and stores: `REVIEW_VERDICT: PASS` or `REVIEW_VERDICT: FAIL`. The app appends
this instruction to **every** review prompt — the default one and any custom
template — and the verdict must be the **final line** of the agent's output. A
request's **latest** review decides its current verdict.

Other services can ask whether a pull/merge request passed over a small,
read-only API:

```bash
# by repository slug + number (the canonical <host>/<owner>/<repo> identity)
curl "http://localhost:5000/api/v1/reviews/status?repo=github.com/acme/api&number=42"

# by the app's internal request id
curl "http://localhost:5000/api/v1/reviews/status?pr_id=123"
```

The response reports `passed` (`true`/`false`/`null`), the `verdict`
(`passed`/`failed`/`unknown`), the latest review's run `status` and a summary:

```json
{
  "repo": "github.com/acme/api",
  "number": 42,
  "pr_id": 123,
  "title": "Add the widget",
  "state": "open",
  "url": "https://github.com/acme/api/pull/42",
  "passed": true,
  "verdict": "passed",
  "review_status": "done",
  "reviews": 3,
  "review": { "id": 7, "status": "done", "verdict": "passed", "agent": "opencode", "model": null }
}
```

`passed` is `true` on a PASS verdict, `false` on FAIL, and `null` when nothing is
decided yet (no review, a review still running, one that errored, or an agent
that emitted no marker). Because the marker must be the **last** line, an agent
that adds a closing remark *after* the verdict yields `unknown`; the instruction
asks it to end there. `GET /api/v1/reviews` lists reviewed requests and can be
filtered with `?repo=<slug>` and `?verdict=passed|failed|unknown` (`?limit=` caps
the list).

> **What `passed` means.** It is the reviewing *agent's opinion*, not a verified
> or security-grade signal. The agent reads content the pull/merge request author
> controls, so a crafted request can try to steer the agent or the marker. Use
> `passed` as a convenience gate, not as the only control before a merge.

Browse and try the API in the browser at **<http://localhost:5000/api/docs>**
(Swagger UI); the OpenAPI 3 document is served at `/api/v1/openapi.json`.

### Protecting the API

The API is open by default, which is fine when the app is only reachable from
your own machine. If you expose it on a network, set an **API token** under
**Settings → Server**. Callers must then send it, either way works:

```bash
curl -H "Authorization: Bearer <token>" "http://localhost:5000/api/v1/reviews?limit=10"
curl -H "X-API-Token: <token>" "http://localhost:5000/api/v1/reviews?limit=10"
```

The Swagger UI and the OpenAPI document stay reachable without the token so the
token can be entered in the UI's **Authorize** dialog; the data endpoints return
`401` until it is presented. Use the **Clear** button beside the field to remove
a saved token and return to the open default.

> **Scope:** the API token protects **only** the read-only `/api/v1` endpoints.
> The rest of the app — `/api/settings`, `/api/sync`, starting reviews,
> removing repositories and the web UI — is **not** covered by it. Do not expose
> the app to an untrusted network without separate protection (a firewall, a
> reverse proxy with authentication, or a VPN).

## Supported agents

The app detects these on `PATH`:

| Agent | Default command | Notes |
| --- | --- | --- |
| OpenCode | `opencode run --format default --auto [--model {model}] {prompt}` | Installed as `opencode`. |
| pi | `pi --print --mode text --no-session [--model {model}] {prompt}` | Installed as `pi`. |
| Claude Code | `claude --print --output-format text [--model {model}] {prompt}` | Installed as `claude`. |
| GitHub Copilot CLI | `copilot --allow-all-tools [--model {model}] --prompt {prompt}` | Installed as `copilot`. |

Each agent can be **detected** but its command line and binary are editable in
**Settings → Agents**, so you can add flags, point at a specific install, or use
a wrapper script. Leave a field empty to keep the built-in default.

Each agent runs with the checked-out workspace as its working directory and
inherits your environment, so it authenticates exactly as it does in your shell.

Command templates use shell-style splitting and these placeholders:

- `{prompt}` — the review prompt (appended automatically if omitted).
- `{model}` — the model you entered (empty if none).
- `[...]` — an optional group, dropped when a placeholder inside it is empty.
  This is why the model flag is written `[--model {model}]`.

### Listing available models

In **Settings → Agents → Available models** you can list the models an agent
reports and click one to use it as the default. The list comes from a per-agent
**Model command**:

| Agent | Default model command |
| --- | --- |
| OpenCode | `opencode models` |
| pi | `pi --list-models` |
| Claude Code | – (set one if your CLI supports it) |
| GitHub Copilot CLI | – |

Override the command in the **Model command** column, or set **Custom model
command** for the custom agent. The command's output can be one `provider/model`
per line or a table whose first two columns are `provider` and `model`; results
are cached for five minutes, and the **Refresh models** button forces a reload.

### Any other agent (custom command)

Set **Custom agent command** in Settings to a command template and choose the
*Custom command* agent. It uses the same placeholders and optional-group syntax,
for example `myagent review --prompt {prompt} [--model {model}]`. The command runs
in the checkout directory, so a plain `myagent {prompt}` works too.

## Configuration

Everything is configured in the web UI's **Settings** dialog and stored in
`data/settings.json`. No environment variables override these values — the app
reads only `DATA_DIR` from the environment, to locate `settings.json` before any
configuration can be loaded (default `./data`).

### Settings reference

| Tab | Setting | Default | Description |
| --- | --- | --- | --- |
| Providers | GitHub token | – | Personal access token for the GitHub API. |
| Providers | GitHub URL | `https://github.com` | Web/clone base; set your GitHub Enterprise URL if self-hosted. |
| Providers | GitHub API URL | derived | Override the REST API base (default `https://api.github.com`, or `<url>/api/v3` for Enterprise). |
| Providers | GitLab token | – | Personal access token (`PRIVATE-TOKEN`) for the GitLab API. |
| Providers | GitLab URL | `https://gitlab.com` | Default host for GitLab repos added as `owner/repo`. |
| Providers | GitLab API URL | derived | Override the API base (default `<host>/api/v4`). |
| Agents | Default agent | auto | Agent id to preselect (`opencode`, `pi`, `claude`, `copilot`, `custom`). |
| Agents | Default model | – | Model passed to the selected agent. |
| Agents | Custom command | – | Command template for the `custom` agent. |
| Agents | Command templates | built-in | Override any agent's command line. |
| Agents | Binaries | built-in | Override an agent's binary name/path (e.g. a wrapper script). |
| Agents | Model commands | built-in | Command used to list an agent's models (see below). |
| Prompt | Review prompt | built-in | The review prompt template (see below). |
| Limits | Review timeout | `900` | Seconds before a running agent is killed. |
| Limits | Max prompt characters | `400000` | Truncate the prompt before passing it to the agent. |
| Limits | Max description characters | `8000` | Truncate the request description inside the prompt (`0` = no limit). |
| Watching | Watch interval | `60` | Seconds between background checks of watched repositories (minimum 15). |
| Server | Bind host / port | `0.0.0.0` / `5000` | Where the web server listens; applied on the next restart. |
| Server | API token | – | Optional shared token required by the read-only `/api/v1` API. Empty means the API is open. |

### Review prompt

The review prompt is a template editable under **Settings → Prompt**. Available
placeholders:

`{kind}`, `{kind_title}`, `{provider}`, `{host}`, `{repo}`, `{number}`,
`{title}`, `{author}` (alias `{user}`), `{url}`, `{base_ref}`, `{head_ref}`,
`{body}` (the description, truncated to *Max description characters*), and
`{diff_command}` (a ready-to-run `git diff origin/<base>...HEAD`).

Use **Restore default** to go back to the built-in prompt.

### Per-repository settings

The global Settings act as defaults for every repository, but each repository
can override the review-related ones. Click the gear (⚙) next to a repository in
the sidebar to open its settings dialog; the gear is highlighted once a repo has
its own overrides.

These keys can be set per repository:

| Setting | Description |
| --- | --- |
| Review prompt | A prompt template just for this repo. |
| Agent | The agent to preselect here (`opencode`, `pi`, `claude`, `copilot`, `custom`). |
| Model | The model to preselect here. |
| Review timeout | Seconds before a running agent is killed. |
| Max prompt characters | Truncate the prompt before passing it to the agent. |
| Max description characters | Truncate the request description inside the prompt (`0` = no limit). |

A field is only stored when it differs from the global value: leave it empty (or
equal to the global value) and the repository inherits the global setting. The
dialog shows the global value as a hint and offers **Use global** and
**Built-in default** shortcuts for the prompt. Overrides are stored in the
`settings` column of the `repos` table. Invalid input (a non-numeric limit or an
unknown agent) is rejected with an error, and the review timeout is floored at
1 second.

Note that choosing the **Custom command** agent for a repository still uses the
global **Custom agent command**; only the choice of agent is per repository, not
the command template.

### Settings file

`data/settings.json` holds all of the above; the tokens are stored in plain text,
so keep the `data/` folder private. Example:

```json
{
  "github_token": "ghp_xxxxxxxxxxxx",
  "github_url": "https://github.com",
  "gitlab_token": "glpat-xxxxxxxxxxxx",
  "gitlab_url": "https://gitlab.example.com",
  "default_agent": "opencode",
  "default_model": "anthropic/claude-sonnet-4",
  "review_prompt": "",
  "review_timeout": 900,
  "max_prompt_chars": 400000,
  "max_description_chars": 8000,
  "watch_interval": 60,
  "agent_commands": { "opencode": "opencode run --format default --auto [--model {model}] {prompt}" },
  "agent_binaries": {},
  "agent_model_commands": { "opencode": "opencode models" },
  "host": "0.0.0.0",
  "port": 5000,
  "api_token": ""
}
```

An empty `review_prompt`, command template, or binary means "use the built-in
default".

## Data storage

```
data/
├── settings.json                 # app settings
├── pr_reviewer.db                # SQLite database (WAL mode)
├── pr_reviewer.pid               # pid file written by scripts/start.sh
├── pr_reviewer.log               # output of the background server
└── workspaces/
    └── <host>__<owner>__<repo>/  # git checkout used for reviews
```

| Table | Contents |
| --- | --- |
| `repos` | Watched repositories (`full_name`, `provider`, `host`, `slug`, `watch`, `settings`). |
| `pull_requests` | One row per PR/MR (slug, labels, draft, branches, head commit, diff stats, ...). |
| `comments` | Comments/notes (cascade-deleted with the request). |
| `reviews` | Agent reviews: agent, model, status, verdict, head commit reviewed, output, error, log, timing. |
| `dismissed_reviews` | Requests cleared from the **AI Reviewed** sidebar list. |
| `notifications` | New-request alerts for watched repositories (cascade-deleted with the request). |

Existing databases are migrated automatically on start (provider/host/slug are
backfilled). `data/` is gitignored. To reset, stop the app and delete the folder.

## API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Dashboard. Optional `?repo=<slug>` and `?state=open\|closed\|merged\|all`. |
| `GET` | `/pr/<id>` | Request detail page with the review panel. |
| `POST` | `/api/sync` | Fetch requests (open, closed and merged) from every repo now; new open requests in watched repos are reviewed automatically, watched requests whose head gained commits since their last review are reviewed again, and reviewed requests that finished are archived. |
| `GET` | `/api/prs` | Stored requests (optional `?repo=<slug>&state=<state>`). |
| `GET` | `/api/pr/<id>` | One stored request as JSON. |
| `GET` | `/api/pr/<id>/commits` | Commits in the request (live from the host). |
| `GET` | `/api/pr/<id>/files` | Changed files with unified diffs (live from the host). |
| `GET` | `/api/repos` | Repos with counts (slug, provider, host). |
| `POST` | `/api/repos` | Add repos: `{"repos": ["owner/repo"], "provider": "gitlab"}`. |
| `DELETE` | `/api/repos/<slug>` | Remove a repo and its data. |
| `POST` | `/api/repos/<slug>/watch` | Watch/unwatch a repo for new PRs: `{"watch": true}`. |
| `GET`/`POST` | `/api/repos/<slug>/settings` | Read/update per-repository settings overrides. |
| `GET` | `/api/notifications` | Stored new-PR notifications (`?unseen=1` for unseen only). |
| `POST` | `/api/notifications/seen` | Mark notifications seen: `{"ids": [1, 2]}` (all when omitted). |
| `GET` | `/api/providers` | GitHub/GitLab hosts, URLs and whether tokens are configured. |
| `GET` | `/api/agents` | Supported agents, availability, and effective command templates. |
| `GET` | `/api/agents/<id>/models` | Models an agent reports; `?refresh=1` bypasses the cache. |
| `POST` | `/api/pr/<id>/review` | Start a review: `{"agent": "...", "model": "..."}`. |
| `GET` | `/api/reviews/<id>` | Review status, output and live log. |
| `GET` | `/api/pr/<id>/reviews` | Review history for a request. |
| `GET` | `/api/reviewed` | AI-reviewed requests with their latest status (sidebar list). |
| `DELETE` | `/api/reviewed/<id>` | Remove a request from the AI-Reviewed list. |
| `GET`/`POST` | `/api/settings` | Read/update all settings (tokens are masked on read). |
| `GET` | `/health` | Status, request count, repo slugs, available agents. |
| `GET` | `/api/v1/reviews/status` | Whether a request passed its latest review: `?repo=<slug>&number=<n>` or `?pr_id=<id>`. |
| `GET` | `/api/v1/reviews` | Reviewed requests with verdicts: `?repo=<slug>&verdict=passed\|failed\|unknown&limit=<n>`. |
| `GET` | `/api/v1/openapi.json` | The OpenAPI 3 document for the v1 API. |
| `GET` | `/api/docs` | Interactive Swagger UI for the v1 API. |

The `/api/v1` endpoints are read-only and, when an **API token** is configured,
require it in `Authorization: Bearer <token>` or `X-API-Token`; the docs page and
the OpenAPI document never require it.

## Project structure

```
pr-reviewer/
├── app.py                 # Flask routes, provider sync, background watcher
├── providers.py           # GitHub + GitLab: parsing, API, clone/ref handling
├── storage.py             # SQLite + settings storage layer
├── agents.py              # Agent registry: detection + command templates
├── reviewer.py            # Workspace checkout + review orchestration
├── api.py                 # Public read-only v1 API + Swagger docs
├── openapi.json           # OpenAPI 3 description of the v1 API
├── requirements.txt
├── AGENTS.md              # Context + workflow for AI coding agents
├── specs/                 # Feature specifications (spec-driven development)
│   ├── README.md          # The workflow and the feature index
│   └── 0NN-feature/       # One folder per feature (spec.md, plan.md, tasks.md)
├── .specify/              # Constitution + spec/plan/tasks templates
│   ├── memory/constitution.md
│   └── templates/
├── tests/
│   ├── test_repo_settings.py     # Per-repository settings tests
│   ├── test_auto_review.py       # Automatic review of watched repos
│   ├── test_archive_reviewed.py  # Auto-archive of reviewed requests
│   ├── test_reviewer.py          # Review run outcome (done/error)
│   ├── test_review_logs.py       # Live timer and streaming logs
│   └── test_api.py               # Review-status API, verdict and Swagger docs
├── scripts/
│   ├── start.sh           # Start the server in the background
│   ├── stop.sh            # Stop it
│   ├── restart.sh         # Stop, then start
│   └── _common.sh         # Shared config/helpers for the scripts
├── templates/
│   ├── index.html         # Repo selector + request queue
│   └── pr_detail.html     # Request details + AI review panel
└── static/
    ├── theme.css          # Shared light/dark palette and base chrome
    ├── icon.svg           # App icon: pull request + review check (favicon + navbar)
    ├── favicon.ico        # Multi-size raster favicon served at /favicon.ico
    └── icon-180.png       # Rasterized icon (180x180) for iOS home-screen bookmarks
```

## Spec-driven development

New features are described in a specification under `specs/` before they are
built, and the spec ships with the code. The project's rules live in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md); the process
is documented in [`specs/README.md`](specs/README.md), and
[`AGENTS.md`](AGENTS.md) is the short version for AI coding agents.

The workflow, with a template for each step in `.specify/templates/`:

| Step | Produces |
| --- | --- |
| `/specify` | `specs/NNN-feature/spec.md` — prioritised user stories, requirements, success criteria |
| Clarify | resolved `[NEEDS CLARIFICATION]`s, checked against the review checklist |
| `/plan` | `specs/NNN-feature/plan.md` — approach, affected modules, constitution check |
| `/tasks` | `specs/NNN-feature/tasks.md` — ordered, independently testable tasks |
| Implement | code + tests on a feature branch, with the spec updated if behaviour diverged |
| Ship | a commit on the branch and a pull request — the default once the suite passes |

A new feature takes the next free number and a short kebab-case name, for
example `specs/007-review-priority-labels/`.

The first six specs (`001`–`006`) were **retrofitted** onto features that already
shipped, so they are the as-is baseline: status `Implemented`, each with an
*Implementation Notes* section mapping requirements to the code and tests. When
you change one of those features, update its spec in the same pull request.

## Troubleshooting

- **"No coding agent found"** — install `opencode`, `pi`, `claude` or `copilot`,
  or configure a custom command in Settings. Check `/api/agents`.
- **GitLab 401/403** — check the GitLab token and that it has `api`/`read_api`
  scope. For self-hosted instances, set the GitLab URL.
- **GitHub Enterprise 404/401** — set **GitHub URL** to your instance (and, if
  the API is not at `<url>/api/v3`, set **GitHub API URL** too).
- **GitLab 404** — the project path must be the full namespace, including
  subgroups (`group/sub/project`).
- **Agent returns an error / empty output** — run the same agent manually in a
  checkout to verify it is authenticated and works non-interactively.
- **Review times out** — raise **Review timeout** in Settings → Limits.
- **Clone fails** — check the token (private repos) and that `git` and network
  access are available. Errors are shown with the token redacted.
- **First review is slow** — the first run clones the whole repository into
  `data/workspaces`; later runs just fetch and check out.
- **Changes don't show up after editing** — restart the app (no auto-reload).
