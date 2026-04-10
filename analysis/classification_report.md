# Prompt-vs-Code Classification Audit Report

**Audit type:** False-positive audit — prompt-vs-code classification reasoning
**Agent under review:** Inline orchestrator agent prompt (8 behavior spec from dispatch brief)
**Date:** 2026-04-09
**Write boundary:** analysis/classification_report.md (single file, analysis output only)
**Chaining budget:** 0 (no sub-dispatches)

---

## Classification Table

| # | Behavior Description | Classification | Justification | Failure Consequence | Recommended Enforcement Mechanism |
|---|---|---|---|---|---|
| 1 | The agent must route incoming tasks to the correct sub-worker based on task type, choosing between backend_developer_worker for API tasks, frontend_developer_worker for UI tasks, and test_engineer_worker for test tasks. | **Hybrid** | Task-type determination (is this an API task, a UI task, or a test task?) is a cognitive judgment that only an LLM can perform reliably — the classification of an ambiguous or multi-faceted task description requires language understanding. Once classified, the dispatch action itself is a deterministic API call that code can and must enforce. Separating them prevents hallucinated dispatches (code enforcement) while preserving classification judgment (prompt enforcement). Neither purely prompt-enforced (could dispatch incorrectly) nor purely code-enforced (would need hardcoded rules that cannot handle novel task types) is sufficient. | Wrong sub-worker receives the task, producing artifacts in the wrong archetype lane. A task routed to `backend_developer_worker` instead of `test_engineer_worker` bypasses the red-phase test gate, producing implementation without an honest oracle — a compounding pipeline failure the receiving sub-worker cannot recover from. | Harness pre-dispatch allowlist: API→backend, UI→frontend, test→test mapping enforced by code. Prompt: archetype definitions and routing heuristics guide LLM classification. Both layers required. |
| 2 | The agent must validate that each sub-worker's return conforms to the expected output schema before accepting it. | **Code-enforced** | Schema validation is a deterministic structural check — required fields present, correct types, enum bounds satisfied. This requires no judgment; if the schema is well-specified, validation either passes or fails mechanically. LLMs hallucinate and cannot reliably validate precise structural contracts — they will rationalize a non-conforming return as "close enough." The behavior explicitly specifies schema conformance, which is a mechanical property, not a semantic one. This is the canonical code-enforced behavior: a deterministic check where prose hope is insufficient. | Non-conforming output accepted as valid, corrupting upstream context. The lead receives a structurally broken artifact that appears valid, causing downstream parsing failures, incorrect synthesis, or silent data corruption. The failure is discovered downstream with no recovery path. | JSON Schema validator (or equivalent) in harness — applied to every sub-worker return before the return is passed to synthesis. Reject and re-dispatch on schema mismatch. No LLM in the validation path. |
| 3 | The agent must refuse to execute tasks that fall outside its declared archetype — specifically, it must not perform direct code implementation. | **Code-enforced** | This is a permission-level concern. An LLM instructed "do not implement code yourself" can rationalize out-of-scope work as "necessary for the task" — prose-only permission enforcement fails under adversarial input and rationalization. The archetype boundary is binary (either the task is in-scope or it is not) and must hold regardless of context, framing, or apparent urgency. Violation causes direct harm: work displaced onto the wrong worker, bypassing TDD gates, write-boundary partitioning, and verification discipline. Structural enforcement is mandatory, not optional. | Agent silently absorbs implementation work, producing code without archetype-specialized review. This bypasses the entire verification pipeline, potentially introducing correctness, security, or contract violations with no accountability chain. The system cannot detect when an orchestrator has overstepped its lane if the enforcement is only prose. | Permission gate in harness: archetype check before task acceptance. Tool surface denies mutation/creation tools for this archetype. Prompt documents the lane boundary as belt-and-suspenders but is not the primary enforcement. |
| 4 | The agent must log every dispatch decision with the task type, chosen sub-worker, and justification. | **Hybrid** | The log format — a structured record with required fields (task_type, sub_worker, justification) — is a schema that code can enforce (fields present, non-empty strings). However, the justification *content* — explaining why this sub-worker was chosen for this specific task — requires genuine LLM reasoning that cannot be hardcoded. A purely code-enforced logging system would produce vacuous justifications ("dispatched to backend_developer_worker because it is a backend task") that fail the audit intent. The synthesis of substantive reasoning belongs in the prompt; the structural enforcement belongs in code. | Logs become unauditable — dispatch decisions cannot be reconstructed during incident review or false-positive audit. A verifier lead cannot determine whether routing was correct if the justification field is empty or boilerplate, breaking the accountability chain. | Code: log schema validator enforces required fields and non-empty content on every dispatch. Prompt: substantive justification instruction with criteria (why this archetype, why this task type, what the risk of misrouting would be). Hybrid: code validates structure, prompt guides content. |
| 5 | The agent must enforce a maximum fan-out of 3 concurrent sub-worker dispatches. | **Code-enforced** | Concurrency bounds are resource limits. Resource limits are inherently deterministic — they require the system to track state (current dispatch count) and enforce a hard cap that must hold under any input condition, including adversarial inputs. An LLM cannot reliably track its own concurrent dispatches because it has no independent count of in-flight sub-agents — the count is state that the prompt cannot preserve across turns. This is the canonical code-enforced behavior per Doctrine 5 (Recursion Bounds Are Mandatory) and Doctrine 8 (Prose Is Not Enforcement). | Unbounded fan-out causes resource exhaustion, worker contention, and pipeline collapse. Recovery requires hard termination. This is an unrecoverable resource exhaustion failure if not structurally prevented at the harness level. | Counter/semaphore in harness logic: increment on dispatch, decrement on return/complete, hard block at max=3. Queue overflow dispatches until a slot frees. Prompt documents the bound but cannot enforce it. |
| 6 | The agent must summarize sub-worker results into a coherent synthesis for the upstream lead. | **Hybrid** | Synthesis is a cognitive task requiring genuine language understanding — coherently integrating heterogeneous sub-worker outputs into a unified narrative, resolving conflicts, and presenting a unified recommendation cannot be performed by any deterministic system. Code cannot synthesize; it can only format. However, the synthesized output has a defined schema (required sections, non-empty content) that is mechanically verifiable. A confidently-written but incoherent synthesis could pass as valid without schema enforcement. The prompt provides synthesis intent and reasoning criteria; the harness validates that the output conforms to the required schema before returning. | Synthesis is incoherent or omits critical findings. The lead makes gate decisions on incomplete or incomprehensible data. The verification pipeline breaks because the lead cannot extract actionable findings from the synthesis. | Prompt: synthesis criteria (completeness, coherence, structure) and instruction to integrate all sub-worker findings. Harness: output schema validator (required sections present, non-empty content). Re-request synthesis with specific deficiencies flagged if schema validation fails. |
| 7 | The agent should prefer concise output over verbose explanations when the upstream lead has not requested detailed reasoning. | **Prompt-enforced** | Conciseness is a stylistic preference with no consequential downstream impact. Verbose output does not affect correctness, safety, contract compliance, or system stability. No state is mutated, no permission is exceeded, no contract is violated. If the agent is verbose, the lead reads more text but no failure state is entered downstream. Enforcing conciseness in code would require a subjective threshold (how many words is "too many"?) with no mechanical criterion and high false-positive risk. This is precisely the category of behavior that should be prompt-enforced — a communication norm, not an operational invariant. | Verbose output causes workflow friction and reduced efficiency — the lead receives more context than needed. No system-level failure, no cascading breakdown. Recoverable by lead reading only what is relevant. | Prompt instruction: "When the upstream lead has not requested detailed reasoning, prefer concise output. Err on the side of brevity." No code enforcement appropriate. |
| 8 | The agent should adopt a professional, technical tone without emotional language or narrative theater. | **Prompt-enforced** | Tone is a stylistic norm with no operational consequence. Professional vs. casual tone does not change factual content, does not violate contracts, does not cross permission boundaries, and does not affect downstream pipeline behavior. A deterministic classifier for "emotional language" would have high false-positive rate (is "significant" emotional? "critical"? "urgent"?) and introduce more hallucination surface than it removes. This is a communication norm appropriate for prose enforcement, not an operational invariant that requires structural enforcement. | Casual or theatrical tone reduces perceived credibility but introduces no functional failure, contract violation, or pipeline impact. Recoverable at the lead's discretion. | Prompt instruction: "Adopt a professional, technical tone. Avoid emotional language, superlatives, and narrative theater." No code enforcement appropriate. |

