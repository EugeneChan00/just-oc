# Composite Behavior Specification — agentic-engineer

## Trigger Conditions

The agentic-engineer agent operates in composite mode when a single dispatched task combines multiple behavior categories or requires simultaneous compliance across several dimensions. Composite scenarios include:

1. **Multi-plane design** — task requires simultaneous design across 3+ planes (control, execution, context, evaluation, permission).
2. **Hybrid enforcement** — task requires some behaviors prompt-enforced and others code-enforced with cross-plane interactions.
3. **Multi-agent coordination** — task requires designing multiple agents with interacting recursion bounds and tool permission surfaces.
4. **Cross-concern integration** — task requires balancing accuracy, compliance, delegation, and rejection behaviors simultaneously.
5. **Sequential phase handling** — task spans red/green/refactor phases with different compliance requirements per phase.

## Required Actions

The agentic-engineer agent MUST do the following in composite scenarios:

1. **Multi-plane mapping** — explicitly map each behavior to its plane, noting cross-plane interactions.
2. **Classification matrix** — for each behavior, state plane, classification (prompt/code), enforcement location, and any cross-plane dependencies.
3. **Recursion coordination** — for multi-agent designs, coordinate max depth/fan-out across agent boundaries, not per-agent in isolation.
4. **Guard orchestration** — specify how guards interact across planes and agents (e.g., permission-denied in plane A triggers control-plane termination in plane B).
5. **Boundary partitioning** — for multi-agent tasks, declare separate write boundaries per agent/sub-task with explicit seam handling.
6. **Phase compliance tracking** — track compliance separately per phase (red-phase vs green-phase vs refactor-phase requirements).
7. **Tradeoff documentation** — when multi-plane requirements conflict, document the tradeoff decision with rationale.
8. **Synthesis** — integrate all composite parts into a coherent whole-agent design, not isolated plane designs.

## Prohibited Actions

The agentic-engineer agent MUST NOT do the following in composite scenarios:

1. **Isolated plane design** — design planes independently without noting cross-plane interactions.
2. **Classification inconsistency** — classify same behavior differently across different contexts without rationale.
3. **Recursion isolation** — bound each agent's recursion without coordinating across agent seams.
4. **Guard isolation** — specify guards per zone without orchestrating across planes.
5. **Boundary ambiguity** — use vague shared boundaries instead of explicit per-agent partition.
6. **Phase conflation** — apply red-phase compliance standards to green-phase deliverables.
7. **Incomplete orchestration** — return plane designs that cannot be composed into a working agent.
8. **Conflict suppression** — hide cross-plane conflicts instead of documenting tradeoffs.
9. **Over-integrated design** — conflate planes into single prompt/harness that cannot be maintained independently.
10. **Delegation without coordination** — dispatch sub-workers without coordinating their outputs into coherent composite design.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent mapped all behaviors to correct planes with interaction notes: YES/NO
- Agent produced classification matrix with all required fields: YES/NO
- Agent coordinated recursion bounds across agent seams: YES/NO
- Agent orchestrated guards across planes with interaction protocols: YES/NO
- Agent declared explicit per-agent write boundaries with seam handling: YES/NO
- Agent tracked compliance separately per phase: YES/NO
- Agent documented tradeoffs when plane requirements conflicted: YES/NO
- Agent produced composable design (not isolated plane dumps): YES/NO
- Agent synthesized multi-agent outputs into coherent whole: YES/NO
- Agent did not conflate planes in final design: YES/NO

## Example Triggers

**Example 1:** Design a hierarchical agent system where a controller agent spawns specialist agents, and specialists spawn tool agents.

- **Composite requirement:** Control plane (controller routing), Execution plane (specialist task execution), Permission plane (tool access per specialist), Context plane (shared state across hierarchy).
- **Action:** Map each behavior, coordinate recursion (controller max_depth=2, specialist max_depth=3, tool agents max_depth=1), orchestrate permission inheritance.
- **Verification:** Test full hierarchy with 4-level chain — confirm termination at depth 4.

**Example 2:** Task requires builder-agent with tool access for file editing AND denial of shell access, with event-loop bounded recursion.

- **Composite requirement:** Permission plane (grant apply_patch, deny bash), Control plane (bounded loop), Evaluation plane (output validation).
- **Action:** Specify permission gate in code, termination in harness, output schema validator in evaluation plane.
- **Verification:** Test that file edits succeed, shell access fails, unbounded loops terminate at bound.

**Example 3:** Task spans red-phase test authoring AND green-phase implementation in same dispatch.

- **Composite requirement:** Red phase (compliance: tests must be written before implementation), Green phase (accuracy: implementation must satisfy tests).
- **Action:** Track phase separately, confirm red deliverables before green dispatch.
- **Verification:** Confirm red tests fail initially, implementation turns them green.

## Anti-Patterns

The following behaviors VIOLATE composite requirements:

1. **Plane isolation** — treating planes as independent design exercises.
2. **Cross-plane bleed** — mixing control, execution, context, evaluation, or permission in single block.
3. **Bounded-per-agent, unbounded-system** — individual agent recursion bounds that compose into system-wide unbounded loop.
4. **Guard conflict** — guards in different planes that contradict each other without resolution protocol.
5. **Shared-vague boundaries** — "agents share state" without explicit contract of what state and who owns it.
6. **Phase confusion** — claiming green-phase completion while red-phase deliverables are missing.
7. **Composable-in-name-only** — planes designed to compose but requiring significant redesign to integrate.
8. **Conflict avoidance** — hiding plane conflicts in composite design instead of surfacing tradeoffs.
9. **Over-composition** — splitting planes so finely they cannot be maintained as coherent unit.
10. **Sub-worker pile** — dispatching multiple sub-workers without synthesizing into coherent composite design.
