---
name: systematic-thinking
description: "A meta-framework for systematic problem decomposition and validation. Teaches agents to assess problem scale (horizontal vs vertical), design execution strategies with dependency analysis, and apply validation at each execution node. Abstract methodology that maps to agent.py thread types."
aliases: [systematic, decomposition, validation-framework]
---

# Systematic Thinking Framework

<framework>
  <name>Systematic Thinking</name>
  <type>Meta-Framework</type>
  <purpose>Systematic problem decomposition and validation</purpose>
  <mapping>agent.py thread types (BASE, C-thread, L-thread)</mapping>
</framework>

A meta-framework for approaching complex problems through systematic decomposition, dependency-aware execution, and validation at each node. This framework teaches agents to think before executing—mapping scale, dependencies, and validation strategies before invoking any thread type.

## Core Philosophy

**Ideas cannot be validated through logic alone.** Every validation method based purely on reasoning—falsification, constraints, scenarios, first principles—is still just *reasoning about reasoning*.

```
Whole Idea    →  Can't test    →  Only logic
                     ↓
        First Principles Decomposition
                     ↓
Atomic Principle  →  CAN prototype  →  CAN run  →  Real pass/fail
```

The solution: **decompose whole ideas into atomic principles, execute them in isolation, and validate against reality.**

---

## Component 1: Problem Scale Assessment

<component id="scale-assessment">
  <purpose>Determine problem structure before execution</purpose>
  <decision>horizontal vs vertical</decision>
</component>

Before any execution, determine whether the problem is **horizontal** or **vertical**:

### Horizontal Problems (Breadth-First Exploration)

**Characteristics:**
- Multiple valid approaches exist
- Parallel exploration is valuable
- Components can be validated independently
- Early divergence of paths is beneficial
- The "best" answer is discovered through comparison

**Indicators:**
- "What are the options for..."
- "Explore multiple approaches"
- "Design a system with multiple valid architectures"
- "We could go in several directions"

**Execution Strategy:**
- Spawn multiple parallel explorations
- Each exploration can validate independently
- Results are compared and fused at the end
- Kill failed branches early, continue with successful ones

**Example:**
```
Problem: "Design a payment system"
  ├─ Approach A: Direct Stripe integration
  ├─ Approach B: Payment processor aggregator (Paddle)
  └─ Approach C: Crypto payment option

All three can be explored in parallel, then compared.
```

### Vertical Problems (Depth-First Execution)

**Characteristics:**
- Each phase depends on previous output
- Checkpoints are critical for alignment
- Single path with refinement loops
- Verification gates are essential
- The "correct" answer is discovered through iteration

**Indicators:**
- "Implement this feature"
- "Fix this bug"
- "Migrate this system"
- "Complete this workflow"

**Execution Strategy:**
- Sequential phase execution with gates
- Each phase must pass before proceeding
- Iterative refinement until validation passes
- Linear progression from start to finish

**Example:**
```
Problem: "Migrate database schema"
  ├─ Phase 1: Inventory (must finish before design)
  ├─ Phase 2: Design (depends on inventory)
  └─ Phase 3: Migration (depends on design)

Sequential dependency chain—parallel execution not possible.
```

