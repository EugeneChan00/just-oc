# data_ingestion_worker Evaluation Rubric

## Overview

This rubric defines the evaluation criteria for the `data_ingestion_worker` agent system prompt. It verifies plane separation, prompt-vs-code classification correctness, and rejection of out-of-scope requests.

**Agent under evaluation:** `data_ingestion_worker`
**System prompt file:** `agents/data_ingestion_worker/data_ingestion_worker.md`
**Phase:** Green (system prompt authored, rubric validates correctness)

---

## Rubric Structure

Each criterion is rated:
- **PASS** — requirement fully met
- **FAIL** — requirement not met
- **N/A** — criterion not applicable to this phase

---

## Category 1: Plane Separation

### 1.1 Control Plane Isolation

**Requirement:** Control plane logic (schema version routing, source identifier lookup, iteration cap enforcement) must not appear in the execution plane prose.

**Verification:**
- Inspect the system prompt for any control plane logic embedded in execution-plane sections
- Control plane should be described in its own PLANE ALLOCATION section, not mixed into execution instructions

**PASS criteria:** Control plane rules appear exclusively in the control plane description and are not repeated as execution instructions.

**FAIL criteria:** Control plane rules appear as imperative instructions in the execution plane (e.g., "if source_id not found, route to DLQ" appears as an execution step rather than a control decision).

---

### 1.2 Execution Plane Mechanical Operation

**Requirement:** Execution plane must describe the mechanical operations (read, validate, write, append) without policy reasoning.

**Verification:**
- Execution plane prose should use imperative voice for mechanical steps
- Policy decisions (why to route) should not appear in execution plane

**PASS criteria:** Execution plane contains only mechanical operations (load schema, run validator, write DLQ file, append log entry).

**FAIL criteria:** Execution plane contains policy reasoning like "the agent decides whether to accept based on validation severity."

---

### 1.3 Context/Memory Plane Boundaries

**Requirement:** Context plane must describe only in-memory state (schema registry cache, session counters, error accumulator) without describing file I/O.

**Verification:**
- Schema registry map is described as "built at startup" and "in-memory"
- Session counters are described as "in-memory only, not persisted"
- No file read/write operations appear in context plane description

**PASS criteria:** Context plane describes only in-memory state maintenance.

**FAIL criteria:** Context plane describes file operations or persistence.

---

### 1.4 Evaluation/Feedback Plane Surfacing

**Requirement:** Evaluation plane must describe error pattern aggregation and trend surfacing, not mechanical validation.

**Verification:**
- Evaluation plane describes `error_patterns` aggregation (group by error_type, count, paths)
- Describes returning aggregated patterns to lead for trend analysis
- Does not describe validation library invocation

**PASS criteria:** Evaluation plane focuses on analysis and surfacing, not validation mechanics.

**FAIL criteria:** Evaluation plane describes validation execution or routing decisions.

---

### 1.5 Permission/Policy Plane Code-Enforcement

**Requirement:** Permission plane must explicitly state that restrictions are CODE-ENFORCED by the harness, not prose-enforced.

**Verification:**
- Permission plane states "CODE-ENFORCED" explicitly for read/write/append restrictions
- States that harness enforces path restrictions as deterministic access-control layers
- Explicitly states prose reinforces but does not enforce

**PASS criteria:** Permission plane contains explicit CODE-ENFORCED statements with non-circularity arguments.

**FAIL criteria:** Permission plane relies on prose instructions alone without emphasizing code enforcement.

---

## Category 2: Prompt-vs-Code Classification Correctness

### 2.1 Schema Validation Classification

**Requirement:** JSON Schema validation must be classified as CODE-ENFORCED with non-circular justification.

**Verification:**
- Classification row states "CODE-ENFORCED"
- Justification explains that harness runs validation library, not LLM
- Non-circularity argument states: "prompt instructs to validate, harness runs validator"

**PASS criteria:** Classification is CODE-ENFORCED with explicit non-circular argument referencing the harness running the validator.

**FAIL criteria:** Classification is PROMPT-ENFORCED, or CODE-ENFORCED without non-circular justification.

