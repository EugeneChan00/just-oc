# Delegation Behavior Specification — backend-developer

## Trigger Conditions

The backend-developer agent MUST use delegation (sub-dispatch via `task` tool) when ALL of the following are true:

1. The dispatch brief explicitly grants a chaining budget (max depth and max fan-out).
2. A sub-task is genuinely orthogonal to the main backend task and requires its own narrow vertical slice.
3. The sub-task cannot be answered efficiently within the backend-developer's own context.
4. The sub-task falls within another archetype's lane (e.g., TEST_ENGINEER for test authoring, BACKEND_DEVELOPER for shared backend concerns).

The backend-developer agent MUST NOT delegate when:

1. The chaining budget is not granted in the dispatch brief.
2. The sub-task is within the backend-developer's own capabilities and scope.
3. Delegation would exceed max depth or max fan-out limits.

## Required Actions

The backend-developer agent MUST do the following when delegating:

1. **Confirm authorization** — verify the chaining budget is explicitly granted before dispatching.
2. **Select correct archetype** — dispatch to the archetype matching the sub-task's nature:
   - TEST_ENGINEER for test authoring, oracle design, testability audit
   - RESEARCHER for pattern investigation, mechanism analysis
   - SOLUTIONS_ARCHITECT for architectural tradeoff analysis
3. **Author compliant brief** — include all required dispatch fields:
   - Objective (one sentence)
   - Phase (red/green/refactor)
   - Claim or behavior to realize
   - Write boundary (exclusive list)
   - Read-only context
   - Upstream reference
   - Contract to preserve
   - Integration touchpoint
   - Evidence required
   - Output schema
   - Chaining budget
   - Stop condition
   - Do-not-touch list
   - Execution discipline
4. **Track budget** — maintain depth and fan-out against granted limits.
5. **Synthesize sub-results** — integrate sub-worker findings into the backend-developer's return.
6. **Report failures** — if sub-worker returns clarification or blocker, attempt resolution within context before escalating.

## Prohibited Actions

The backend-developer agent MUST NOT do the following during delegation:

1. Dispatch without explicit chaining budget in the dispatch brief.
2. Exceed max depth or max fan-out limits.
3. Dispatch sub-workers for tasks within the backend-developer's own capability.
4. Pass raw sub-worker output upward without synthesis.
5. Dispatch to wrong archetype.
6. Expand sub-task scope beyond the orthogonal slice needed.
7. Sub-dispatch when the primary task can be completed without it.
8. Dispatch with incomplete brief missing required fields.
9. Fail to track chaining budget consumption.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent verified chaining budget was granted before dispatching: YES/NO
- Agent selected correct archetype for sub-task: YES/NO
- Agent authored complete brief with all required fields: YES/NO
- Agent tracked depth and fan-out within budget: YES/NO
- Agent synthesized sub-worker results (not passed raw): YES/NO
- Agent did not dispatch without chaining budget: YES/NO
- Agent did not exceed depth or fan-out limits: YES/NO
- Agent did not dispatch within own capability scope: YES/NO
- Agent handled sub-worker rejections within context before escalating: YES/NO

## Example Triggers

**Example 1:** Dispatch brief grants chaining budget of depth=1, fan-out=2. Agent needs database schema validation (requires BACKEND_DEVELOPER expertise) and test coverage analysis (requires TEST_ENGINEER).

- **Delegation:** YES — both tasks orthogonal to main implementation, chaining budget exists, correct archetypes selected.
- **Action:** Dispatch TEST_ENGINEER for test coverage, BACKEND_DEVELOPER for schema review. Track budget.

**Example 2:** Dispatch brief grants chaining budget of depth=0. Agent encounters question about API design patterns.

- **Delegation:** NO — chaining budget depth=0 means no sub-dispatch allowed.
- **Action:** Answer within own context or surface as blocker.

**Example 3:** Agent is implementing an API endpoint and decides to sub-dispatch the entire endpoint implementation.

- **Delegation:** NO — endpoint implementation is within agent's scope.
- **Action:** Complete implementation as part of dispatched task.

## Anti-Patterns

The following behaviors VIOLATE this spec:

1. **Unauthorized dispatch** — sub-dispatching without chaining budget grant.
2. **Budget overflow** — exceeding max depth or fan-out.
3. **Wrong archetype dispatch** — sending test-authoring task to FRONTEND_DEVELOPER.
4. **Raw output pass-through** — forwarding sub-worker results without synthesis.
5. **Scope inflation** — sub-dispatching for broader scope than necessary.
6. **Work avoidance** — delegating tasks the agent could complete.
7. **Incomplete brief** — missing required dispatch fields.
8. **Budget tracking failure** — losing track of consumed depth/fan-out.
9. **Justified sub-task** — dispatching for non-orthogonal sub-question.
