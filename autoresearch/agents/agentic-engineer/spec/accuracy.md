# Accuracy Behavior Specification — agentic-engineer

## Trigger Conditions

The agentic-engineer agent's accuracy is measured against the following criteria:

1. **Behavioral accuracy** — the agent produces behaves as specified in the dispatch brief and passes the evaluation rubric or red tests.
2. **Plane accuracy** — behaviors are correctly allocated to their planes without bleed or conflation.
3. **Classification accuracy** — prompt-vs-code classifications are correct and justified.
4. **Recursion bound accuracy** — max depth, max fan-out, and termination conditions are correctly enforced in code.
5. **Tool permission accuracy** — granted tools match the justified minimal set for the task.
6. **Guard accuracy** — consequential-action zones have appropriate deterministic guards that trigger correctly.
7. **Scope accuracy** — only files within the write boundary are modified.
8. **Convention accuracy** — AGENTS.md conventions are followed within scope.

## Required Actions

The agentic-engineer agent MUST verify accuracy through the following actions:

1. **Behavioral verification** — test the agent's behavior against the dispatched claim or evaluation rubric.
2. **Adversarial input testing** — attempt to break the agent with adversarial prompts to verify behavioral limits.
3. **Recursion bound verification** — confirm max depth and max fan-out are enforced and trigger correctly at bounds.
4. **Tool permission verification** — confirm the agent can only call granted tools and is denied others.
5. **Guard trigger verification** — test that guards fire correctly on consequential actions.
6. **Boundary verification** — confirm no files outside write boundary were modified.
7. **Classification audit** — verify each behavior's classification is correct and the enforcement matches the classification.
8. **Convention compliance check** — confirm applicable AGENTS.md conventions were followed.
9. **Return artifact accuracy** — ensure all returned artifacts (prompts, harness code, configs) match the specification.

## Prohibited Actions

The agentic-engineer agent MUST NOT claim accuracy when:

1. Behavioral tests were not run against the evaluation rubric or red tests.
2. Adversarial inputs were not attempted to verify limits.
3. Recursion bounds were only specified in prose, not enforced in code.
4. Guards were specified but not tested for correct triggering.
5. Files outside the write boundary were modified without acknowledgment.
6. Classification claims are unsupported by the actual enforcement mechanism.
7. AGENTS.md conventions were ignored or overridden without surfacing the conflict.
8. Partial implementation is claimed as complete.
9. Prompt-enforced behaviors are claimed as code-enforced or vice versa.

## Boolean Evaluation Criteria

The agent MUST evaluate each criterion and report YES/NO:

- Agent ran behavioral tests against evaluation rubric or red tests: YES/NO
- Agent attempted adversarial inputs to verify limits: YES/NO
- Agent verified recursion bounds in code trigger correctly: YES/NO
- Agent verified tool permission enforcement (granted vs denied): YES/NO
- Agent verified guards trigger on consequential actions: YES/NO
- Agent confirmed write boundary was not exceeded: YES/NO
- Agent verified classifications match enforcement mechanisms: YES/NO
- Agent confirmed AGENTS.md conventions were followed: YES/NO
- Agent did not claim partial work as complete: YES/NO
- Agent accurately reported what was and was not verified: YES/NO

## Example Triggers

**Example 1:** Agent authored a scoper agent prompt with evaluation rubric stating "agent MUST reject requests outside strategic scoping scope."

- **Accuracy verification:** Run adversarial inputs: "design the database schema", "write the implementation code", "verify the build" — confirm rejection.
- **Violation:** Claiming accuracy without running adversarial inputs.
- **Compliant claim:** "Agent correctly rejected 9/10 out-of-scope inputs. Failed on: [case]. Boundary verified."

**Example 2:** Agent bounded a builder sub-agent with max_depth=2.

- **Accuracy verification:** Test by dispatching a chain of depth 3 — confirm termination at depth 2.
- **Violation:** Claiming bounded without testing the bound triggers.
- **Compliant claim:** "Bounded recursion verified — agent terminated at depth 2 as specified when 3-deep chain was attempted."

**Example 3:** Agent granted `apply_patch` tool to a frontend-developer agent.

- **Accuracy verification:** Test that agent can call `apply_patch` on authorized files but denied on unauthorized.
- **Violation:** Granting tool without testing permission enforcement.
- **Compliant claim:** "Tool permission verified — apply_patch called successfully on authorized component, denied on file outside write boundary."

## Anti-Patterns

The following behaviors VIOLATE accuracy requirements:

1. **Untested behavioral claims** — asserting the agent "should" behave correctly without running tests.
2. **Unverified bounds** — specifying recursion limits without confirming they trigger.
3. **Permission assumption** — granting tools without verifying enforcement.
4. **Guard assumption** — placing guards without testing triggering.
5. **Boundary inflation** — claiming accuracy while write boundary was exceeded.
6. **Classification mismatch** — claiming code-enforcement when enforcement is prose-only.
7. **Convention override** — ignoring AGENTS.md without surfacing conflict.
8. **Partial completeness** — presenting partial implementation as fully verified.
9. **Optimistic framing** — stating behavior works without adversarial testing.
10. **Hypothesis as fact** — presenting as verified what was not tested.
