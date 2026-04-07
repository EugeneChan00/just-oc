---
allowed-tools: Read, Write, Edit, Glob, Bash, Grep, Task, AskUserQuestion
description: Create structured prompts with XYZ execution semantics and interview-driven tier classification
argument-hint: <prompt_request>
model: opus
doc-class: threads-framework-commands
---

# Meta-Prompt v2 — Execution-Semantic Command Generator

**Core Principle:** A Prompt is the atomic primitive of agent execution.
Agent Execution = Interaction Model + Reflexion Model + Context.

This meta-prompt generates slash commands with explicit execution semantics,
using the XYZ execution model for structured reasoning and verification.

---

## Input/Output Contract

### Input

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| USER_PROMPT | Yes | $1 | The prompt description to generate |
| ABSTRACTION_LAYER | Yes | Interview | concept / tech_stack / implementation |
| INTENT_SCOPE | Yes | Interview | atomic / composed / nested |
| DEPENDENCIES | Yes | Interview | List of declared dependencies |
| RISK_LEVEL | Yes | Interview | low / medium / high |
| CONTEXT_DEPTH | Yes | Interview | single_file / cross_file / cross_project |
| CONDITIONAL_EXECUTION | No | Interview | {condition, action} pairs |
| DELEGATION_POLICY | Yes | Interview | none / selective / aggressive |
| GATE_VERIFICATION_CONFIG | Yes | Interview | {gate, subagents[]} mapping |
| CHEATING_GUIDANCE | No | Interview | User-provided cheating behavior hints |

### Output

| Artifact | Location | Description |
|----------|----------|-------------|
| Command File | `.claude/commands/[name].md` (project) or `~/.claude/commands/[name].md` (home) | Generated slash command |
| XYZ Manifest | Embedded in command | Coordinates and verification config |

**Output Path Detection:**
```bash
if git rev-parse --git-dir > /dev/null 2>&1; then
    OUTPUT_DIR=".claude/commands"
else
    OUTPUT_DIR="$HOME/.claude/commands"
fi
mkdir -p "$OUTPUT_DIR"
```

---

## Variables

### Static Variables (Framework Constants)

```yaml
PIEV_QUADRANTS: [P, I, E, V]  # Plan, Implement, Execute, Verify
GATE_CHECKPOINTS:
  P4: plan_gate        # PASS before entering Implement
  I4: node_gate        # PASS before entering Execute
  E4: integration_gate # PASS before entering Verify
  V4: closeout_gate    # PASS before closure
Z_SUBAGENTS:
  context_delegate: "Summarize constraints, unknowns, risk blind spots"
  verifier_structural: "Check required artifacts/sections exist and are complete"
  verifier_semantic: "Reject contradictions and non-testable acceptance claims"
  verifier_functional: "Run commands/tests and validate executable evidence"
MAX_DEPTH: 3  # Default recursion limit
```

### Dynamic Variables (Interview-Derived)

Collected during PIEV-P (Interview phase). Agent MUST ask user to refine proposals.

| Variable | Domain | Interview Question |
|----------|--------|-------------------|
| ABSTRACTION_LAYER | concept, tech_stack, implementation | "What abstraction level should this operate at?" |
| INTENT_SCOPE | atomic, composed, nested | "Is this single-step, multi-step with branches, or requires delegation?" |
| DEPENDENCIES | string[] | "What external dependencies does this have? I'll propose some, you refine." |
| RISK_LEVEL | low, medium, high | "What breaks if this goes wrong? Is it reversible?" |
| CONTEXT_DEPTH | single_file, cross_file, cross_project | "How much context is needed?" |
| DELEGATION_POLICY | none, selective, aggressive | "When should subagents be spawned?" |
| GATE_VERIFICATION_CONFIG | {gate: subagents[]} | "Which verification subagents at each gate?" |

---

## Invariants

These MUST ALWAYS hold true, regardless of prompt type or tier.

### Structural Invariants

1. **I/O Contract Defined** — Input/output declared before any execution
2. **Reflexion Present** — Every generated command includes verification metrics
3. **Measurable Metrics** — All validation criteria are testable, not subjective

### Semantic Invariants

1. **Single Responsibility** — One clear purpose per command
2. **No Mixed Abstraction** — All steps operate at same abstraction level
3. **Bounded Scope** — Explicit declaration of what is in/out of scope

### Execution Invariants

1. **No Gate Skip** — No PIEV quadrant transition without gate PASS
2. **Depth Bounded** — No hidden recursion beyond MAX_DEPTH
3. **Evidence Required** — No closure without functional evidence at V4