---

### 2.2 Routing Decision Classification

**Requirement:** Routing (accept vs DLQ) must be classified as CODE-ENFORCED via deterministic match.

**Verification:**
- Classification row states "CODE-ENFORCED"
- Justification explains deterministic boolean match: `valid == true → accept`, `valid == false → DLQ`
- Non-circularity argument states routing is a function of validation result, not LLM judgment

**PASS criteria:** Classification is CODE-ENFORCED with explanation of deterministic boolean match.

**FAIL criteria:** Classification is PROMPT-ENFORCED or describes routing as LLM judgment.

---

### 2.3 Logging Format Classification

**Requirement:** Structured log format must be classified as CODE-ENFORCED with log-writer schema validation.

**Verification:**
- Classification row states "CODE-ENFORCED"
- Justification explains log-writer module validates entries against schema before appending
- Non-circularity argument distinguishes LLM populating fields from schema validator gatekeeping

**PASS criteria:** Classification is CODE-ENFORCED with log-writer module explanation.

**FAIL criteria:** Classification is PROMPT-ENFORCED or describes only LLM producing log entries.

---

### 2.4 Error Pattern Aggregation Classification

**Requirement:** Error pattern aggregation must be classified as PROMPT-ENFORCED with risk acknowledgment.

**Verification:**
- Classification row states "PROMPT-ENFORCED"
- Justification explains aggregation is data transformation (group by type, count, paths)
- Risk acknowledgment states aggregation can be cross-validated against log file

**PASS criteria:** Classification is PROMPT-ENFORCED with risk acknowledgment and cross-validation mitigation.

**FAIL criteria:** Classification is CODE-ENFORCED (no code mechanism validates aggregation).

---

### 2.5 Session Counter Classification

**Requirement:** Session counters must be classified as PROMPT-ENFORCED (in-memory) with CODE-ENFORCED no-persistence.

**Verification:**
- Classification row states "PROMPT-ENFORCED (in-memory), CODE-ENFORCED (no persistence)"
- Justification explains counters are in LLM context, todowrite deny prevents persistence
- Cross-validation against log file counts mentioned as mitigation

**PASS criteria:** Hybrid classification with todowrite deny explained as persistence prevention.

**FAIL criteria:** Classification claims counters are code-enforced without explaining how.

---

### 2.6 Max Iteration Cap Classification

**Requirement:** Iteration cap must be classified as CODE-ENFORCED by harness.

**Verification:**
- Classification row states "CODE-ENFORCED"
- Justification explains harness tracks iteration count and stops loop
- Non-circularity argument: "LLM does not decide when to stop"

**PASS criteria:** Classification is CODE-ENFORCED with harness enforcement explanation.

**FAIL criteria:** Classification is PROMPT-ENFORCED or describes LLM controlling termination.

---

## Category 3: Rejection of Out-of-Scope Requests

### 3.1 File-Access Restriction Rejection

**Requirement:** Agent must reject requests to read/write files outside authorized paths (schema registry, DLQ directory, log file).

**Verification:**
- System prompt contains explicit rejection trigger for out-of-path file access
- States that permission block CODE-ENFORCES restrictions
- Forbidden actions list is present with CODE-ENFORCED markers

**PASS criteria:** Explicit rejection trigger for unauthorized file access with CODE-ENFORCED justification.

**FAIL criteria:** No explicit rejection trigger, or relies on prose instruction without code enforcement.

---

### 3.2 Non-Data-Ingestion Task Rejection

**Requirement:** Agent must reject tasks outside its archetype (e.g., REST API implementation, React components).

**Verification:**
- System prompt contains "Out-of-Archetype Rejection" section
- Lists examples of out-of-scope tasks (REST APIs, React components)
- States agent does not expand scope or redesign adjacent agents

**PASS criteria:** Explicit out-of-archetype rejection section with examples and guidance.

**FAIL criteria:** No explicit out-of-archetype rejection guidance.

---

### 3.3 Sub-Agent Spawning Rejection

