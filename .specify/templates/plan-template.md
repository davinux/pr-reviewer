# Implementation Plan: [FEATURE NAME]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link to spec.md]

**Input**: Feature specification from `specs/[###-feature-name]/spec.md`

> This plan is produced by the `/plan` step. It turns an agreed spec into a
> concrete technical approach. It does not change *what* the feature does — that
> belongs in `spec.md`.

## Summary

[The primary requirement from the spec, plus the technical approach chosen to
meet it.]

## Technical Context

<!-- Fill in the values that apply to this project; keep NEEDS CLARIFICATION for
     anything genuinely undecided at planning time. -->

**Language/Version**: Python 3.9+ (project standard)

**Primary Dependencies**: Flask, `requests`, PyGithub (project standard)

**Storage**: SQLite (WAL) + `data/settings.json` in `DATA_DIR`

**Testing**: `unittest` (`python3 -m unittest discover -s tests`)

**Target Platform**: Local developer machine; server-rendered web UI

**Project Type**: Single-project web application

**Performance Goals**: [e.g. "a sync of N repositories completes without
blocking the UI"; "the list refreshes in < 1s"]

**Constraints**: [e.g. "no new external services"; "no build step"]

**Scale/Scope**: [e.g. tens of repositories, hundreds of requests]

## Constitution Check

*GATE: must pass before design. Re-check after the design below is complete.*

| Principle | Applies | How this plan complies |
| --- | --- | --- |
| I. Local-First & Private | [yes/no] | [e.g. "state stays in DATA_DIR; tokens redacted"] |
| II. Provider-Agnostic | [yes/no] | [e.g. "new field fetched through the provider surface"] |
| III. Agent-Agnostic | [yes/no] | [e.g. "no new agent-specific branching"] |
| IV. No Surprise Actions | [yes/no] | [e.g. "opt-in only; no background work without watching"] |
| V. Spec-First, Test-Supported | [yes/no] | [e.g. "extends tests/test_x.py"] |
| VI. Simple, Migratable Storage | [yes/no] | [e.g. "additive column + backfill"] |
| VII. Small Modules | [yes/no] | [e.g. "kept in providers.py; no new module needed"] |

Any **no** or partial answer is carried into *Complexity Tracking* with a
justification and the simpler alternative that was rejected.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── spec.md              # the feature specification
├── plan.md              # this file
├── research.md          # optional: decisions and options weighed
├── data-model.md        # optional: entities/schema changes
├── quickstart.md        # optional: how to exercise the feature
└── tasks.md             # the /tasks step output
```

### Source Code (repository root)

```text
app.py          # Flask routes, provider sync, background watcher
providers.py    # GitHub + GitLab: parsing, API, clone/ref handling
storage.py      # SQLite + settings storage layer
agents.py       # agent registry: detection + command templates
reviewer.py     # workspace checkout + review orchestration
templates/      # Jinja2 pages (index.html, pr_detail.html, _dialogs.html)
static/         # CSS + dependency-free JavaScript
tests/          # unittest suite
```

**Structure Decision**: [Which existing files change, and why no new module is
(or is) needed.]

## Complexity Tracking

> **Fill in only if the Constitution Check has violations to justify.**

| Violation | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| [principle / shortcut] | [current need] | [why the simpler option is insufficient] |

## Risks & Rollback

- **Risks**: [e.g. a schema change affecting existing databases.]
- **Rollback**: [e.g. "revert the commit; the additive column is ignored by the
  previous version".]
