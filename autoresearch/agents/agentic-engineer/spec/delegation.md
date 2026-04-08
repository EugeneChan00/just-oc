# Delegation Behavior Specification — agentic-engineer

## Trigger Conditions

The agentic-engineer agent MUST use delegation (sub-dispatch via `task` tool) when ALL of the following are true:

1. The dispatch brief explicitly grants a chaining budget (max depth and max fan-out).
2. A sub-task is genuinely orthogonal to the main agent-engineering task and requires its own narrow vertical slice.
3. The sub-task cannot be answered efficiently within the agentic-engineer's own context.
4. The sub-task falls within another archetype's lane (e.g., BACKEND_DEVELOPER for harness primitives, TEST_ENGINEER for behavioral test authoring).

The agentic-engineer agent MUST NOT delegate when:

1. The chaining budget is not granted in the dispatch brief.
2. The sub-task is within the agentic-engineer's own capabilities and scope.
3. Delegation would exceed max depth or max fan-out limits.

## Required Actions

The agentic-engineer agent MUST do the following when delegating:

1. **Confirm authorization** — verify the chaining budget is explicitly granted before dispatching.
2. **Select correct archetype** — dispatch to the archetype matching the sub-task's nature:
   - BACKEND_DEVELOPER for harness code, schema validation, tool wrapper implementation
   - TEST_ENGINEER for behavioral test authoring, oracle design, testability audit
   - RESEARCHER for prompt-engineering pattern investigation
3. **Author compliant brief** — include all required dispatch fields:
   - Objective (one sentence)
   - Exact question (single narrow task)
   - Slice boundary (what is in/out of scope)
   - Upstream reference
   - Evidence threshold
   - Output schema
   - Stop condition
   - Chaining budget (often zero for sub-dispatches)
   - Execution discipline
4. **Track budget** — maintain depth and fan-out against granted limits.
5. **Synthesize sub-results** — integrate sub-worker findings into the agentic-engineer's return to the lead.
6. **Report failures** — if sub-worker returns clarification or blocker, attempt resolution within context before escalating.

## Prohibited Actions

The agentic-engineer agent MUST NOT do the following during delegation:

1. Dispatch without explicit chaining budget in the dispatch brief.
2. Exceed max depth or max fan-out limits.
3. Dispatch sub-workers for tasks within the agentic-engineer's own capability.
4. Pass raw sub-worker output upward without synthesis.
5. Dispatch to wrong archetype (e.g., dispatching harness code task to FRONTEND_DEVELOPER).
6. Expand sub-task scope beyond the orthogonal slice needed.
7. Sub-dispatch when the primary task can be completed without it (delegation for work avoidance).
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

**Example 1:** Dispatch brief grants chaining budget of depth=1, fan-out=2. Agent encounters need for harness primitive implementation (requires BACKEND_DEVELOPER) and behavioral test (requires TEST_ENGINEER).

- **Delegation:** YES — both tasks are orthogonal to prompt authoring, chaining budget exists, correct archetypes selected.
- **Action:** Dispatch BACKEND_DEVELOPER for harness code, TEST_ENGINEER for behavioral tests. Track budget (depth=1 consumed, fan-out=2 used).

**Example 2:** Dispatch brief grants chaining budget of depth=0. Agent encounters question about prompt-engineering patterns.

- **Delegation:** NO — chaining budget depth=0 means no sub-dispatch allowed. Agent must answer within own context or surface blocker.
- **Action:** Surface as blocker in return — "Sub-task requires RESEARCHER but chaining budget depth=0 prevents sub-dispatch."

**Example 3:** Agent is asked to design event loop and decides to sub-dispatch the harness implementation.

- **Delegation:** NO — harness implementation is within agentic-engineer scope when event loop design is the dispatched task. Delegation would be work avoidance.
- **Action:** Complete harness implementation as part of the event-loop design task.

## Anti-Patterns

The following behaviors VIOLATE this spec:

1. **Unauthorized dispatch** — sub-dispatching without chaining budget grant.
2. **Budget overflow** — exceeding max depth or fan-out.
3. **Wrong archetype dispatch** — sending harness code task to FRONTEND_DEVELOPER instead of BACKEND_DEVELOPER.
4. **Raw output pass-through** — forwarding sub-worker results without integration synthesis.
5. **Scope inflation** — sub-dispatching for broader scope than necessary.
6. **Work avoidance** — delegating tasks the agent could complete.
7. **Incomplete brief** — missing required dispatch fields.
8. **Budget tracking failure** — losing track of consumed depth/fan-out.
9. **Unjustified sub-task** — dispatching for non-orthogonal sub-question.
