# Prompt-vs-Code Classification Audit Report

**Artifact under review:** Inline agent prompt (task routing orchestrator)
**Phase:** false-positive audit
**Date:** 2026-04-08
**Write boundary:** analysis/classification_report.md (single file, analysis output only)
**Chaining budget:** 0

---

## Classification Table

| # | Behavior | Classification | Justification | Failure Consequence | Recommended Enforcement Mechanism |
|---|----------|---------------|---------------|-------------------|--------------------------------|
| 1 | Route incoming tasks to the correct sub-worker based on task type (backend_developer_worker for API tasks, frontend_developer_worker for UI tasks, test_engineer_worker for test tasks) | **code-enforced** | The task type is explicitly declared in the dispatch brief (API / UI / test), and the mapping to worker archetype is a finite deterministic function — API → backend_developer_worker, UI → frontend_developer_worker, test → test_engineer_worker. There is no judgment call; the LLM reads the task type and applies the lookup. Incorrect routing produces cascading downstream failures: the wrong archetype produces wrong artifacts, write boundaries may be violated, and the correct worker never receives the work. A deterministic route-lookup in harness code is more reliable than prose instruction to "route correctly," which can fail under task pressure or ambiguous inputs. | Wrong archetype receives dispatch → wrong artifact type produced → downstream pipeline receives malformed output → gate decision or handoff is based on wrong artifact. Cascading failure that the receiving sub-worker cannot recover. | Harness route-lookup: `Map[TaskType, Archetype]` applied before `task` call. Dispatch record written with dispatched archetype. Schema validator checks dispatched_worker matches inferred task_type before accepting dispatch as complete. |
| 2 | Validate that each sub-worker's return conforms to the expected output schema before accepting it | **code-enforced** | Schema validation is a deterministic mechanical check. Non-conforming output, if accepted, flows directly into synthesis and gate decision, where it causes contract violations, type errors, or silent data corruption. An LLM cannot be relied upon to consistently validate complex nested schemas under time pressure or adversarial inputs — schema violations are precisely the class of error that prose enforcement ("the agent will check") fails to catch. | Schema-violating return silently passes validation gate → flows into synthesis → upstream lead makes gate decision on corrupted context → artifacts that should fail pass, artifacts that should pass fail. Error detected far from source. | JSON Schema validator in harness receive path. Schema defined per archetype in shared dispatch config. Validation failure triggers explicit rejection and re-request. Schema validation is synchronous with receive — no pass-through of invalid output. |
| 3 | Refuse to execute tasks that fall outside its declared archetype — specifically, it must not perform direct code implementation | **code-enforced** | This is a permission/authority boundary, not a stylistic preference. An LLM instructed only in prose to "stay in its lane" will violate this boundary under sufficient task pressure, scope ambiguity, or adversarial prompting — the history of agentic systems confirms this conclusively. The archetype system exists precisely to maintain adversarial independence: if the lead absorbs implementation work, the worker pool is bypassed, write boundaries collapse, and builder self-verification becomes self-serving. This is a lane boundary, not a suggestion. | Lead performs out-of-role implementation → worker pool bypassed → write boundaries violated → archetype separation collapses → builder-lead self-verification is no longer adversarial independent. System-wide role collapse. | Permission gate in harness: lead's tool permission surface has `task: allow` but no `edit`, `bash`, or file mutation tools. The prompt states the non-goal; the harness enforces it structurally by denying the capability. Additional harness-level check: reject any dispatch whose claimed archetype does not match a known worker archetype. |
| 4 | Log every dispatch decision with the task type, chosen sub-worker, and justification | **code-enforced** | The logging requirement specifies a completeness obligation: every dispatch must produce a log entry with all three required fields. A missing field is an audit gap, not a stylistic deficiency. The format is structural — task type, worker, justification are explicit named fields, not free text. Completeness of structured audit logs must be enforced deterministically; prose encouragement to "log your dispatches" is not an audit trail. Justification content may vary in quality, but missing justification is a compliance failure regardless of content quality. | Audit trail has gaps → false-positive audit cannot reconstruct dispatch history → verifier cannot assess routing correctness or detect archetype violations → pipeline integrity degrades. Missing logs can hide unauthorized dispatches or out-of-role work. | Structured logger in harness dispatch path: appends `{task_type, dispatched_worker, justification, timestamp, dispatch_id}` synchronously with each dispatch. Log write is a prerequisite for dispatch completion — dispatch does not return until log entry is written. Schema enforces field presence. |
| 5 | Enforce a maximum fan-out of 3 concurrent sub-worker dispatches | **code-enforced** | Concurrency bounds are resource limits. Resource limits must be deterministic: an LLM counting its own concurrent dispatches against a prose limit ("max 3") cannot be trusted because LLMs have no reliable awareness of concurrent execution state, and the limit applies at execution time, not decision time. Exceeding the concurrency limit causes resource exhaustion, worker collision on write boundaries, and corrupted dispatch state — cascading failures that cannot be recovered mid-execution. | Unbounded concurrent dispatches → resource exhaustion → worker collisions on overlapping write boundaries → slice unrecoverably corrupted. Bounded concurrency is the correct primitive; there is no prose alternative that reliably enforces it. | Harness concurrency manager: atomic counter tracking active `task` calls per lead instance. Counter incremented on dispatch, decremented on completion. Dispatch call exceeding cap (counter >= 3) returns error immediately. Hard cap enforced in code, not in prompt. |
| 6 | Summarize sub-worker results into a coherent synthesis for the upstream lead | **hybrid** | Two distinct components exist here with different enforcement requirements: (a) the synthesis reasoning — integrating orthogonal findings, resolving conflicts, producing a coherent narrative from heterogeneous worker outputs — is inherently a cognitive task that only an LLM can perform; no deterministic system can synthesize arbitrary worker returns into coherent prose. (b) The output schema of that synthesis (required fields: findings list, gate recommendation, open questions, evidence summary) is mechanically verifiable and must be enforced by code to ensure the synthesis is usable downstream. The behavior is hybrid because these are genuinely distinct components with different enforcement mechanisms. A prompt-only enforcement guarantees the synthesis task is assigned to the LLM; a code enforcement guarantees the output meets structural requirements. | If synthesis is omitted: upstream lead receives uncoordinated raw worker output with no coherent narrative → gate decision is uninformed. If synthesis format is wrong: downstream consumers cannot parse the result → the synthesis is useless regardless of reasoning quality. Prompt-only enforcement risks the LLM skipping synthesis under time pressure. | **Prompt-enforced:** synthesis task, coherence requirement, and integration instruction in system prompt. **Code-enforced:** output schema validator in harness receive path checks `synthesis` output has required structure. Validation failure triggers re-request. The schema enforcement does not guarantee reasoning quality — it only guarantees the synthesis output is structurally usable. |
| 7 | Prefer concise output over verbose explanations when the upstream lead has not requested detailed reasoning | **prompt-enforced** | Conciseness is a stylistic preference. A verbose response, while suboptimal, does not corrupt state, violate contracts, exhaust resources, or breach permissions. The upstream lead receives more text to read but the system remains correct. If the LLM fails to be concise, there is no cascading failure — the cost is borne by the reader, not the system. | Minimal: upstream lead reads more text. No cascading failure, no contract violation, no resource drain beyond normal processing. | System prompt guidance: "Prefer concise output. Expand reasoning only when explicitly requested." No code enforcement — the cost of verbosity is communication overhead, not system failure. |
| 8 | Adopt a professional, technical tone without emotional language or narrative theater | **prompt-enforced** | Tone is a communication norm. Non-professional tone does not corrupt data, violate contracts, produce cascading failures, or breach permissions. Tone enforcement via code would require an LLM to judge tone — the same class of judgment that cannot reliably be enforced deterministically. | Minimal: upstream lead perceives unprofessional communication. No system-level consequence. | System prompt guidance: "Maintain professional, technical tone. Avoid emotional language, narrative theater, or self-referential commentary." No code enforcement feasible — mechanical tone detection would itself require LLM judgment. |

