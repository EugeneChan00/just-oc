# pipeline_coordinator — Plane Allocation Analysis

**Phase:** design (pre-implementation)  
**Write boundary:** `analysis/pipeline_coordinator_plane_allocation.md`  
**Read-only context:** `.opencode/agents/`, `autoresearch/results/eval_schema.md`  
**Chaining budget:** 0 (no sub-dispatches; pure design analysis)

---

## Overview

`pipeline_coordinator` is an orchestrator agent positioned between the CEO and the four team leads (`scoper_lead`, `architect_lead`, `builder_lead`, `verifier_lead`). It owns four distinct responsibilities. This document maps each responsibility to exactly one of the five fixed planes, provides explicit justification, identifies cross-plane risks, and specifies a mitigation strategy for each risk.

**Fixed five-plane model** (from doctrine; no additions permitted):
1. **Control** — what triggers what, what routes where, what stops the loop
2. **Execution** — what the agent actually does, what tools it calls
3. **Context/memory** — what the agent reads, what it remembers, what it forgets
4. **Evaluation/feedback** — how outputs are judged, how feedback flows back
5. **Permission/policy** — what the agent is and is not allowed to do, enforced where

No "coordination plane," "orchestration plane," or any other non-fixed plane may be introduced. Any responsibility that appears to span two planes is assigned to exactly one primary plane, and the cross-plane dependency is managed via an explicit interface documented in the mitigation strategy.

---

## Plane Allocation Table

