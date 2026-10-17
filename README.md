# PR Reviewer

Review **GitHub pull requests** and **GitLab merge requests** with a local
coding agent. PR Reviewer lists the requests across the repositories you care
about — open, closed and merged — and on demand it clones the repository, checks
out the request, and runs an installed agent CLI
([opencode](https://opencode.ai), `pi`, Claude Code, GitHub Copilot, or a custom
command) to produce a review you can read in the browser.

There is no automatic review: reviews run only when you ask for them. Data stays
on your machine except the GitHub/GitLab API calls and whatever your chosen
agent does.

## Features

- **GitHub and GitLab** — add repositories from either host (including
  self-hosted GitLab). The same `owner/repo` on two hosts is kept distinct.
- **Any installed agent** — detects `opencode`, `pi`, `claude` and `copilot`,
  and lets you run whichever is present. A **custom command** option covers any
  other CLI.
- **Selectable repositories** — pick a repo from the sidebar to see just its
  requests, or "All repositories".
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
- **AI Reviewed list** — the sidebar tracks every reviewed pull/merge request
  with its latest status, and you can clear the ones you are done with.
- **Local storage** — repositories, requests, comments and reviews live in
  SQLite under a single `data/` folder.
- **Sync on demand** — a button fetches requests from the hosts when asked,
  including their current open/closed/merged state.
- **Watch for new PRs** — optionally watch individual repositories; new
  pull/merge requests show a notification and play a short sound.
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
   history of previous reviews.

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
6. Choose an agent and click **Run review**. Watch the status until it
   finishes, then read the review. Earlier reviews are under **History**.

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

Notes:

- A repository's **first** sync only establishes a baseline — the requests that
  already existed are stored without notifying, so you are not flooded when you
  enable watching.
- Only **open** requests raise a notification. Closed and merged requests are
  still stored so their status stays accurate, but they never alert.
- Browsers block sound until you interact with the page. Click anywhere once and
  the notification chime will play for subsequent new requests.
- The background watcher only polls watched repositories; unwatched ones are
  untouched until you sync manually.

## Tracking AI-reviewed requests

The **AI Reviewed** section of the sidebar lists every request that has an agent
review, so you can follow progress without hunting for it:

1. Start a review on a request page. It appears in the list immediately.
2. The coloured dot and label show the latest review status — **Queued**,
   **Preparing**, **Running**, **Reviewed** or **Failed** — and update on their
   own (the list refreshes every 15 seconds). Running reviews pulse.
3. Click **×** next to an entry to remove it once you are done with it.

Notes:

- Membership is derived from the review history, so requests you reviewed before
  this list existed show up automatically.
- Removing an entry only hides it from the list; the review history is kept. Run
  a new review on the request and it reappears.
- Removing a repository (or deleting a request) removes its entries too.

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

### Review prompt

The review prompt is a template editable under **Settings → Prompt**. Available
placeholders:

`{kind}`, `{kind_title}`, `{provider}`, `{host}`, `{repo}`, `{number}`,
`{title}`, `{author}` (alias `{user}`), `{url}`, `{base_ref}`, `{head_ref}`,
`{body}` (the description, truncated to *Max description characters*), and
`{diff_command}` (a ready-to-run `git diff origin/<base>...HEAD`).

Use **Restore default** to go back to the built-in prompt.

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
  "port": 5000
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
| `repos` | Watched repositories (`full_name`, `provider`, `host`, `slug`, `watch`). |
| `pull_requests` | One row per PR/MR (slug, labels, draft, branches, diff stats, ...). |
| `comments` | Comments/notes (cascade-deleted with the request). |
| `reviews` | Agent reviews: agent, model, status, output, error, timing. |
| `dismissed_reviews` | Requests cleared from the **AI Reviewed** sidebar list. |
| `notifications` | New-request alerts for watched repositories (cascade-deleted with the request). |

Existing databases are migrated automatically on start (provider/host/slug are
backfilled). `data/` is gitignored. To reset, stop the app and delete the folder.

## API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Dashboard. Optional `?repo=<slug>` and `?state=open\|closed\|merged\|all`. |
| `GET` | `/pr/<id>` | Request detail page with the review panel. |
| `POST` | `/api/sync` | Fetch requests (open, closed and merged) from every repo now. |
| `GET` | `/api/prs` | Stored requests (optional `?repo=<slug>&state=<state>`). |
| `GET` | `/api/pr/<id>` | One stored request as JSON. |
| `GET` | `/api/pr/<id>/commits` | Commits in the request (live from the host). |
| `GET` | `/api/pr/<id>/files` | Changed files with unified diffs (live from the host). |
| `GET` | `/api/repos` | Repos with counts (slug, provider, host). |
| `POST` | `/api/repos` | Add repos: `{"repos": ["owner/repo"], "provider": "gitlab"}`. |
| `DELETE` | `/api/repos/<slug>` | Remove a repo and its data. |
| `POST` | `/api/repos/<slug>/watch` | Watch/unwatch a repo for new PRs: `{"watch": true}`. |
| `GET` | `/api/notifications` | Stored new-PR notifications (`?unseen=1` for unseen only). |
| `POST` | `/api/notifications/seen` | Mark notifications seen: `{"ids": [1, 2]}` (all when omitted). |
| `GET` | `/api/providers` | GitHub/GitLab hosts, URLs and whether tokens are configured. |
| `GET` | `/api/agents` | Supported agents, availability, and effective command templates. |
| `GET` | `/api/agents/<id>/models` | Models an agent reports; `?refresh=1` bypasses the cache. |
| `POST` | `/api/pr/<id>/review` | Start a review: `{"agent": "...", "model": "..."}`. |
| `GET` | `/api/reviews/<id>` | Review status/output. |
| `GET` | `/api/pr/<id>/reviews` | Review history for a request. |
| `GET` | `/api/reviewed` | AI-reviewed requests with their latest status (sidebar list). |
| `DELETE` | `/api/reviewed/<id>` | Remove a request from the AI-Reviewed list. |
| `GET`/`POST` | `/api/settings` | Read/update all settings (tokens are masked on read). |
| `GET` | `/health` | Status, request count, repo slugs, available agents. |

## Project structure

```
pr-reviewer/
├── app.py                 # Flask routes, provider sync, background watcher
├── providers.py           # GitHub + GitLab: parsing, API, clone/ref handling
├── storage.py             # SQLite + settings storage layer
├── agents.py              # Agent registry: detection + command templates
├── reviewer.py            # Workspace checkout + review orchestration
├── requirements.txt
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
