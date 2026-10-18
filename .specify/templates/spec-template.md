# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`

**Created**: [DATE]

**Status**: Draft

**Input**: User description: "[what the feature should do]"

> **Status values**: `Draft` → `Clarified` → `Planned` → `In Progress` →
> `Implemented` → `Superseded`. Specs retrofitted onto already-shipped behaviour
> start at `Implemented` and add an *Implementation Notes* section (see below).

## User Scenarios & Testing *(mandatory)*

<!--
  User stories are PRIORITISED as user journeys ordered by importance. Each
  story must be INDEPENDENTLY TESTABLE: implementing just one of them still
  delivers a usable slice of value.

  Assign priorities (P1, P2, P3, ...), where P1 is the most critical. Each story
  is one standalone slice that can be developed, tested, deployed and
  demonstrated on its own.
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language.]

**Why this priority**: [The value it delivers and why it ranks here.]

**Independent Test**: [How to verify this story on its own, e.g. "Can be fully
exercised by <specific action> and delivers <specific value>".]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome].
2. **Given** [initial state], **When** [action], **Then** [expected outcome].

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language.]

**Why this priority**: [Reasoning.]

**Independent Test**: [How to verify this story on its own.]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome].

---

[Add more user stories as needed, each with a priority. Remove unused ones.]

### Edge Cases

<!-- Concrete boundary and error cases, not placeholders. -->

- What happens when [boundary condition]?
- How does the system handle [error scenario]?

## Requirements *(mandatory)*

<!--
  Functional requirements are precise and testable. Mark anything genuinely
  undecided with [NEEDS CLARIFICATION: the specific question], and resolve it
  before the spec moves past `Clarified`.
-->

### Functional Requirements

- **FR-001**: The system MUST [specific capability].
- **FR-002**: The system MUST [specific capability].
- **FR-003**: A user MUST be able to [key interaction].
- **FR-004**: The system MUST [data requirement].
- **FR-005**: The system MUST [behaviour / constraint].

*Example of an intentionally deferred decision:*

- **FR-006**: The system MUST [capability] via [NEEDS CLARIFICATION: the
  available options and the question to settle].

### Key Entities *(include when the feature involves data)*

- **[Entity 1]**: [What it represents and its key attributes, without
  implementation detail.]
- **[Entity 2]**: [What it represents and how it relates to other entities.]

## Success Criteria *(mandatory)*

<!--
  Measurable, technology-agnostic outcomes. Prefer a number or a clear pass/fail
  condition over an adjective.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g. "A user can ... in under 2 minutes".]
- **SC-002**: [Measurable metric, e.g. "The list shows the correct count for
  each state after a sync".]
- **SC-003**: [User-facing outcome, e.g. "A repository's setting change is
  visible without restarting the server".]

## Assumptions

<!--
  Reasonable defaults taken where the feature description was silent. Anything
  load-bearing here is worth confirming during clarification.
-->

- [Assumption about target users or environment.]
- [Assumption about scope boundaries.]
- [Dependency on an existing capability or service.]

## Implementation Notes *(for retrofitted specs only)*

<!--
  Present only when this spec documents behaviour that already ships. Maps the
  requirements above to the real code and tests, so future changes have an
  as-is baseline to diff against. Delete the whole section for a new feature.
-->

- **Modules**: [files that implement the behaviour.]
- **Tests**: [tests that cover it, or "none yet".]
- **Known limitations**: [anything the current implementation does not do.]
