---
doc-class: mlre-prompt
prompt-type: control-flow
difficulty: S
module: orchestration
---

# MLRE Orchestration Control-Flow
## X/Y/Z Orthogonal Scalability: Phases (X) + Recursion Depth (Y) + Lateral Subagents (Z)

## Information

### Objective

Define a reusable orchestration control-flow where:

1. **X axis (Horizontal phases):** A strict sequential reliance chain at the current scope: `A -> B -> C -> D -> E`.
2. **Y axis (Vertical depth / recursion):** A bounded recursion stack inside the same workflow instance: `LAYER(1..N)`.
3. **Z axis (Lateral subagents):** One-shot, non-recursive sidecar agents spawned at the same `(phase=X, depth=Y)` coordinate to:
   - delegate context reading and summarization,
   - critique and risk-scan,
   - produce verification evidence (tool runs),
   - perform bounded utility work.

4. Parallel execution is allowed only under explicitly proven non-coupling rules (wave policy).
5. Integration is two-dimensional:
   - **Vertical integration:** `LAYER(y+1) -> LAYER(y)` upward only.
   - **Horizontal integration:** every transition `X -> X+1` requires gate evaluation, including integration + end-to-end validation evidence at the current `(X,Y)` scope.

This framework is **use-case independent**. Domain adapters supply what “integration validation” and “end-to-end validation” mean and what evidence artifacts are required.

---

## Coordinate Model (X/Y/Z)

### Node Coordinate
A unit of orchestration state is a node:
- `NODE = (PHASE=X, DEPTH=Y)`

### Axis Semantics
- **X movement** changes phase state (A->B->C->D->E). Only allowed with a verifier credential.
- **Y movement** changes recursion depth (spawn deeper decomposition at same phase). Only allowed when Phase C authorizes recursion and when wave boundary rules permit instantiation.
- **Z movement** spawns one-shot sidecars at the same node. Z does not advance phase and does not create new recursion depth.

### Orthogonality Constraints (non-bypass rules)

1) Z-subagents do not advance X:
- Sidecars may propose, critique, and produce evidence, but cannot authorize `X -> X+1`.

2) Z-subagents do not create Y:
- Sidecars do not spawn deeper branches and do not define integration contracts.
- If a sidecar discovers the need for new decomposition, the orchestrator must update Phase C artifacts and re-run the C gate.

3) Z-subagents must not introduce coupling:
- Sidecars must not create dependency edges between same-wave branches.
- If a sidecar modifies artifacts, that modification is treated as a normal deliverable subject to boundary rules and gates.

---

## Parameters (Must be declared for each MLRE run)

### X-axis parameters
- `PHASES = [A, B, C, D, E]` (or extended sequence)
- `BRANCH_LOCAL_PHASE_POLICY = full(A'..E') | compressed | none`

### Y-axis parameters
- `MAX_DEPTH = N`
- `ROLE_MAP(y)` assigns behaviors to depth boundaries (not fixed names)

Recommended defaults:
- `ROLE_MAP(1) = Orchestrator`
- `ROLE_MAP(2) = Dispatcher` (optional; activate when branch count or complexity warrants)
- `ROLE_MAP(3..MAX_DEPTH-1) = Recursive Branch Executor`
- `ROLE_MAP(MAX_DEPTH) = Leaf Executor` (no spawn)

### Parallelization + dependency invariants
- `WAVE_POLICY = enabled | disabled`
- `FORBID_SAME_WAVE_COUPLING = true`
- `FORBID_DEPENDENCY_RELIANCE_MUTATION = true`
- `ALLOW_PARTIAL_INTEGRATION = true | false (bounded)`

### Z-axis parameters
- `Z_SUBAGENTS_ENABLED = true | false`
- `Z_SUBAGENT_BUDGET = max_count | max_tokens | max_time` (implementation-specific)
- `Z_SUBAGENT_ALLOWED_ACTIONS = {context_read, critique, evidence_generation, utility}`

### Adapter parameters (domain-specific)
Your project provides:
- definitions of integration validation and end-to-end validation
- required evidence artifact types and pass criteria
- acceptable risk policies for CONDITIONAL passes (L0 authority)

---

## Hard Rules (Non-Negotiable)

### R1 — Natural-language-only prompts at delegation boundaries
All prompts to any agent (including Z subagents) are natural-language imperative task descriptions.
No embedded shell/CLI blocks inside prompts.

### R2 — Downward directives, upward suggestions
Parents direct children. Children suggest next steps upward.

### R3 — Leaf nodes are workflow-blind
Leaf prompts contain only local objective, boundary, constraints, success criteria, evidence requirements.

### R4 — Parallelism requires proof
Wave concurrency is allowed only when non-coupling is proven. Otherwise serialize/regroup.

### R5 — Dependency reliance is invariant per planned scope
No branch-specific reliance semantics mutation. Shared immutable baseline allowed.

### R6 — Integration is two-dimensional
- Vertical: upward-only across depth boundaries.
- Horizontal: gate evidence required before advancing phases.

---

## MLRE Phase Machine (X-axis)

For each phase, define:
- phase purpose
- required outputs (artifact *types*, not filenames)
- decision logic (why this exists)
- spawn permissions (Y recursion) and Z-sidecar allowances
- horizontal gate requirements before moving to the next phase

### Phase A — Requirements, Constraints, Boundary Lock

**Purpose**
Freeze intent before scaling compute (Y recursion) and before building dependency models (B).

**Primary outputs**
- objective definition
- scope boundary (in/out, forbidden zones)
- constraints (hard/soft)
- acceptance criteria (observable)
- assumptions + non-goals

**Y permissions**
- No recursion authorization.
- No branch execution.