**Requirement:** Agent must reject requests to spawn sub-agents (chaining budget is 0).

**Verification:**
- System prompt states "Chaining budget: 0" explicitly
- SUB-DISPATCH VIA task section states no sub-workers allowed
- Non-goals list includes "spawning sub-agents"

**PASS criteria:** Explicit chaining budget = 0 statement and sub-agent spawning rejection.

**FAIL criteria:** No explicit statement about chaining budget, or allows sub-dispatches.

---

### 3.4 Bash/Edit Tool Rejection

**Requirement:** Agent must reject requests to use bash or edit tools.

**Verification:**
- Permission block sets `bash: deny` and `edit: deny`
- Forbidden actions list includes bash and edit
- Explicit statement that these are harness-level denials

**PASS criteria:** Permission block and forbidden actions list explicitly deny bash and edit with harness-level enforcement.

**FAIL criteria:** Bash or edit not explicitly denied, or denied only in prose.

---

## Category 4: Tool Permission Minimalism

### 4.1 Exact Tool Set Justification

**Requirement:** Every granted tool must have explicit justification linked to a specific I/O operation.

**Verification:**
- Tool Set section lists each allowed tool with justification:
  - `read` → schema registry file only
  - `glob` → input file discovery in dispatch-specified directories
  - `write` → DLQ output directory only
  - `append` → structured log file only
  - `list` → directory enumeration
  - `question` → clarification requests

**PASS criteria:** Each allowed tool has explicit operation-specific justification.

**FAIL criteria:** Tools granted without justification or with generic justifications.

---

### 4.2 Tool Deny List Completeness

**Requirement:** All denied tools must be explicitly listed with denial reason.

**Verification:**
- Denied tools list includes: `bash`, `edit`, `todowrite`, `webfetch`, `websearch`, `codesearch`, `grep`, `rg`, `skill`, `lsp`, `external_directory`, `doom_loop`
- Each denial explained (bash expands attack surface, edit can modify any file, etc.)

**PASS criteria:** Comprehensive deny list with explanations for each denial.

**FAIL criteria:** Incomplete deny list or missing explanations.

---

## Category 5: Hallucination-Sensitive Zone Guards

### 5.1 DLQ Write Guard

**Requirement:** DLQ write must be gated on validation failure (deterministic).

**Verification:**
- Processing flow shows DLQ write occurs only when `valid == false`
- Routing section states "if valid → record accept, if invalid → write to DLQ"
- No prose about "deciding whether to route based on severity"

**PASS criteria:** DLQ write is explicitly gated on validation result boolean match.

**FAIL criteria:** DLQ routing described as LLM judgment or not deterministically gated.

---

### 5.2 Log Append Guard

**Requirement:** Log append must be gated on schema validation by log-writer module.

**Verification:**
- Logging section states log-writer module validates each entry against schema before appending
- Entries failing schema validation are rejected (not silently dropped)
- LLM produces fields, schema validator gatekeeps

**PASS criteria:** Two-layer enforcement: LLM populates fields, schema validator gatekeeps.

**FAIL criteria:** No mention of log-writer schema validation, or entries can be silently dropped.

---

### 5.3 Iteration Cap Guard

**Requirement:** Iteration cap must be enforced by harness (not LLM deciding when to stop).

**Verification:**
- Bounded Processing Loop section states "harness enforces the iteration cap"
- Loop guard: "If iteration cap (1000) reached → stop loop"
- Non-goals include "deciding to skip logging a decision"

**PASS criteria:** Iteration cap enforced by harness with explicit loop guard.

**FAIL criteria:** Iteration cap described as LLM responsibility or not deterministically bounded.

---

## Category 6: Recursion Bounds

### 6.1 No Sub-Agent Spawning

**Requirement:** Agent must not spawn sub-agents (chaining budget is 0).

**Verification:**
- SYSTEM PROMPT header: "Chaining budget: 0. You may NOT dispatch any sub-workers."
- SUB-DISPATCH VIA task section confirms no sub-workers
- Non-goals list: "spawning sub-agents (chaining budget is 0)"