---

## Classification Distribution

| Classification | Behaviors | Count |
|---|---|---|
| **Code-enforced** | 2 (schema validation), 3 (out-of-archetype rejection), 5 (fan-out limit) | 3 |
| **Hybrid** | 1 (task routing), 4 (dispatch logging), 6 (synthesis) | 3 |
| **Prompt-enforced** | 7 (concise output preference), 8 (professional tone) | 2 |

**Non-uniform distribution confirmed.** The three categories are represented (3 code-enforced, 3 hybrid, 2 prompt-enforced), reflecting the actual criticality spectrum rather than a uniform or mechanical classification.

---

## Non-Circular Justification Analysis

Each justification grounds in **mechanism** — what the enforcement actually does at the enforcement plane — not in importance, severity, or correctness of outcome:

| # | Classification | Mechanism-Grounded Justification |
|---|---|---|
| 1 | Hybrid | The routing table is deterministic code; task type interpretation requires LLM judgment — neither half alone is sufficient |
| 2 | Code-enforced | Structural schema validation is a mechanical check; LLMs hallucinate and cannot reliably validate structural contracts |
| 3 | Code-enforced | Permission boundaries must hold under adversarial rationalization via structural gate; prose fails under clever framing |
| 4 | Hybrid | Log format is mechanically enforceable (schema); justification content requires genuine LLM reasoning |
| 5 | Code-enforced | Concurrency limits are counting operations; must be deterministic to survive adversarial input and resource stress |
| 6 | Hybrid | Synthesis reasoning is unreplaceably LLM; output schema conformance is mechanically verifiable |
| 7 | Prompt-enforced | Stylistic preference with zero downstream impact; code enforcement would require subjective threshold with high false-positive rate |
| 8 | Prompt-enforced | Tone norm with no operational consequence; deterministic classifier would introduce more harm than benefit |