**Z permissions (orthogonal)**
Allowed: context delegation and critique.
Examples:
- Z(Context Delegate): summarize existing project context and relevant files.
- Z(Critique): identify ambiguity, missing acceptance criteria, and boundary conflicts.

**Horizontal gate A->B**
Before B, require integration + end-to-end validation evidence appropriate to the domain adapter:
- Integration validation: internal consistency of A artifacts.
- End-to-end validation: “criteria evaluability” proof (criteria can be tested/validated).

---

### Phase B — Dependency, Impact, Parallelization Model

**Purpose**
Construct a dependency model and candidate parallel zones that remain invariant under decomposition.

**Primary outputs**
- dependency reliance graph (explicit)
- impact analysis
- candidate parallel zones (hypotheses + justification)
- invariants list (what cannot vary per branch)

**Y permissions**
- No deep recursion instantiation.
- May create draft branch candidates, but final branch specs are in Phase C.

**Z permissions**
Allowed: dependency mapping, coupling hazard detection, parallel-zone proposals, evidence generation.
Examples:
- Z(Dependency Mapper): produce reliance graph and note weak/unknown edges.
- Z(Parallel Zone Finder): propose wave candidates with disjointness rationale.
- Z(Coupling Auditor): search for hidden shared mutable scope risks.

**Horizontal gate B->C**
Require integration + end-to-end evidence:
- Integration validation: dependency model consistent with Phase A boundaries.
- End-to-end validation: “dependency feasibility” evidence (adapter-defined).

---

### Phase C — Decomposition + Wave Plan + Integration Points + Verify-Plan

**Purpose**
Create the plan that makes execution deterministic:
- bounded branch specs,
- wave plan,
- recursion permissions,
- integration points,
- verify-plan consistency proof.

**Primary outputs**
- branch specs with explicit boundaries and contracts
- wave plan (W1..Wk) with entry/exit gates
- integration points (partial/full) + conditions
- recursion authorization policy (which branches may spawn deeper, where, when)
- verify-plan report (no contradiction / no circularity / no impossible ordering)

**Y permissions**
This phase is the only place that authorizes:
- which child branches exist,
- which branches may recurse (Y+1),
- under what conditions recursion instantiates (Phase D wave boundaries only).

**Z permissions**
Allowed: plan critique, logical fallacy detection, boundary overlap audit, evidence generation.
Examples:
- Z(Plan Consistency Checker): look for circular deps, self-satisfying gates, impossible wave ordering.
- Z(Boundary Auditor): check for overlaps and forbidden-zone violations.
- Z(Integration Sentinel): validate declared integration points against invariants.

**Horizontal gate C->D (Verify-Plan hard gate)**
Require:
- Integration validation: coherence across A+B+C artifacts.
- End-to-end validation: plan dry-run / simulation evidence (adapter-defined).

---

### Phase D — Wave-Based Execution + Bounded Integration

**Purpose**
Execute branches under wave policy, integrate only at declared boundaries, and enforce micro-gates.

**Primary outputs**
- per-wave execution report(s)
- per-branch evidence bundles
- integration reports (partial/full)
- incident log (boundary/coupling/dependency)

**Y permissions**
- Recursion instantiation is allowed only:
  - if predeclared in Phase C,
  - at wave boundaries,
  - within depth budget.

**Z permissions**
Allowed: evidence generation, regression scouting, integration verification, post-wave critique.
Examples:
- Z(Evidence Runner): generate evidence bundles (tests/backtests/QA runs).
- Z(Regression Scout): locate failures and summarize.
- Z(Coupling Sentinel): verify no same-wave reliance appeared in practice.

**Horizontal gates inside D**
- Wave entry gate (start Wn)
- Wave exit gate (complete Wn + evidence + incidents)
- Integration point gate (only integrate when conditions match Phase C declarations)

**Horizontal gate D->E**
Require integration + end-to-end evidence that the current scope is integration-ready.

---

### Phase E — Final Integration + End-to-End Acceptance Proof

**Purpose**
Prove milestone completion at the scope level with evidence aligned to Phase A criteria.

**Primary outputs**
- final integration report
- end-to-end validation report
- acceptance proof bundle (mapped to Phase A criteria)
- residual risk ledger (explicit)

**Z permissions**
Allowed: evidence curation, adversarial review, completeness audit.
Examples:
- Z(Evidence Curator): ensure acceptance-proof bundle completeness and traceability.
- Z(Adversarial Reviewer): attempt to falsify “pass” claims.

**Closure gate**
Close only with integration + end-to-end proof (adapter-defined) and explicit handling of residual risk.

---

## Two-Agent Roundtable Mode (Orchestrator ↔ Verifier) with Z-sidecars

### Roles
- **Orchestrator agent**: constructs Phase Packets for A..E; may spawn Z-subagents for context/critique/evidence.
- **Verifier agent**: evaluates requested gates with phase-specific lenses; may spawn Z-subagents to independently validate evidence; issues gate credentials.

### Contracts

#### Phase Packet (Orchestrator -> Verifier)
- Phase: X
- Scope: node coordinate `(X,Y)`
- Artifacts: produced types + pointers
- Decisions: what was decided and why
- Invariants: what is frozen
- Z-Outputs: (optional) attached sidecar reports with provenance
- Gate Request: transition `X -> next` + expected evidence types

#### Gate Packet (Verifier -> Orchestrator)
- Gate: `X -> next`
- Assessment: Structural/Semantic/Functional with phase lens
- Verdict: PASS | FAIL | CONDITIONAL_PASS
- Credential: token if PASS/CONDITIONAL_PASS
- Required Fixes: minimal delta
- Routing: redo X, or return to earlier phase

### Rule
No phase transition occurs without a valid verifier credential token.
Z-sidecar outputs inform decisions but do not authorize transitions.

---