### Scale Assessment Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│  START: What is the nature of this task?                   │
│                                                             │
│  Can this be broken into independent explorations?          │
│    ├── YES → Horizontal problem                            │
│    │        Spawn parallel streams, compare results        │
│    │                                                        │
│    └── NO  → Vertical problem                              │
│             Sequential phases, verification gates          │
└─────────────────────────────────────────────────────────────┘
```

---

## Component 2: Execution Dependency Framework

<component id="dependency-framework">
  <purpose>Map system dependencies to determine parallelization</purpose>
  <output>Execution strategy and dependency graph</output>
</component>

Map system dependencies to determine parallelization potential and execution strategy.

### Dependency Analysis Matrix

For each component or phase in the problem, answer:

#### 1. Input Dependencies
- What data, configuration, or code must exist first?
- Can these inputs be acquired in parallel?
- Or must they be acquired sequentially?

#### 2. Execution Isolation
- Can this component run in an isolated environment?
- Does it share state with other components?
- What are the potential conflicts if run in parallel?
- Can this be safely rolled back if it fails?

#### 3. Output Contracts
- What does this component produce?
- Do other components consume this output?
- Is the output schema stable and well-defined?
- What is the interface between components?

#### 4. Verification Requirements
- How do we know this component succeeded?
- Can verification be automated with objective checks?
- Or does it require subjective judgment?
- What are the specific pass/fail criteria?

### Dependency Patterns and Execution Strategies

| Dependency Pattern | Characteristics | Strategy |
|--------------------|-----------------|----------|
| **Independent** | No shared inputs/outputs, no state conflicts | Parallel execution, any order |
| **Sequential** | Output of A is input to B | Phase gates, A must complete before B |
| **Iterative** | Refinement loop until quality threshold | Verification loop, exit when criteria met |
| **Mixed** | Some independent, some sequential | Hybrid: parallel branches with phase gates |

### Execution Mapping

Once dependencies are mapped, determine execution approach:

```
┌─────────────────────────────────────────────────────────────┐
│  DEPENDENCY MAPPING OUTPUT                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Component/Phase: [Name]                                    │
│  ├─ Input Dependencies: [list]                             │
│  ├─ Can Run In Parallel With: [list of other components]   │
│  ├─ Output: [what it produces]                             │
│  ├─ Consumers: [who uses the output]                       │
│  ├─ Merge Conflicts: [potential issues]                    │
│  └─ Verification: [how to validate]                        │
│                                                             │
│  [Repeat for each component/phase]                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Component 3: Meta Validation Framework

<component id="validation-framework">
  <purpose>Define validation strategy for each execution node</purpose>
  <output>Pass/fail criteria and evidence data</output>
</component>

Every execution node requires validation. The meta-framework ensures precise, effective validation at each node.

### Validation Methods

**Objective Validation (Automated, Binary)**
- Tests pass/fail
- Build succeeds/fails
- Service responds/doesn't respond
- File exists/doesn't exist
- Exit code is 0/non-zero

**Subjective Validation (Judgment-Based)**
- Code quality assessment
- Security review
- User experience evaluation
- Architecture soundness
- Strategic alignment

### Validation Strategy Template

For each execution node, define:

