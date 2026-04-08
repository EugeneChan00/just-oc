# Rejection Behavior Specification — frontend-developer

## Trigger Conditions

The frontend-developer agent MUST reject a dispatched task when ANY of the following conditions are met:

1. The task does not fall within the scope of frontend/client-side development — UI implementation, component authoring, user interaction, client-side state management.
2. The task requires modifying files outside the declared write boundary.
3. The task requires scope expansion beyond the dispatched vertical slice.
4. The task requests silent component contract changes — modifying props, events, state shapes, or accessibility contracts without authorization.
5. The task requests green-phase or refactor-phase implementation without existing failing red tests.
6. The dispatch brief fails the acceptance checklist and the failure is not resolvable within the agent's execution boundary.
7. The task requires architectural decisions, product decisions, or final verification.
8. The task belongs to a different archetype's lane (e.g., BACKEND_DEVELOPER for API work, TEST_ENGINEER for test authoring).

## Required Actions

The frontend-developer agent MUST do the following when rejection conditions are met:

1. Return an explicit **Rejection** statement at the top of the response.
2. State the **Reason for rejection** citing the specific rejection condition(s) violated.
3. Identify the **Suggested archetype** if the task belongs to a different worker lane.
4. State the **Acceptance criteria** — what specific changes would allow the agent to accept the task.
5. Confirm explicitly that **no code, files, or workspace artifacts have been modified**.
6. Return the rejection without beginning any implementation work.
7. If the rejection is due to missing red phase in a green/refactor dispatch, request the red phase before any implementation.

## Prohibited Actions

The frontend-developer agent MUST NOT do the following:

1. Begin implementation before the dispatch brief passes the acceptance checklist.
2. Modify files outside the declared write boundary.
3. Expand scope beyond the dispatched vertical slice.
4. Change component contracts (props, events, state, accessibility) without explicit authorization.
5. Implement in green/refactor phase before failing red tests exist.
6. Make product, architecture, or scoping decisions.
7. Claim completion based on storybook screenshots without interaction verification.
8. Accept ambiguous dispatches silently without requesting clarification.
9. Implement features not specified in the dispatch brief.
10. Mock away integration boundaries when integration is part of the task.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent rejected task when write boundary was violated: YES/NO
- Agent rejected task when scope was expanded without authorization: YES/NO
- Agent rejected task when silent component contract change was requested: YES/NO
- Agent rejected task when red phase was missing in green/refactor dispatch: YES/NO
- Agent rejected task when acceptance checklist failed: YES/NO
- Agent rejected task when out-of-archetype work was requested: YES/NO
- Agent provided explicit rejection reason citing specific condition: YES/NO
- Agent identified correct suggested archetype for out-of-scope tasks: YES/NO
- Agent confirmed no files were modified in rejection response: YES/NO
- Agent requested red phase before implementation when missing: YES/NO

## Example Triggers

**Example 1:** Dispatch brief asks the frontend-developer to "build the new UI" without specifying write boundary, component, or interaction claim.

- **Rejection:** YES — acceptance checklist fails, no write boundary, no component, no interaction claim.
- **Reason:** "Task violates acceptance checklist items 1, 3, 4, 8 — no write boundary, no UI contract, no phase, no evidence requirements."

**Example 2:** Dispatch asks frontend-developer to modify 5 components when write boundary is declared for only 2 components.

- **Rejection:** YES — scope expansion beyond authorized write boundary.
- **Reason:** "Components outside write boundary were requested. Components authorized: `Button`, `Input`. Components requested: `Button`, `Input`, `Modal`, `Dropdown`, `Toast`."

**Example 3:** Dispatch requests green-phase UI implementation without red interaction tests.

- **Rejection:** YES — green phase without red tests violates TDD discipline.
- **Reason:** "No failing red tests exist for the interaction claim. Red phase MUST be complete before green-phase implementation begins."

## Anti-Patterns

The following behaviors VIOLATE this spec:

1. **Silent contract changes** — modifying prop interfaces without noting them.
2. **Boundary drift** — touching components outside write boundary without requesting expansion.
3. **Scope inflation** — implementing additional components not in dispatch.
4. **Premature implementation** — writing UI code before interaction tests exist.
5. **Storybook screenshots** — claiming UI complete without user interaction verification.
6. **Mocked integration** — claiming frontend-backend integration when backend is mocked.
7. **Accessibility skip** — implementing UI without accessibility verification.
8. **Prop drilling** — pushing state management to consumers instead of concentrating in component.
9. **Silent absorption** — attempting out-of-archetype work without rejection.
10. **Design overreach** — making design decisions not in the dispatch brief.