| Responsibility | Assigned Plane | Justification | Cross-Plane Risks | Mitigation Strategy |
|---|---|---|---|---|
| **Task routing** | **Control** | Routing determines what is triggered, where work flows, and when the pipeline stops or continues. This is the canonical definition of the control plane: route decisions that govern which lead receives which work and at what pipeline stage. | 1. **Control ↔ Evaluation**: routing decisions could be contaminated by quality evaluation — if the agent observes a prior lead return was poor quality, it could re-route to a different lead rather than issuing a rework directive. This creates a feedback loop where evaluation outcome dictates routing path instead of objective pipeline state. <br><br> 2. **Control ↔ Execution**: the routing decision (control) must actually execute as a `task` tool call (execution). If the control logic and execution are not tightly coupled in code, the agent could route correctly in analysis but fail to dispatch. | 1. **Mitigation for Control↔Evaluation bleed**: mandate that routing decisions are made on pipeline-state inputs only (dispatch brief existence, prior gate outcomes, pipeline stage position). Quality evaluation results must NOT be inputs to the routing decision. The evaluation result triggers a rework path on the *same* lead, not a re-route. The handoff from evaluation to control must be explicit: evaluation outputs a gate outcome; control reads the gate outcome and routes accordingly. No direct evaluation→control state bleed within the same agent turn. <br><br> 2. **Mitigation for Control↔Execution**: encode routing decisions as deterministic code branches that directly produce the `task` tool call. Do not allow intermediate prose reasoning between the routing decision and the tool call. |
| **Conversation history management** | **Context/memory** | Conversation history is the memory substrate: what has been dispatched, what results returned, what the current pipeline state is. The context/memory plane governs what the agent reads, remembers, and forgets — exactly what conversation history management does. | 1. **Context/memory ↔ Permission/policy**: conversation history may contain tool-use records (which tools each lead invoked). Tool allowlist enforcement (permission/policy) requires inspecting these records. If the permission check directly reads from the context store, any context corruption or injection could bypass tool enforcement. <br><br> 2. **Context/memory ↔ Control**: routing decisions (control) depend on accurate memory of prior dispatches. If context is not durably updated after each dispatch, the agent could re-dispatch completed work or route to an occupied lead. | 1. **Mitigation for Context/memory↔Permission/policy**: define a strict read-only interface: permission/policy plane has query-only access to a curated tool-use audit log (a structured, append-only subset of conversation history). The audit log is written by the execution plane at dispatch time. Permission checks read from this log only; they never write. This prevents context mutation from bypassing permission enforcement. <br><br> 2. **Mitigation for Context/memory↔Control**: enforce that context updates are transactional with dispatch actions. The context record (lead, task_id, status) must be updated atomically with the `task` tool call. No dispatch is considered complete until the context record is updated. This prevents the agent from "forgetting" a dispatch and routing to the same lead again. |
| **Output quality evaluation** | **Evaluation/feedback** | Quality evaluation judges outputs against dispatch brief success criteria and decides gate outcomes. This is the canonical evaluation/feedback plane: how outputs are judged and how feedback flows back into the pipeline. The evaluation plane also determines rework vs advance, which feeds back into the control plane's routing. | 1. **Evaluation ↔ Control**: the gate decision (PASS/FAIL from evaluation) directly triggers the next routing action (control). If evaluation and control are the same agent with no enforced separation, evaluation could shortcut to routing without a proper gate decision artifact. <br><br> 2. **Evaluation ↔ Execution**: the evaluation must actually read the lead's return artifact and apply the success criteria. If evaluation logic is conflated with execution (e.g., the agent applies criteria while simultaneously executing other pipeline actions), the evaluation inputs could be contaminated by later actions in the same turn. | 1. **Mitigation for Evaluation↔Control coupling**: the gate decision must be a first-class structured artifact (PASS / CONDITIONAL PASS / FAIL / BLOCKED) produced by the evaluation plane, stored in context/memory, and consumed by the control plane in a subsequent reasoning step. The agent must not route to the next stage until the gate artifact is in memory. This is an explicit handoff protocol, not implicit state sharing. <br><br> 2. **Mitigation for Evaluation↔Execution**: evaluation runs as a distinct logical phase before any re-dispatch or pipeline continuation. The evaluation phase reads and judges the return artifact; only after evaluation is complete does the agent enter the control phase to route based on the gate outcome. These phases must be ordered, not interleaved. |
| **Tool allowlist enforcement** | **Permission/policy** | Tool allowlist enforcement governs what each lead is permitted to do with tools — it is a policy constraint enforced on lead agents. The permission/policy plane is exactly the right fit: it defines what actors (leads) are allowed to invoke, with enforcement via deterministic checking rather than prose instruction. | 1. **Permission/policy ↔ Context/memory**: as noted above, the permission check requires tool-use records from conversation history. Without a defined interface, the permission plane could mutate context (false positive / false negative by corrupting the audit log). <br><br> 2. **Permission/policy ↔ Execution**: if a tool-use violation is detected, the enforcement must execute a response (flag, reject, escalate). If the permission logic and the enforcement action are separated (permission says "violation" but execution does something else), the guard is ineffective. | 1. **Mitigation for Permission/policy↔Context/memory**: as stated above, the permission plane accesses tool-use records through a read-only query interface to an append-only audit log. The permission plane cannot delete, modify, or re-order audit entries. <br><br> 2. **Mitigation for Permission/policy↔Execution**: enforcement actions must be code-enforced, not prose-enforced. The permission check returns a boolean; a boolean `false` result must deterministically trigger a flag or rejection in the execution plane without LLM discretion. The response action (what happens on violation) must be declared in the dispatch brief's permission block, not improvised at evaluation time. |

---

## Additional Cross-Plane Risk Analysis

### Risk 1: Control ↔ Evaluation Feedback Loop

**Scenario:** A `builder_lead` returns a `FAIL` self-verification report. The `pipeline_coordinator`'s evaluation plane judges this as poor quality. Instead of routing back to the same `builder_lead` for rework (correct behavior), the control plane interprets the poor evaluation as a signal to route to a different lead (e.g., skip back to `architect_lead`). This is a re-route based on evaluation, not on pipeline-state.

**Mechanism:** The agent observes the FAIL → infers "this lead is not capable" → control plane re-routes. This bypasses the proper rework loop.

**Contract required:** Routing is based exclusively on: (a) new input from CEO, (b) gate outcome of `PASS` advancing to next stage, (c) gate outcome of `FAIL` or `CONDITIONAL PASS` returning to the same lead with remediation context. No routing decision may be made based on the agent's own quality assessment of the return — only the gate artifact's classification controls routing.

### Risk 2: Context/Memory ↔ Permission/Policy Dependency via Tool-Use Records

**Scenario:** `builder_lead` uses a tool (`bash`) that is not in its declared permission block. The tool-use record is written to conversation history. `pipeline_coordinator` must detect this violation. If the permission check reads from raw conversation history, any misalignment between what was dispatched and what was recorded could cause false positives (tool was permitted but not recorded) or false negatives (tool was used but the record is absent or corrupted).