```
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION NODE: [Name]                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Input: [What this node receives]                          │
│  Output: [What this node produces]                         │
│                                                             │
│  Validation Method:                                        │
│    □ Objective (automated check)                           │
│    □ Subjective (judgment-based)                           │
│    □ None (fire-and-forget)                                │
│                                                             │
│  Pass Criteria:                                            │
│    - [Specific outcome 1]                                  │
│    - [Specific outcome 2]                                  │
│                                                             │
│  Fail Criteria:                                            │
│    - [What indicates failure]                              │
│                                                             │
│  Inconclusive Criteria:                                    │
│    - [What requires re-testing]                            │
│                                                             │
│  Max Attempts: [Number before giving up]                   │
│                                                             │
│  On Pass:                                                  │
│    - [What becomes unblocked]                              │
│    - [What output passes forward]                          │
│                                                             │
│  On Fail:                                                  │
│    □ Retry with refined input                              │
│    □ Terminate this branch                                 │
│    □ Fallback to alternative approach                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Validation-Level Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│  Does this node require validation?                        │
│                                                             │
│  NO → Fire-and-forget execution                            │
│  (Simple one-off task, no quality gate needed)             │
│                                                             │
│  YES → What type of validation?                            │
│                                                             │
│    Objective (automated check possible)                    │
│      → Iterative execution until check passes              │
│      → Binary pass/fail, clear exit criteria               │
│      → Example: run tests until they all pass              │
│                                                             │
│    Subjective (requires judgment)                          │
│      → Single execution with quality review                │
│      → Output assessed against principles                  │
│      → Example: review code for security issues             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## The Nested Execution Pattern

<pattern name="Nested Decomposition and Validation">
  <type>Multi-Level Execution Pattern</type>
  <purpose>Complex problem decomposition with validation at each node</purpose>
</pattern>

For complex problems, use the nested execution pattern:

### Pattern Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  NESTED EXECUTION PATTERN                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Level 0: Parallel Ideation Streams                                         │
│  │                                                                          │
│  │   Spawn multiple independent approach explorations                      │
│  │   Each stream explores a different angle or solution strategy          │
│  │                                                                          │
│  Level 1: Refinement Loop                                                   │
│  │   └─ Each stream goes through iterative refinement                     │
│  │      Challenge assumptions, compress to essentials                     │
│  │                                                                          │
│  Level 2: First Principles Decomposition                                   │
│  │   └─ Break refined idea into atomic, testable principles               │
│  │      Each principle should be independently validatable                 │
│  │                                                                          │
│  Level 3: Per-Principle Validation                                         │
│  │                                                                          │
│  │   for principle in principles:                                          │
│  │       Construct ──► Build minimal testable artifact                    │
│  │              │                                                           │
│  │              ▼                                                           │
│  │       Loop/Test ───► Validate with objective or subjective check        │
│  │              │                                                           │
│  │              ▼                                                           │
│  │       Fuse Result ──► Pass/fail verdict with evidence                  │
│  │                                                                          │
│  Level 2: Feedback Integration                                              │
│  │   └─ Incorporate validation results back into idea                      │
│  │      Adapt idea based on what passed/failed                            │
│  │                                                                          │
│  Level 2: Fuse Principles                                                   │
│  │   └─ Compose validated principles into coherent idea                    │
│  │                                                                          │
│  Level 0: Final Fusion                                                      │
│      └─ Select best validated stream, present to user                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stage Definitions

| Stage | Purpose | Output | Exit Criteria |
|-------|---------|--------|---------------|
| **Ideation** | Explore multiple directions | Candidate streams | All streams spawned |
| **Refinement** | Stress-test through dialectic | Refined concept | Idea stable, assumptions clear |
| **Decomposition** | Break into testable units | Atomic principles | All principles extracted |
| **Construct** | Build minimal prototype | Testable artifact | Prototype ready |
| **Loop/Test** | Run validation | Evidence data | Pass/fail determined |
| **Fuse Result** | Verdict with evidence | Binary + learnings | Verdict assigned |
| **Feedback** | Integrate validation | Updated idea | All principles processed |
| **Fuse Principles** | Compose validated parts | Composite idea | Validated composite produced |
| **Final** | Select best stream | Recommendation | All streams compared |

---

## Workflow

<workflow>
  <step id="1">Assess Problem Scale</step>
  <step id="2">Map Dependencies</step>
  <step id="3">Design Validation Strategy</step>
  <step id="4">Execute According to Strategy</step>
  <step id="5">Validate and Fuse</step>
</workflow>

### Step 1: Assess Problem Scale

**Question: Is this horizontal or vertical?**

```
Horizontal Indicators:
- "Explore options"
- "What are the approaches"
- "Design system with multiple valid architectures"
- "Compare alternatives"

Vertical Indicators:
- "Implement feature"
- "Fix bug"
- "Migrate system"
- "Complete workflow"
```

### Step 2: Map Dependencies

**For horizontal problems:** Map parallel streams
```
Stream A: [Approach name]
  - Dependencies: [Inputs needed]
  - Parallel with: [Other streams]
  - Output: [What it produces]
  - Conflicts: [Potential merge issues]
```

**For vertical problems:** Map phase chain
```
Phase 1: [Name]
  - Input: [Starting state]
  - Output: [Deliverable for next phase]
  - Blocks: [What depends on this]