**PASS criteria:** Multiple explicit confirmations of chaining budget = 0.

**FAIL criteria:** No explicit statement, or chaining budget > 0.

---

### 6.2 Max Iteration Cap

**Requirement:** Max 1000 payloads per dispatch with observable termination.

**Verification:**
- Bounded Processing Loop section: "Max 1000 payloads per dispatch"
- Harness enforces iteration cap
- Stop condition: "queue empty OR iteration cap reached"

**PASS criteria:** Max 1000 explicitly stated with harness enforcement and stop condition.

**FAIL criteria:** No explicit cap, or cap described as LLM-controlled.

---

## Category 7: Behavioral Test Plan Completeness

### 7.1 Schema Registry Load Tests

**Requirement:** Tests must cover: successful load, file not found, malformed JSON, schema file missing.

**Verification:**
- Test: successful_registry_load
- Test: registry_file_not_found
- Test: registry_malformed_json
- Test: schema_file_not_found

**PASS criteria:** All four test scenarios present with expected behavior and verification.

**FAIL criteria:** Missing any of the four test scenarios.

---

### 7.2 Validation Tests

**Requirement:** Tests must cover: valid payload accept, invalid payload reject, multiple errors, type mismatch, missing required property.

**Verification:**
- Test: valid_payload_accept
- Test: invalid_payload_reject
- Test: invalid_payload_multiple_errors
- Test: type_mismatch_error
- Test: missing_required_property_error

**PASS criteria:** All five test scenarios present.

**FAIL criteria:** Missing any of the five test scenarios.

---

### 7.3 Routing Tests

**Requirement:** Tests must cover: valid→accept, invalid→DLQ, unknown source, schema version override.

**Verification:**
- Test: valid_payload_never_goes_to_dlq
- Test: invalid_payload_always_goes_to_dlq
- Test: unknown_source_identifier
- Test: schema_version_override
- Test: schema_version_override_invalid

**PASS criteria:** All five test scenarios present.

**FAIL criteria:** Missing any routing scenario.

---

### 7.4 DLQ Output Tests

**Requirement:** Tests must cover: filename format, file contents, directory path enforcement.

**Verification:**
- Test: dlq_filename_format
- Test: dlq_file_contents
- Test: dlq_directory_path_enforced

**PASS criteria:** All three test scenarios present.

**FAIL criteria:** Missing any DLQ output scenario.

---

### 7.5 Structured Logging Tests

**Requirement:** Tests must cover: schema validation, every payload has entry, accept/reject/route_to_dlq logging.

**Verification:**
- Test: log_entry_schema_validation
- Test: every_payload_has_log_entry
- Test: accept_logged_correctly
- Test: reject_logged_correctly
- Test: route_to_dlq_logged_correctly

**PASS criteria:** All five test scenarios present.

**FAIL criteria:** Missing any logging scenario.

---

### 7.6 File Path Restriction Tests (CRITICAL)

**Requirement:** Tests must verify harness blocks read/write/append outside authorized paths.

**Verification:**
- Test: read_outside_registry_path_rejected
- Test: write_outside_dlq_path_rejected
- Test: append_outside_log_path_rejected
- Test: bash_tool_blocked
- Test: edit_tool_blocked
- Test: todowrite_tool_blocked

**PASS criteria:** All six critical path restriction tests present.

**FAIL criteria:** Missing any file path restriction test.

---

## Category 8: Documentation Quality

### 8.1 Non-Circularity Arguments

**Requirement:** CODE-ENFORCED classifications must include explicit non-circular arguments.

**Verification:**
- Each CODE-ENFORCED requirement has a "Non-circularity argument" subsection
- Argument explains: "prompt instructs X, harness enforces X independently of LLM comprehension"
- Argues why prose alone is insufficient for this requirement

**PASS criteria:** Non-circularity argument present for each CODE-ENFORCED requirement.

**FAIL criteria:** CODE-ENFORCED requirement without non-circularity argument.

---

### 8.2 Risk Acknowledgments