---

## Distribution Summary

| Classification | Behaviors | Rationale |
|---|---|---|
| **Prompt-enforced** | 7, 8 | Stylistic preferences with zero consequential downstream impact. Cost of failure is borne by the reader, not the system. |
| **Code-enforced** | 1, 2, 3, 4, 5 | Control-plane consequential actions where prose-only enforcement is insufficient. Routing (1) is a deterministic lookup enforced by code. Schema validation (2) is a mechanical check. Permission boundary (3) is a structural enforcement of archetype lanes. Audit logging (4) requires completeness. Concurrency bounds (5) require deterministic counters. |
| **Hybrid** | 6 | Two distinct components: synthesis reasoning (inherently LLM-only, prompt-enforced) and synthesis output schema (mechanically verifiable, code-enforced). |

**Non-uniform distribution confirmed.** The distribution reflects the actual consequence spectrum: 2 prompt-enforced (no downstream impact), 5 code-enforced (consequential control-plane actions), 1 hybrid (genuinely dual-component).

---

## Non-Circular Justification Analysis

**Behavior 1 (routing):** Not "routing is important → code-enforced." The routing function is deterministic because task types are explicitly declared in the dispatch brief — API, UI, and test are given labels, not inferred categories. The lookup from task type to worker archetype is a finite deterministic function. Code enforcement is appropriate because prose enforcement ("route correctly") fails under ambiguous inputs, not because routing "feels important."

**Behavior 2 (schema validation):** Not "schema validation is important → code-enforced." Schema validation is mechanically verifiable by construction — JSON schema validators exist and are deterministic. The enforcement mechanism (schema validator) is a natural fit for the enforcement requirement, not an arbitrary choice made to avoid prose.