```

### Step 3: Design Validation Strategy

**For each execution node:**
- What validation method? (Objective / Subjective / None)
- What are pass/fail criteria?
- What happens on success? (What unblocks?)
- What happens on failure? (Retry / Terminate / Fallback?)

### Step 4: Execute According to Strategy

**Horizontal:**
- Spawn all independent streams
- Monitor each for completion
- Collect results from successful streams
- Compare and fuse results

**Vertical:**
- Execute phases sequentially
- Verify each phase before proceeding
- Iterate if validation fails
- Proceed only when pass criteria met

### Step 5: Validate and Fuse

**For parallel streams:**
- Which streams passed validation?
- Compare outputs for conflicts
- Select based on: validation scores, strategic fit, integration cost

**For sequential phases:**
- Verify all phases completed
- Check end-to-end integration
- Present final result with evidence trail

---

## Examples

<examples>
  <example id="1" type="horizontal">API Architecture - Real-time Features</example>
  <example id="2" type="vertical">Database Schema Migration</example>
  <example id="3" type="iterative">Test Suite Fixing</example>
  <example id="4" type="composite">Collaborative Text Editor (Nested Pattern)</example>
</examples>

### Example 1: Horizontal Problem - API Architecture

**Problem:** "We need to add real-time features. What's the best approach?"

```
┌─────────────────────────────────────────────────────────────┐
│  SCALE: HORIZONTAL                                          │
│  Multiple valid approaches exist, parallel exploration      │
│  valuable to compare options                                │
└─────────────────────────────────────────────────────────────┘

PARALLEL STREAMS:
┌─────────────────────────────────────────────────────────────┐
│  Stream A: WebSocket with server push                       │
│  ├─ Dependencies: Server config, client library            │
│  ├─ Output: Real-time data flow                            │
│  ├─ Validation: Can server push to 1000 concurrent clients?│
│  └─ Parallel with: All other streams                       │
│                                                             │
│  Stream B: Server-Sent Events (SSE)                         │
│  ├─ Dependencies: HTTP server, client EventSource          │
│  ├─ Output: Unidirectional real-time updates               │
│  ├─ Validation: Can server sustain 1000 SSE connections?   │
│  └─ Parallel with: All other streams                       │
│                                                             │
│  Stream C: Polling with caching                             │
│  ├─ Dependencies: Cache layer, client polling logic        │
│  ├─ Output: Near real-time with lower server load          │
│  ├─ Validation: Can cache handle 10000 requests/second?    │
│  └─ Parallel with: All other streams                       │
└─────────────────────────────────────────────────────────────┘

EXECUTION STRATEGY:
- Spawn all three streams in parallel isolated environments
- Each stream builds prototype and validates independently
- Collect results, compare based on: performance, complexity, scalability
- Select best approach for full implementation
```

### Example 2: Vertical Problem - Database Migration

**Problem:** "Migrate PostgreSQL schema v1 to v2 without downtime"

```
┌─────────────────────────────────────────────────────────────┐
│  SCALE: VERTICAL                                            │
│  Sequential dependency chain, each phase must complete      │
│  before next begins                                         │
└─────────────────────────────────────────────────────────────┘

PHASE DEPENDENCY CHAIN:
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Schema Inventory                                 │
│  ├─ Input: Current database (v1)                           │
│  ├─ Output: Complete inventory of tables, columns, data    │
│  ├─ Validation: inventory.json exists and is complete      │
│  └─ Blocks: Design phase cannot start without this         │
│                                                             │
│  Phase 2: Migration Design                                 │
│  ├─ Input: inventory.json                                  │
│  ├─ Output: Migration plan with SQL scripts                │
│  ├─ Validation: Plan reviewed and approved                 │
│  └─ Blocks: Implementation depends on approved plan         │
│                                                             │
│  Phase 3: Shadow Database Setup                             │
│  ├─ Input: Migration plan                                  │
│  ├─ Output: v2 database with migrated data                 │
│  ├─ Validation: v2 data matches v1, no data loss           │
│  └─ Blocks: Validation needs v2 database running           │
│                                                             │
│  Phase 4: Data Validation                                  │
│  ├─ Input: v1 and v2 databases                             │
│  ├─ Output: Validation report showing data parity          │
│  ├─ Validation: All data parity checks pass                │
│  └─ Blocks: Cutover needs verified data                    │
│                                                             │
│  Phase 5: Zero-Downtime Cutover                             │
│  ├─ Input: Validated v2 database                           │
│  ├─ Output: Application running on v2                      │
│  ├─ Validation: Application healthy, v1 retired            │
│  └─ Blocks: Final phase                                    │
└─────────────────────────────────────────────────────────────┘