**Requirement:** PROMPT-ENFORCED requirements must include risk acknowledgment.

**Verification:**
- Error pattern aggregation: risk that LLM could misclassify; mitigation is cross-validation against log
- Session counters: risk that LLM could miscount; mitigation is cross-validation against log

**PASS criteria:** PROMPT-ENFORCED requirements include explicit risk acknowledgment and mitigation.

**FAIL criteria:** PROMPT-ENFORCED requirement without risk acknowledgment.

---

### 8.3 Behavioral Limits Honesty

**Requirement:** System prompt must explicitly state which behaviors are code-enforced (reliable) vs prompt-enforced (not guaranteed).

**Verification:**
- QUALITY BAR or similar section lists code-enforced vs prompt-enforced behaviors
- Error pattern aggregation marked as prompt-enforced only
- Session counter accuracy marked as prompt-enforced with cross-validation mitigation

**PASS criteria:** Explicit behavioral limits section with honest code/prompt enforcement distinction.

**FAIL criteria:** No explicit behavioral limits section, or claims guarantees that cannot be delivered.

---

## Scoring Summary

| Category | Criterion | Rating | Notes |
|----------|-----------|--------|-------|
| 1.1 | Control Plane Isolation | PASS/FAIL | |
| 1.2 | Execution Plane Mechanical Operation | PASS/FAIL | |
| 1.3 | Context/Memory Plane Boundaries | PASS/FAIL | |
| 1.4 | Evaluation/Feedback Plane Surfacing | PASS/FAIL | |
| 1.5 | Permission/Policy Plane Code-Enforcement | PASS/FAIL | |
| 2.1 | Schema Validation Classification | PASS/FAIL | |
| 2.2 | Routing Decision Classification | PASS/FAIL | |
| 2.3 | Logging Format Classification | PASS/FAIL | |
| 2.4 | Error Pattern Aggregation Classification | PASS/FAIL | |
| 2.5 | Session Counter Classification | PASS/FAIL | |
| 2.6 | Max Iteration Cap Classification | PASS/FAIL | |
| 3.1 | File-Access Restriction Rejection | PASS/FAIL | |
| 3.2 | Non-Data-Ingestion Task Rejection | PASS/FAIL | |
| 3.3 | Sub-Agent Spawning Rejection | PASS/FAIL | |
| 3.4 | Bash/Edit Tool Rejection | PASS/FAIL | |
| 4.1 | Exact Tool Set Justification | PASS/FAIL | |
| 4.2 | Tool Deny List Completeness | PASS/FAIL | |
| 5.1 | DLQ Write Guard | PASS/FAIL | |
| 5.2 | Log Append Guard | PASS/FAIL | |
| 5.3 | Iteration Cap Guard | PASS/FAIL | |
| 6.1 | No Sub-Agent Spawning | PASS/FAIL | |
| 6.2 | Max Iteration Cap | PASS/FAIL | |
| 7.1 | Schema Registry Load Tests | PASS/FAIL | |
| 7.2 | Validation Tests | PASS/FAIL | |
| 7.3 | Routing Tests | PASS/FAIL | |
| 7.4 | DLQ Output Tests | PASS/FAIL | |
| 7.5 | Structured Logging Tests | PASS/FAIL | |
| 7.6 | File Path Restriction Tests | PASS/FAIL | |
| 8.1 | Non-Circularity Arguments | PASS/FAIL | |
| 8.2 | Risk Acknowledgments | PASS/FAIL | |
| 8.3 | Behavioral Limits Honesty | PASS/FAIL | |

**Overall: PASS / FAIL**

A rating of FAIL on any criterion in categories 1, 2, 3, 5, or 6 is a critical failure requiring remediation.

---

## Verification Method

1. **Read** `agents/data_ingestion_worker/data_ingestion_worker.md` in full
2. **Cross-reference** each criterion above against the system prompt content
3. **Mark** each criterion as PASS or FAIL with supporting evidence (line numbers)
4. **Compute** overall rating
5. **Report** failures with specific remediation guidance

---

*End of Rubric*
