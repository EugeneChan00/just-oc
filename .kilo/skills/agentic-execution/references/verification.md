---
doc-class: mlre-prompt
prompt-type: control-flow
difficulty: S
module: verification
---

# MLRE Verification Control-Flow
## Phase-Specific Three-Signal Lenses + X/Y/Z Evidence Handling

## Information

### Objective

Provide a verification procedure that:

1. Applies three-signal assessment (Structural, Semantic, Functional) to MLRE artifacts.
2. Applies those signals phase-by-phase (A–E) with phase-specific interpretation.
3. Enforces **horizontal integration gates** between phases at the same depth.
4. Enforces **vertical integration gates** for handoffs across depth boundaries.
5. Treats **Z-axis subagent outputs** as orthogonal evidence sources:
   - Z outputs may provide context, critique, or evidence generation,
   - but do not themselves authorize phase transitions or modify invariants without re-gating.

The verification logic is context-invariant; the evidence types and validation methods are supplied by a domain adapter.

---

## X/Y/Z Verification Model

### What is being verified?
- **X (phases):** validity of moving from `A->B->C->D->E`.
- **Y (depth):** validity of integrating child results upward `LAYER(y+1)->LAYER(y)`.
- **Z (subagents):** validity and provenance of sidecar contributions used as inputs/evidence at a node.

### Z-Output Provenance Rule
Any Z-subagent output used in a gate decision must include:
- what it read/touched (scope)
- what method it used (critique, scan, evidence generation)
- what evidence artifacts it produced or referenced
- what limitations remain (unknowns, partial coverage)

If provenance is missing, the verifier treats the evidence as incomplete (Structural Partial/Fail).

---

## Three-Signal Model (Invariant)

### Structural
- Required artifacts exist
- Required fields exist
- Coverage accounted for (no silent omissions)
- Evidence provenance present (including Z provenance when used)

### Semantic
- Artifacts align with phase objective and prior invariants
- No drift from acceptance criteria
- No contradictions between artifacts (including contradictions introduced by Z critiques)

### Functional
- Evidence demonstrates correctness (adapter-defined)
- Integration is safe under declared boundaries and dependency invariants
- No critical failures are ignored

---

## Gate as Decision Function (Not a Checklist)

For a gate `G: X -> Y` (phase transition) or `VG: LAYER(y+1)->LAYER(y)` (vertical integration):

### Inputs
- Phase Packet / Integration Packet
- Evidence bundle:
  - integration validation evidence (adapter-defined)
  - end-to-end validation evidence (adapter-defined)
- Incident log (coupling/boundary/dependency)
- Policy state (frozen invariants)

### Output
- PASS -> credential token
- FAIL -> no token + minimal fixes + routing
- CONDITIONAL_PASS -> token only with explicit risk acceptance requirements

---

## Phase-Specific Lenses (A–E)

Each phase lens explicitly re-applies three signals to:
- principles/invariants
- requirements/constraints
- dependency/parallelization logic
- execution sequencing logic (as applicable)
- integration readiness (horizontal and vertical)

Even if a category is not “primary” in a phase, it is still checked for contradiction (semantic) and feasibility (functional).

---

### Lens A (Gate A->B): Requirements, Constraints, Boundary Lock

**Structural**
- Objective/boundary/constraints/acceptance criteria exist and are explicit.
- Assumptions/non-goals exist.
- If Z-context delegation used: provenance included.

**Semantic**
- Acceptance criteria match objective (no drift).
- Boundary does not contradict acceptance criteria.
- No hidden dependencies implied by acceptance criteria (e.g., “requires data X” but data X is forbidden/out-of-scope).

**Functional**
- Integration validation evidence: A artifacts are internally consistent.
- End-to-end evidence: criteria evaluability is proven (adapter-defined).

**Logical fallacy checks**
- self-referential completion
- contradictory scope vs acceptance

---

### Lens B (Gate B->C): Dependency, Impact, Parallelization Model

**Structural**
- Dependency model exists (reliance relationships explicit).
- Impact analysis exists.
- Candidate parallel zones exist with justification.
- Z-audits (if used) have provenance.

**Semantic**
- Dependency model respects Phase A boundary.
- Candidate parallel zones do not imply same-wave reliance.
- No reliance semantics mutation is introduced.

**Functional**
- Integration validation evidence: dependency model usable to derive wave plan.
- End-to-end evidence: dependency feasibility check passes (adapter-defined).

**Logical fallacy checks**
- circular reliance not detected
- “parallel zone” asserted without disjointness evidence

---