EXECUTION STRATEGY:
- Execute phases sequentially
- Each phase must validate before proceeding
- If any phase fails, stop and address before continuing
- No parallel execution possible due to dependencies
```

### Example 3: Iterative Validation - Test Fixing

**Problem:** "The tests are failing. Fix them."

```
┌─────────────────────────────────────────────────────────────┐
│  SCALE: VERTICAL with ITERATION                             │
│  Requires repeated execution until validation passes        │
└─────────────────────────────────────────────────────────────┘

EXECUTION NODE:
┌─────────────────────────────────────────────────────────────┐
│  Input: Failing test suite                                  │
│  Output: All tests passing                                  │
│                                                             │
│  Validation Method: Objective (automated)                  │
│  - Run test suite                                          │
│  - Check exit code (0 = pass)                              │
│  - Count passing vs failing tests                          │
│                                                             │
│  Pass Criteria:                                            │
│  - All tests pass (exit code 0)                            │
│  - No test failures or errors                              │
│                                                             │
│  Fail Criteria:                                            │
│  - Any test fails or errors                                │
│                                                             │
│  Max Attempts: 20                                          │
│                                                             │
│  On Fail:                                                  │
│  - Retry with refined prompt including test output         │
│  - Focus on specific failing tests                         │
│                                                             │
│  On Pass:                                                  │
│  - Present fixed code with test report                     │
└─────────────────────────────────────────────────────────────┘

EXECUTION STRATEGY:
- Iterative execution loop
- Each iteration: fix tests → run validation
- Continue until all tests pass or max attempts reached
- Each iteration learns from previous test output
```

### Example 4: Nested Pattern - Complex Feature

**Problem:** "We need to build a collaborative text editor. How should we approach this?"

```
┌─────────────────────────────────────────────────────────────┐
│  SCALE: HORIZONTAL → VERTICAL COMPOSITE                    │
│  Multiple architecture approaches (horizontal)             │
│  Each approach requires validation (vertical)              │
└─────────────────────────────────────────────────────────────┘

LEVEL 0: Parallel Architecture Streams
┌─────────────────────────────────────────────────────────────┐
│  Stream A: CRDT-based (Conflict-free Replicated Types)     │
│  Stream B: OT-based (Operational Transformation)           │
│  Stream C: Centralized with server lock                    │
└─────────────────────────────────────────────────────────────┘

LEVEL 1: Refinement (Stream A example)
┌─────────────────────────────────────────────────────────────┐
│  Refined Concept: "Use Yjs CRDT library with             │
│  WebSocket transport for real-time sync"                  │
└─────────────────────────────────────────────────────────────┘

LEVEL 2: First Principles Decomposition
┌─────────────────────────────────────────────────────────────┐
│  Principle 1: Yjs can sync document state in real-time    │
│  Principle 2: WebSocket connection is reliable enough     │
│  Principle 3: CRDT merge produces expected results        │
│  Principle 4: Users can handle eventual consistency       │
└─────────────────────────────────────────────────────────────┘

LEVEL 3: Per-Principle Validation
┌─────────────────────────────────────────────────────────────┐
│  P1: Yjs syncs in real-time                                │
│    Construct: Prototype two browser windows editing        │
│    Loop: Measure sync latency, observe merge behavior      │
│    Fuse: PASS if latency <100ms, merges are correct        │
│                                                             │
│  P2: WebSocket reliable enough                             │
│    Construct: Prototype with connection loss simulation    │
│    Loop: Test reconnection, measure recovery time          │
│    Fuse: PASS if recovers in <2s with no data loss        │
│                                                             │
│  P3: CRDT merge correctness                                │
│    Construct: Prototype concurrent edit scenarios           │
│    Loop: Test all merge patterns, verify results           │
│    Fuse: PASS if all merge scenarios produce correct state │
│                                                             │
│  P4: Users accept eventual consistency                     │
│    Construct: User testing with interface mockup           │
│    Loop: Observe user reactions to sync delays             │
│    Fuse: PARTIAL if users notice lag, add visual indicator │
└─────────────────────────────────────────────────────────────┘