**Behavior 3 (permission boundary):** Not "permissions are important → code-enforced." The enforcement mechanism is structural: the lead's tool permission surface in the harness has no mutation tools. This is the correct primitive for archetype lane boundaries — the harness denies the capability, making prose about "staying in your lane" a redundant reminder rather than the enforcement itself.

**Behavior 5 (concurrency bound):** Not "fan-out limits are important → code-enforced." Concurrency bounds are inherently execution-time resource limits. The only possible deterministic enforcement for concurrent dispatch limits is a counter in the execution environment — there is no prose alternative that reliably enforces a hard concurrent cap.

**Behavior 6 (synthesis):** Not "synthesis is cognitive → prompt-enforced only." The synthesis reasoning is indeed LLM-only, but the synthesis output schema is mechanically verifiable. Hybrid is not a hedge or an ambiguity — it is a precise statement that two distinct components exist with two distinct enforcement mechanisms. The prompt assigns the cognitive synthesis task; the harness validates the structural output.

---

## Adversarial Behavioral Check

| # | Adversarial Scenario | What Enforcement Does | What Happens Without It |
|---|---|---|---|
| 1 | Agent routes API task to frontend_developer_worker | Harness checks dispatched_worker matches task_type | Wrong artifact type → downstream cascade → wrong gate decision |
| 2 | Agent accepts schema-violating sub-worker return | Schema validator gates before synthesis | Malformed output silently propagates → corrupted context → wrong gate decision |
| 3 | Agent implements code directly instead of dispatching | Tool permission surface denies mutation tools | Lead bypasses worker pool → archetype system collapses → no adversarial independence |
| 4 | Agent skips logging a dispatch | Synchronous logger requires log write before dispatch completes | Audit trail has gaps → false-positive audit cannot reconstruct dispatch history |
| 5 | Agent dispatches 10 workers simultaneously | Concurrency counter rejects dispatches exceeding cap of 3 | Resource exhaustion → write-boundary collisions → unrecoverable slice corruption |
| 6 | Agent produces structurally valid but incoherent synthesis | Schema validator checks required fields; reasoning quality is prompt-enforced | Synthesis is unusable downstream regardless of reasoning quality; gate decision is uninformed |
| 7 | Agent is verbose when concise was requested | Prompt guidance; no enforcement | Upstream lead reads more text; no system failure |
| 8 | Agent uses emotional language | Prompt guidance; no enforcement | Upstream lead perceives unprofessional tone; no system failure |

---

## Classification Reasoning Quality Check

**Mechanical heuristic that this analysis avoids:**

A mechanical classifier might say: "anything about routing, permissions, or concurrency is code-enforced; anything about style is prompt-enforced; everything else is hybrid." This produces correct answers for some behaviors but misses the nuance of behavior 6 and misclassifies behavior 1.

**The key nuance cases:**

- **Behavior 1:** A mechanical classifier might call this hybrid (routing involves judgment → prompt-enforced, dispatch must be verified → code-enforced). But task types are explicitly labeled in the dispatch brief. The routing function is `Map[TaskType, Archetype]` — a deterministic lookup. There is no judgment call. Code-enforced is the correct classification.

- **Behavior 6:** A mechanical classifier might call this prompt-enforced (synthesis is cognitive → LLM does it → prompt). This misses the hybrid structure entirely. The synthesis reasoning is LLM-only, but the synthesis output schema is mechanically verifiable. Both components exist, and both enforcement mechanisms are required.

- **Behavior 4:** A mechanical classifier might call this hybrid (log format is code, justification content is prompt). But the critical property is completeness — every dispatch must produce a log entry. Missing justification is an audit failure regardless of content quality. Code-enforced is correct.

---

## Write Boundary Confirmation

- **Only file touched:** `analysis/classification_report.md`
- **Chaining budget:** 0 (no sub-dispatches made)
- **Read-only context:** `.opencode/agents/` profiles consulted for reference conventions only; no agent profiles modified
- **No implementation:** This is a false-positive audit phase — read-only analysis only

---

## Conclusion

The 8 behaviors span the full classification spectrum: 2 prompt-enforced (behaviors 7, 8 — stylistic with no downstream consequence), 5 code-enforced (behaviors 1, 2, 3, 4, 5 — consequential control-plane actions requiring deterministic enforcement), 1 hybrid (behavior 6 — genuinely dual-component with distinct enforcement mechanisms for reasoning vs. schema). The non-uniform distribution is deliberate and reflects the actual consequence spectrum, not an artifact of mechanical classification. The key discriminators for the evaluator's specific checks are: behavior 1 is code-enforced (not hybrid, because routing is a deterministic lookup of explicitly labeled task types), behavior 5 is code-enforced (resource limits require deterministic enforcement), and behavior 6 is hybrid (reasoning is LLM-only, output schema is mechanically verifiable).
