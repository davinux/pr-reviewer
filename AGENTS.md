# AGENTS.md — working in the PR Reviewer repository

This file is the context an AI coding agent needs to work in this repo: what the
project is, how it is laid out, and the workflow every change follows. It
complements, and never overrides,
[`.specify/memory/constitution.md`](.specify/memory/constitution.md).

## What this project is

**PR Reviewer** is a local Flask app that reviews GitHub pull requests and GitLab
merge requests with an installed coding-agent CLI. It lists requests across the
repositories you configure — open, closed and merged — and on demand clones the
repository, checks out the request and runs an agent (opencode, pi, Claude Code,
GitHub Copilot, or a custom command) to produce a review you read in the browser.

Data stays on the machine except the GitHub/GitLab API calls and whatever the
chosen agent does. See `README.md` for the user-facing documentation.

## Layout

```text
app.py          # Flask routes, provider sync, background watcher
providers.py    # GitHub + GitLab: parsing, API, clone/ref handling
storage.py      # SQLite + settings storage layer
agents.py       # Agent registry: detection + command templates
reviewer.py     # Workspace checkout + review orchestration
templates/      # Jinja2 pages
static/         # CSS + dependency-free JavaScript
tests/          # unittest suite
scripts/        # start / stop / restart the background server
specs/          # feature specifications (the source of truth for behaviour)
.specify/       # constitution + spec/plan/tasks templates
```

## Run, test, restart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python3 app.py                       # run (serves http://localhost:5000)
python3 -m unittest discover -s tests  # tests
scripts/restart.sh                   # restart the background server
```

- The server runs with `debug=False` and does **not** reload on changes —
  restart it after editing source.
- Configuration lives in `data/settings.json`, not environment variables.
  `DATA_DIR` is the only environment variable read, and only to locate that file.
- Tests point `DATA_DIR` at a throwaway folder; never write to the real `data/`.

## Spec-Driven Development workflow

Behaviour is agreed in writing before it is coded. The rules are in the
constitution; the process is in [`specs/README.md`](specs/README.md).

1. **`/specify`** — create `specs/NNN-feature-name/spec.md` from
   `.specify/templates/spec-template.md`. Prioritised user stories, `FR-###`
   requirements, measurable success criteria. No implementation detail.
2. **Clarify** — walk `.specify/templates/checklist-template.md`; resolve every
   `[NEEDS CLARIFICATION]` before moving on.
3. **`/plan`** — create `plan.md` from `.specify/templates/plan-template.md`,
   including the **Constitution Check** and any justified violation.
4. **`/tasks`** — create `tasks.md` from
   `.specify/templates/tasks-template.md`, grouped by user story and ordered so
   each is independently testable.
5. **Implement** — work the tasks on a feature branch, add or extend tests, run
   the full suite, and update the spec if the implementation diverged.
6. **Ship** — once the full suite passes and the work matches the spec, commit
   on the branch and open a pull request. This is the **default**: do not wait to
   be asked to commit or to open the PR. Note the branch and PR in your summary.

The next free spec number is the one after the highest in `specs/` (currently
`007`, so a new feature is `008-`).

### Existing specs

Specs `001`–`006` were retrofitted onto already-shipped features and are the
as-is baseline (status `Implemented`, with an *Implementation Notes* section).
When you change one of those features, update its spec in the same pull request.

## House rules (from the constitution)

- **Local-first**: keep state in `DATA_DIR`; never add telemetry; redact tokens.
- **Provider-agnostic**: GitHub and GitLab behind one surface; identity is the
  `<host>/<owner>/<repo>` slug.
- **Agent-agnostic**: never hard-require a specific agent; drive CLIs through
  command templates.
- **No surprise actions**: reviews only on request, except explicitly watched
  repositories (per repository, off by default).
- **Tests**: `unittest`, network-free, `DATA_DIR` redirected.
- **Storage**: additive, self-healing migrations; cascade on deletes.
- **Small modules**: put a new concern in its own module rather than growing an
  existing one.