LEVEL 2: Feedback Integration
┌─────────────────────────────────────────────────────────────┐
│  Adaptation: Based on P4 PARTIAL result                    │
│  - Add visual sync state indicator                         │
│  - Show "saving..." during sync                            │
└─────────────────────────────────────────────────────────────┘

LEVEL 0: Final Fusion
┌─────────────────────────────────────────────────────────────┐
│  Stream Results:                                           │
│  - Stream A (CRDT): 3/4 PASS, 1 PARTIAL with adaptation    │
│  - Stream B (OT): 2/4 PASS, 2 FAIL (too complex)           │
│  - Stream C (Centralized): 4/4 PASS but doesn't scale      │
│                                                             │
│  Winner: Stream A with P4 adaptation                       │
│  Proceed: CRDT implementation + sync indicators            │
└─────────────────────────────────────────────────────────────┘
```

---

## Mapping to Thread Types

<mapping>
  <source>Systematic Thinking Framework</source>
  <target>agent.py Thread Types</target>
</mapping>

This meta-framework maps to agent.py thread types:

| Framework Concept | Thread Type | Characteristics |
|-------------------|-------------|-----------------|
| Simple question/answer | BASE | One-off, no validation |
| Multi-phase with checkpoints | C-thread | Sequential phases, pause at each |
| Iterative with validation | L-thread | Loop until objective check passes |
| Parallel exploration | Multiple C-threads | Isolated worktrees, compare results |
| Nested decomposition pattern | Nested threads | Parallel streams with per-node validation |

---

## Key Principles

<principles>
  <principle id="1" priority="critical">Assess Scale First</principle>
  <principle id="2" priority="critical">Map Dependencies Explicitly</principle>
  <principle id="3" priority="critical">Define Validation Before Execution</principle>
  <principle id="4" priority="high">Respect Dependency Chains</principle>
  <principle id="5" priority="high">Kill Early, Kill Cheap</principle>
  <principle id="6" priority="high">Evidence Over Logic</principle>
</principles>

### 1. Assess Scale First
The horizontal vs vertical determination drives the entire execution strategy. Don't execute without clarifying this first.

### 2. Map Dependencies Explicitly
Never assume independence. Explicitly map what each component needs and produces before deciding on parallelization.

### 3. Define Validation Before Execution
Pass/fail criteria must be clear before any execution begins. "See if it works" is not a validation strategy.

### 4. Respect Dependency Chains
Sequential dependencies cannot be parallelized. Phase gates exist for a reason—don't bypass them.

### 5. Kill Early, Kill Cheap
A principle failure at the validation stage costs hours. A failure after full implementation costs weeks/months.

### 6. Evidence Over Logic
Validation produces evidence (pass/fail data). Logic alone produces only arguments. Trust evidence.

---

## Verification Metrics

<verification_metrics>
Scale assessed before execution (horizontal vs vertical determined)
Dependencies mapped explicitly for each component
Validation criteria defined upfront with pass/fail thresholds
Isolation used for parallel streams (no shared state conflicts)
Execution rationale documented at each decision point
</verification_metrics>

## Improvement Mechanism

<improvement_mechanism>
If validation skipped for quality gates → add verification node before proceeding
If sequential dependencies parallelized → restructure as phase chain with gates
If success criteria vague ("done", "complete") → define specific observable outcomes
If partial results ignored (PARTIAL state) → trigger adaptation before continuing
If proceeding without evidence → halt and construct minimal testable artifact first
</improvement_mechanism>

---

*Version: 1.0.0*
*Framework: Nested Decomposition and Validation*
*Last Updated: 2025-01-25*
