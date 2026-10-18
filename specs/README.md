# Specifications

This folder holds the specifications that drive development of PR Reviewer. A
feature is described here **before** it is built, and the spec and the code ship
together.

The rules that govern the project live in
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Read it
first.

## Workflow

Spec-Driven Development moves a feature through five stages. Each stage has a
template in [`.specify/templates/`](../.specify/templates).

| Stage | Command | Produces | Template |
| --- | --- | --- | --- |
| 1. Specify | `/specify` | `specs/NNN-feature/spec.md` | `spec-template.md` |
| 2. Clarify | *(review)* | resolved `[NEEDS CLARIFICATION]`s | `checklist-template.md` |
| 3. Plan | `/plan` | `specs/NNN-feature/plan.md` | `plan-template.md` |
| 4. Tasks | `/tasks` | `specs/NNN-feature/tasks.md` | `tasks-template.md` |
| 5. Implement | *(coding)* | merged code + tests | — |

1. **Specify** — describe the *what* and *why*: prioritised user stories,
   functional requirements and measurable success criteria. No implementation
   detail.
2. **Clarify** — walk the checklist and remove ambiguity. No requirement is left
   with an unexplained placeholder.
3. **Plan** — describe the *how*: affected modules, the constitution check and
   any justified violations.
4. **Tasks** — break the plan into ordered, independently testable tasks.
5. **Implement** — work the tasks on a branch; add or extend tests; run
   `python3 -m unittest discover -s tests`.

A new feature gets the next free number and a short kebab-case name:

```text
specs/007-review-priority-labels/
├── spec.md
├── plan.md
└── tasks.md
```

`research.md`, `data-model.md` and `quickstart.md` are optional and added only
when they earn their place.

## Status

Each spec carries a status: `Draft` → `Clarified` → `Planned` → `In Progress` →
`Implemented` → `Superseded`.

## Index

| # | Feature | Status | Spec |
| --- | --- | --- | --- |
| 001 | Multi-host repositories (GitHub + GitLab) | Implemented | [spec](001-multi-host-repositories/spec.md) |
| 002 | Request list and status tabs | Implemented | [spec](002-request-status-tabs/spec.md) |
| 003 | Per-repository settings | Implemented | [spec](003-per-repository-settings/spec.md) |
| 004 | Watch and automatic review | Implemented | [spec](004-watch-and-auto-review/spec.md) |
| 005 | Agent review pipeline | Implemented | [spec](005-agent-review-pipeline/spec.md) |
| 006 | AI-reviewed tracking list | Implemented | [spec](006-ai-reviewed-list/spec.md) |

The first six specs were **retrofitted** onto features that already shipped, so
they are the as-is baseline: each has status `Implemented` and an *Implementation
Notes* section mapping requirements to the code and tests. New work starts from
the next free number and follows the full spec → plan → tasks flow.

## Retrofit note

A retrofitted spec reverses the usual direction: the code already exists and the
spec captures its behaviour. When you change a retrofitted feature, update its
spec in the same pull request so the baseline stays true.