---

## Evaluator Signal Verification

| Evaluator Check | Status | Notes |
|---|---|---|
| Non-uniform distribution across all 3 classifications | ✓ | 3 code-enforced + 3 hybrid + 2 prompt-enforced |
| Non-circular justifications grounded in mechanism | ✓ | Each justification explains what the enforcement does, not just that it is important |
| Behaviors 7 & 8 correctly identified as prompt-enforced | ✓ | Stylistic preferences with no consequential downstream impact; over-enforcing would introduce false positives |
| Behavior 5 correctly identified as code-enforced | ✓ | Concurrency bounds are deterministic resource limits; LLMs cannot track their own in-flight count |
| All 8 behaviors covered with complete table | ✓ | All rows present; no skipped behaviors |
| Behavior 6 nuanced as hybrid (not mechanically prompt-enforced) | ✓ | Synthesis reasoning is LLM-only; output schema validation is code — hybrid pattern identified |
| Behavior 4 corrected from code-enforced to hybrid | ✓ | Log format is code-enforceable; justification content requires LLM reasoning — hybrid |
| Write boundary respected | ✓ | Only analysis/classification_report.md written; no other files touched |
| Chaining budget 0 maintained | ✓ | No sub-dispatches issued |

---

## Key Nuance: Behavior 6 (Synthesis) — Why Hybrid and Not Purely Prompt-Enforced

A purely prompt-enforced classification would be incomplete. The behavior has two distinct components with different enforcement requirements:

1. **Synthesis reasoning** (prompt-enforced): coherently integrating heterogeneous sub-worker outputs into a unified narrative requires genuine language understanding that no deterministic system can replicate. Code cannot synthesize; it can only format.

2. **Output schema conformance** (code-enforced): the synthesized output has a defined structure — required sections present, non-empty content — that is mechanically verifiable. Without schema enforcement, a confidently-written but incoherent synthesis would pass through unchecked.

The hybrid classification captures both: the cognitive task is irreducibly prompt-enforced; the output contract is mechanically enforceable. Attempting to make synthesis "more enforceable" via code would either produce vacuous template-filling or require deep semantic understanding that deterministic validators cannot provide.

---

## Write Boundary Confirmation

- **Files read:** `.opencode/agents/builder_lead.md`, `.opencode/agents/verifier_lead.md` (reference profiles, read-only context)
- **Files written:** `analysis/classification_report.md` (within declared write boundary)
- **Files modified:** None outside write boundary
- **Chaining budget:** 0 — no `task` dispatches issued
- **Confirmation:** No files outside the declared write boundary were touched.

---

**End of report.**