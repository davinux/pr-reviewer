# Review Checklist: [FEATURE NAME]

**Purpose**: a requirements-quality gate to run against a `spec.md` before
planning. Use it to catch vague, missing or untestable requirements early.

**Scope**: [the spec being reviewed] | **Reviewed**: [DATE]

## Completeness

- [ ] Every functional requirement is numbered (`FR-###`) and testable.
- [ ] Every user story has a priority and at least one acceptance scenario.
- [ ] Edge cases are described with concrete conditions, not placeholders.
- [ ] Success criteria are measurable (a number or a clear pass/fail).
- [ ] Key entities are named where the feature touches stored data.

## Clarity

- [ ] No requirement says "should" where "MUST" is intended.
- [ ] No `[NEEDS CLARIFICATION: ...]` markers remain (or each is explicitly
  deferred with an owner).
- [ ] No implementation detail leaked into the spec (that belongs in `plan.md`).

## Consistency & Scope

- [ ] Requirements do not contradict each other or the constitution.
- [ ] The feature is scoped to one shippable increment.
- [ ] Stories are independently testable.

## Coverage

- [ ] Provider-agnostic behaviour is specified for both GitHub and GitLab.
- [ ] Agent-agnostic behaviour holds for any configured agent.
- [ ] Failure and empty states are covered (no data, API error, no agent).

## Notes

[Findings that must be resolved before the spec moves past `Clarified`.]