### Dependency Invariants

1. **Explicit Declaration** — All dependencies listed upfront
2. **Proposal + Refine** — Agent proposes dependencies, user confirms/adjusts

---

## Conditionals

### Abstraction Layer Conditionals

```
IF ABSTRACTION_LAYER == concept:
  - Model: opus
  - Workflow: Declarative, reasoning-heavy
  - Tools: Read, Grep, Glob (analysis focus)

IF ABSTRACTION_LAYER == tech_stack:
  - Model: sonnet
  - Workflow: Tool-specific instructions
  - Tools: Bash, Edit, Write (implementation focus)

IF ABSTRACTION_LAYER == implementation:
  - Model: haiku or sonnet
  - Workflow: Concrete step-by-step
  - Tools: All available (execution focus)
```

### Scope Conditionals

```
IF INTENT_SCOPE == atomic:
  - Single-file target
  - Linear workflow (no loops, no delegation)
  - Y-depth: 0 (root only)

IF INTENT_SCOPE == composed:
  - Multi-file target
  - Control-flow with <loop> blocks
  - Y-depth: 0-1 (root + optional single delegation)

IF INTENT_SCOPE == nested:
  - Cross-project scope
  - Delegation with Task tool
  - Y-depth: 1-MAX_DEPTH
```

### Gate Verification Conditionals

```
IF GATE_VERIFICATION_CONFIG specified:
  FOR each gate IN [P4, I4, E4, V4]:
    ACTIVATE subagents FROM config[gate]

IF GATE_VERIFICATION_CONFIG undefined:
  # Progressive defaults
  P4: [context_delegate, verifier_structural]
  I4: [verifier_structural, verifier_semantic]
  E4: [verifier_semantic, verifier_functional]
  V4: [verifier_functional]  # Full evidence required
```

---

## Execution Sequence

The meta-prompt generation follows PIEV with XYZ coordinate tracking.

### Phase 1: Interview (PIEV-P) — X=P, Y=0

**Objective:** Gather all interview-derived variables.

**Workflow:**

1. **Parse USER_PROMPT** for initial signals (keywords, scope hints)

2. **Launch Interview** using AskUserQuestion for:
   - Abstraction layer
   - Intent + Scope
   - Dependencies (propose first, ask user to refine)
   - Risk level
   - Context depth
   - Conditional execution needs
   - Delegation policy
   - Gate verification configuration

3. **Propose Tier Classification** based on collected signals:
   - **Tier C**: atomic scope, low risk, single_file
   - **Tier B**: composed scope, medium risk, cross_file
   - **Tier A**: nested scope, high risk, requires selective delegation
   - **Tier S**: nested scope, high risk, aggressive delegation, cross_project

4. **Ask user to confirm or refine** tier proposal

5. **P4 Gate Check:**
   - Run structural verifier: all interview variables collected?
   - Run semantic verifier: tier classification consistent with signals?
   - IF FAIL → loop back to step 2 for missing/contradictory data

**XYZ Coordinates at P4:** `(P, depth=0, z=[context_delegate, verifier_structural, verifier_semantic])`

### Phase 2: Decomposition (PIEV-I) — X=I, Y=0

**Objective:** Break down prompt into execution components.

**Workflow:**

1. **Decompose** USER_PROMPT into:
   - Purpose (what and why)
   - Context (constraints, assumptions)
   - Instructions (step-by-step)
   - Execution steps (tool invocations)
   - Validation metrics (how to verify success)
   - Improvement mechanism (what if fails)

2. **Map to XYZ Coordinates:**
   - X: Which PIEV stages the generated command will use
   - Y: Recursion depth needed (0=atomic, 1=delegated, 2+=nested)
   - Z: Which verification subagents to activate per gate

3. **Generate XYZ Manifest:**
   ```yaml
   xyz_coordinates:
     x_stages: [P, I, E, V]  # or subset
     y_depth: <derived from INTENT_SCOPE>
     z_active:
       P4: <from GATE_VERIFICATION_CONFIG>
       I4: <from GATE_VERIFICATION_CONFIG>
       E4: <from GATE_VERIFICATION_CONFIG>
       V4: <from GATE_VERIFICATION_CONFIG>
   ```

4. **I4 Gate Check:**
   - Run structural verifier: all 6 decomposition elements present?
   - Run semantic verifier: no contradictions between elements?
   - IF FAIL → identify gaps, loop back to step 1

**XYZ Coordinates at I4:** `(I, depth=0, z=[verifier_structural, verifier_semantic])`

### Phase 3: Generation (PIEV-E) — X=E, Y=0-1