### Lens C (Gate C->D): Decomposition, Wave Plan, Integration Points, Verify-Plan

**Structural**
- Branch specs exist with boundary + evidence + integration contract.
- Wave plan exists with gates.
- Integration points declared with conditions.
- Recursion authorization declared.
- Verify-plan report exists.
- If Z critique used: contradictions captured and resolved or explicitly routed.

**Semantic**
- Decomposition covers objective without gaps/overlaps.
- Wave grouping consistent with dependencies.
- Integration points do not create coupling.
- Recursion is justified and bounded.

**Functional**
- Integration validation evidence: A+B+C coherence.
- End-to-end evidence: plan dry-run/simulation shows no contradiction.

**Logical fallacy checks (critical)**
- impossible wave ordering
- gates satisfied by their own outputs
- integration point violates no-same-wave-consumption

---

### Lens D (Gate D->E): Wave Execution, Sequencing, Bounded Integration

**Structural**
- Wave reports exist.
- Evidence bundles exist per branch.
- Incident log exists (explicitly empty or populated).
- Partial integration reports exist if partial integration was used.
- Z-generated evidence includes provenance.

**Semantic**
- Execution follows declared wave plan (no ad hoc concurrency).
- No same-wave evolving-output reliance.
- Boundaries respected.
- Integration conditions respected.

**Functional**
- Integration validation evidence: wave-level and scope-level integration checks pass.
- End-to-end evidence: readiness check passes (adapter-defined).

**Logical fallacy checks**
- redefining coupling incident as “acceptable” without reroute
- same-wave consumption of partial integration outputs

---

### Lens E (Closure Gate): Final Integration + End-to-End Acceptance Proof

**Structural**
- Final integration report exists.
- End-to-end report exists.
- Acceptance proof bundle maps directly to Phase A criteria.
- Residual risk ledger exists.

**Semantic**
- Proof aligns with Phase A acceptance (no criteria drift).
- Invariants preserved (dependency reliance, boundaries, anti-coupling).
- No critical failures are reframed.

**Functional**
- Integration validation evidence: integrated system behaves correctly at integration level.
- End-to-end evidence: acceptance criteria pass under representative conditions.

**Logical fallacy checks**
- “pass by narrative”
- closure with failing critical criteria

---

## Horizontal Integration Gate Requirement (X-axis)

At every transition `X -> X+1`, the verifier requires:
1) integration validation evidence at current scope
2) end-to-end validation evidence at current scope

If either is missing:
- FAIL, or
- CONDITIONAL_PASS only with explicit risk acceptance requirements.

---

## Vertical Integration Gate Requirement (Y-axis)

At every upward handoff `LAYER(y+1)->LAYER(y)`:
- Structural: deliverable + evidence bundle + provenance
- Semantic: matches the parent contract and boundary
- Functional: contract-level validations pass (adapter-defined)

Token format:
- `MLRE-VGATE-L{y+1}2L{y}-PASS`

---

## Z-axis Handling (Orthogonal sidecars)

### What Z-subagents may do
- context delegation (read/summarize)
- critique (adversarial checks)
- evidence generation (tool runs)
- utility tasks (bounded, non-recursive)

### What Z-subagents may not do
- authorize phase transitions
- change invariants without re-gating (their suggestions must be integrated by orchestrator and re-evaluated)
- create coupling across concurrently executing branches

### Z-output acceptance criteria (for gate use)
A Z report is admissible evidence only if:
- provenance is present,
- claims are tied to evidence artifacts or explicit reasoning limits,
- scope boundaries are respected.

---

## Failure Classification + Routing (Minimum rollback principle)

- `logic_fallacy` -> return to Phase C
- `hidden_dependency` -> return to Phase B or C
- `coupling_violation` -> return to Phase C
- `boundary_violation` -> redo affected work; may require Phase C tightening
- `contract_drift` -> return to Phase C (or A if acceptance drift)
- `verification_deficiency` -> redo with required evidence
- `integration_defect` -> redo D or E depending on where it manifests

Verifier must specify:
- minimal fix set
- routing target
- why earlier phases remain valid or not

---

## Verifier Output Contract (Gate Packet)

- Gate: X->Y (or vertical gate)
- Structural: Pass/Partial/Fail + basis
- Semantic: Pass/Partial/Fail + basis
- Functional: Pass/Partial/Fail + basis
- Verdict: PASS | FAIL | CONDITIONAL_PASS
- Credential token if PASS/CONDITIONAL_PASS
- Required Fixes (minimal delta)
- Routing (redo X or return upstream)

---