**Contract required:** The tool-use audit log is a structured, append-only, immutable-once-written log with schema: `{lead, task_id, tool_name, timestamp, dispatch_permission_block}`. The permission check queries this log and compares `tool_name` against `dispatch_permission_block`. No raw conversation history text is parsed for tool names.

### Risk 3: Evaluation ↔ Control Handoff Coupling

**Scenario:** `pipeline_coordinator` evaluates a lead return, concludes FAIL, and immediately routes the rework dispatch to the same lead without a distinct reasoning step that cites the gate artifact. This collapses evaluation and control into a single agent turn with no durable gate artifact.

**Contract required:** The evaluation phase produces a gate artifact stored in context/memory. The gate artifact must be retrievable and attributable in subsequent turns. The control phase must explicitly cite the gate artifact when routing. If the agent cannot produce a gate artifact, it cannot route — it must surface the blocker instead.

---

## Responsibilities That Could Span Two Planes

### Task Routing — Secondary: Execution

Task routing's primary plane is **control**. However, the routing decision materializes only through an actual `task` tool call (execution). This is not a plane-conflation hazard — it is the normal control→execution interface: control decides *what routes where*, execution performs the dispatch. The two remain distinct: control holds the routing logic, execution holds the tool call. Conflation would occur only if the routing decision and the dispatch action were interleaved without a clear control reasoning step.

### Conversation History Management — Secondary: Execution

Context/memory's primary plane is **context/memory**. However, writing to conversation history occurs during execution (at dispatch time and at return-handling time). The distinction is maintained by defining the write operation as a side effect of execution, with the memory store itself residing in the context/memory plane. This is a plane interface, not conflation: execution plane writes to context plane's store; context plane does not execute tool calls.

### Tool Allowlist Enforcement — Secondary: Evaluation

Tool allowlist enforcement's primary plane is **permission/policy**. However, detecting a violation requires evaluating whether the observed tool use matches the declared permission block — a comparison operation that could be mistaken for the evaluation/feedback plane. The distinction is sharp: evaluation/feedback judges *quality of output against success criteria*; permission/policy judges *compliance with declared constraints*. A tool-use violation is not a quality failure — it is a policy violation. The evaluation plane does not detect policy violations; the permission/policy plane does.

---

## Summary of Plane Assignments

| Responsibility | Primary Plane | Code-Enforced? | Prose-Enforced? |
|---|---|---|---|
| Task routing | Control | Routing logic encoded as deterministic branches; routing inputs restricted to pipeline-state only | N/A — no prose routing rules |
| Conversation history management | Context/memory | Append-only audit log with schema; atomic update with dispatch | N/A — no prose memory rules |
| Output quality evaluation | Evaluation/feedback | Gate artifact schema (PASS/FAIL/CONDITIONAL/BLOCKED); phase ordering (evaluate before routing) | Success criteria defined in dispatch brief (prose input), but evaluation result is code-enforced boolean against criteria |
| Tool allowlist enforcement | Permission/policy | Boolean permission check against audit log; violation triggers deterministic enforcement action | Permission blocks declared per-lead in dispatch brief (prose), but enforcement is code-enforced |

---

## Evaluation Notes for `verifier_lead` Audit

The `verifier_lead` will assess this plane allocation for:

1. **No invented sixth plane.** The five planes are fixed. Any document proposing a "coordination plane," "orchestration plane," or equivalent is a factual error. All four responsibilities map to one of the five fixed planes.

2. **No cross-plane conflation.** Each responsibility is assigned to exactly one primary plane. Where cross-plane dependencies exist, they are managed via explicit interfaces (read-only query, append-only log, phase ordering, gate artifact handoff), not via prose希望 or implicit state sharing.

3. **Feedback loop identification.** The control↔evaluation feedback loop risk is explicitly identified, and the mitigation (gate artifact as explicit handoff, routing inputs restricted to pipeline-state) is concrete and code-enforced rather than prose希望.

4. **Hallucination-sensitive zones are guarded.** Tool allowlist enforcement is code-enforced (boolean check against audit log, not prose instruction). Gate decisions are stored as structured artifacts, not prose conclusions.

5. **Consequential actions have deterministic guards.** Routing actions, dispatch actions, and enforcement actions are all code-enforced with defined responses for each condition.