**Objective:** Generate the command file.

**Workflow:**

1. **Select Template** based on INTENT_SCOPE:
   - atomic → linear workflow template
   - composed → control-flow template with `<loop>` blocks
   - nested → delegation template with Task tool patterns

2. **Generate Frontmatter:**
   ```yaml
   ---
   allowed-tools: <derived from ABSTRACTION_LAYER>
   description: <one-line from Purpose>
   argument-hint: <if VARIABLES defined>
   model: <derived from ABSTRACTION_LAYER>
   module: <interaction|reflexion|context>
   xyz: <embedded XYZ manifest>
   doc-class: threads-framework-commands
   ---
   ```

3. **Generate Sections** (order matters):
   - Purpose (what and why)
   - Information (IF tier B+)
   - Context Map (IF tier A+, file references)
   - Variables (IF tier A+, dynamic inputs)
   - Workflow (structured by INTENT_SCOPE)
   - Reflexion (verification metrics + improvement)
   - Report (output format)

4. **Embed Conditionals** from interview:
   - Abstraction layer conditionals in tool selection
   - Scope conditionals in workflow structure
   - Gate conditionals in reflexion section

5. **Include Delegation Patterns** (IF DELEGATION_POLICY != none):
   ```markdown
   ## Workflow
   1. [Prepare context]
   2. Delegate via `Task` tool:
      - subagent_type: [type]
      - prompt: [minimal, focused]
   3. Verify sub-agent output against I/O contract
   4. On failure: retry (max 1), skip, or abort
   5. [Aggregate results]
   ```

6. **E4 Gate Check:**
   - Run structural verifier: all required sections present?
   - Run semantic verifier: conditionals correctly embedded?
   - Run functional verifier: generated command parses as valid markdown?
   - IF FAIL → regenerate with adjustments

**XYZ Coordinates at E4:** `(E, depth=0|1, z=[verifier_semantic, verifier_functional])`

### Phase 4: Verification (PIEV-V) — X=V, Y=0+

**Objective:** Validate generated command meets all criteria.

**Workflow:**

1. **Spawn Z-axis Verification Subagents** using this same meta-prompt-v2 skill:
   - Each subagent receives the generated command
   - Each subagent receives cheating detection criteria
   - Subagents report: `{signal_type, evidence, verdict}`

2. **Collect Verification Reports:**
   ```yaml
   verification_report:
     structural:
       signal: pass|fail
       evidence: "..."
       verdict: "..."
     semantic:
       signal: pass|fail
       evidence: "..."
       verdict: "..."
     functional:
       signal: pass|fail
       evidence: "..."
       verdict: "..."
   ```

3. **V4 Gate Check:**
   - All signals = pass → PROCEED to save
   - Any signal = fail → identify defect, loop back to appropriate phase
   - conditional_pass → apply specified remediation, re-verify

4. **Save Command File** to OUTPUT_DIR

**XYZ Coordinates at V4:** `(V, depth=0+, z=[verifier_functional])`

---

## Error Detection

### Cheating Behavior Detection

**CRITICAL:** Agent must define and detect cheating behaviors.

**Cheating Categories:**

| Category | Description | Detection Signal |
|----------|-------------|------------------|
| Skipped Verification | Agent claims done without evidence | No functional evidence in output |
| Shallow Analysis | Surface-level work when depth required | Context_depth mismatch, unused tools |
| Claimed-Without-Evidence | Assertions without proof | Missing evidence links or test results |
| Scope Creep | Exceeding declared boundaries | Actions outside declared scope |
| Context Pollution | Mixing unrelated concerns | Mixed abstraction levels in output |

**Detection Protocol:**

1. **Prompt user** for cheating behavior guidance (if CHEATING_GUIDANCE not provided)
2. **Define error test scenario** — What would trigger each cheating detector?
3. **Define false positive scenario** — When would detector incorrectly flag?
4. **Define false negative scenario** — When would detector miss real cheating?
5. **Define real negative scenario** — What does honest execution look like?

**Example Detection Matrix:**

```yaml
cheating_detection:
  skipped_verification:
    error_test: "Command outputs 'Done' with no test results or links"
    false_positive: "User explicitly requested quick verification"
    false_negative: "Agent provides fake evidence that looks real"
    real_negative: "Command includes test output, links, or screenshots"

  shallow_analysis:
    error_test: "Single Read tool when cross_file context required"
    false_positive: "Task is genuinely simple, single-file"
    false_negative: "Agent reads many files but doesn't synthesize"
    real_negative: "Multiple reads with synthesis and cross-references"

  claimed_without_evidence:
    error_test: "States 'The function works correctly' without tests"
    false_positive: "Trivial assertion like '1 + 1 = 2'"
    false_negative: "Includes test that doesn't actually verify claim"
    real_negative: "Test output showing function behavior"

  scope_creep:
    error_test: "Modifies files outside declared scope"
    false_positive: "Unforeseen but necessary dependency fix"
    false_negative: "Stays in scope but does unrelated work"
    real_negative: "All modifications map to declared scope"

  context_pollution:
    error_test: "Mixes concept-level and implementation-level steps"
    false_positive: "Legitimate cross-abstraction reasoning"
    false_negative: "Stays at one level but jumps domains"
    real_negative: "Consistent abstraction level throughout"
```

### Verification Subagent Integration

Z-axis subagents are spawned using this same meta-prompt-v2 skill:

```markdown
When spawning a verification subagent:
1. Use Task tool with subagent_type: "general-purpose"
2. Prompt includes:
   - The generated command to verify
   - Cheating detection criteria
   - Specific signal to check (structural/semantic/functional)
3. Subagent reports: {signal_type, evidence, verdict}
4. Main agent aggregates reports for V4 gate decision
```

---

## Error Handling

### Input Validation Errors

| Error Type | Detection | Handling |
|------------|-----------|----------|
| Missing args | USER_PROMPT empty | Prompt user for input |
| Invalid types | Variable outside domain | Reject with valid options, do not proceed |
| Contradictory requirements | Semantic verifier detects conflict | AskUserQuestion to clarify |

### Execution Drift

| Error Type | Detection | Handling |
|------------|-----------|----------|
| Agent off-spec | Z-subagent structural check | Report deviation, loop back |
| Scope creep | Boundary check fails | Identify excess, trim or get approval |
| Context pollution | Semantic verifier rejects | Identify mixed levels, restructure |

### Output Contract Violations

| Error Type | Detection | Handling |
|------------|-----------|----------|
| Missing deliverables | Structural verifier | List missing items, regenerate |
| Wrong format | Semantic verifier | Reformat with correct structure |
| Incomplete coverage | Functional verifier | Identify gaps, extend coverage |

### Gate Failure Handling

| Gate | On FAIL | Loop Target |
|------|---------|-------------|
| P4 | Refine interview data, re-classify tier | Phase 1, Step 2 |
| I4 | Revise decomposition, fix gaps | Phase 2, Step 1 |
| E4 | Regenerate with adjusted parameters | Phase 3, Step 1 |
| V4 | Collect missing evidence | Phase 3 or Phase 4 |

**Maximum Loop Iterations:** 2 per gate (prevents runaway)

---

## Report

**Output Format:**

```
**Command:** [command-name]
**XYZ Coordinates:** (X=[PIEV stages], Y=[depth], Z=[active subagents])
**Tier:** [C|B|A|S] — [derived from interview]
**Abstraction Layer:** [concept|tech_stack|implementation]
**Scope:** [atomic|composed|nested]
**Gate Config:**
  - P4: [subagents]
  - I4: [subagents]
  - E4: [subagents]
  - V4: [subagents]

**Save to:** `$OUTPUT_DIR/[command-name].md`
**Invoke with:** `/[command-name] [args]`

---

[Complete generated command file content]
```

---

## References

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `allowed-tools` | Yes | Comma-separated list of permitted tools |
| `description` | Yes | One-line description for `/` menu |
| `argument-hint` | No | Placeholder for required arguments |
| `model` | No | `opus`, `sonnet`, or `haiku` |
| `module` | Yes | `interaction`, `reflexion`, or `context` |
| `xyz` | No | Embedded XYZ coordinate manifest |
| `doc-class` | No | Document classification |

### XYZ Coordinate Reference

| Axis | Name | Values | Meaning |
|------|------|--------|---------|
| X | PIEV Progression | P, I, E, V + gates | Current execution phase |
| Y | Recursion Depth | 0, 1, 2, ..., MAX_DEPTH | Decomposition level |
| Z | Verification Subagents | context_delegate, verifier_* | Active checkers |

**Coordinate Tuple:** `(x_stage_or_gate, y_depth, z_active_subagents)`

**Navigation Questions:**
1. X: Which quadrant or gate checkpoint am I in?
2. Y: What depth am I operating at?
3. Z: Which verifier subagents are active/pending?

### Interaction Rules

- At every Y depth, X progression still follows PIEV
- Recursion can trigger from any X stage, but each child runs full PIEV
- Z-axis checks are mandatory at configured gates before X can advance
- A gate FAIL blocks progression until defects resolved with explicit evidence
