# Recursion-Bound Enforcement Module — Design Specification

**Document Type:** Security-Critical Enforcement Module Design  
**Author:** agentic_engineer_worker  
**Phase:** Design Specification (to be implemented by backend_developer_worker)  
**Classification:** SECURITY-CRITICAL — Adversarial Environment Expected  

---

## 1. RECURSION TRACKING MODEL

### 1.1 Depth Tracking Strategy

**Decision: Hybrid per-agent + session-level tracking with immutable lineage chain**

**Rationale:** Pure global tracking fails to isolate agents within concurrent sessions. Pure per-agent tracking fails to capture parent-child relationships when agents outlive their dispatch context. The lineage chain provides auditability and prevents identity spoofing.

**Tracking Mechanism:**

```
┌─────────────────────────────────────────────────────────────┐
│ LINEAGE CHAIN (immutable, cryptographically signed)         │
│                                                             │
│  Session(root) ──► Agent_A ──► Agent_B ──► Agent_C         │
│       │               │            │            │           │
│    session_id      agent_id     agent_id     agent_id      │
│    depth=0         depth=1     depth=2     depth=3        │
│    budget=N        consumed    consumed    consumed        │
└─────────────────────────────────────────────────────────────┘
```

**Depth Increment:** Depth increases by 1 when an agent spawns a sub-agent via the `task` tool. The increment happens atomically BEFORE the sub-agent is dispatched.

**Depth Decrement:** Depth decreases by 1 when a sub-agent completes (success, failure, or error). The decrement happens atomically AFTER the result is captured and logged.

**Key Invariant:** `current_depth = sum of all active agent depths in session`  
**Critical Invariant:** `parent.depth = child.depth - 1` always holds

### 1.2 Plane Allocation for Tracking

| Plane | Responsibility | Code/Prompt |
|-------|----------------|-------------|
| Control | Triggers dispatch, checks budget before sub-agent spawn | **Code-enforced** — atomic check-and-increment |
| Context | Stores lineage chain, budget state | **Code-enforced** — in-memory immutable log |
| Permission | Declares budget limits, validates signatures | **Code-enforced** — signature verification |
| Execution | Actually spawns sub-agent | **Code-enforced** — dispatch gate |
| Evaluation | Determines if violation occurred | **Code-enforced** — deterministic predicate |

**CRITICAL:** No part of budget enforcement is prompt-enforced. An LLM cannot be trusted to limit its own recursion.

---

## 2. BUDGET DECLARATION SYNTAX

### 2.1 Budget Declaration Location

Budget is declared **at dispatch time** via the `task` tool call, not in agent prompts. This prevents prompt injection from altering budget mid-execution.

### 2.2 Budget Declaration Schema

```python
@dataclass
class ChainingBudget:
    max_depth: int              # Maximum nesting depth allowed (not depth+1)
    max_fan_out: int            # Maximum direct children per agent
    session_budget: int          # Total sub-agents allowed in session
    timeout_per_agent: float     # Seconds before agent is considered hung
    parent_budget_id: str        # ID of parent's budget context
    lineage_signature: str       # HMAC-signed lineage chain
```

### 2.3 Budget Declaration Syntax at Dispatch

```python
# Dispatch call format (harness-level, not agent prompt)
task(
    agent="agent_name",
    prompt="...",
    chaining_budget=ChainingBudget(
        max_depth=3,
        max_fan_out=5,
        session_budget=50,
        timeout_per_agent=300.0,
        parent_budget_id="current_agent_budget_id",
        lineage_signature=compute_lineage_hmac(current_agent.lineage_chain)
    )
)
```

### 2.4 Budget Inheritance Rules

- **Inheritance:** Child agents inherit parent's remaining budget (not parent's full budget)
- **Non-escalation:** Child cannot have higher budget than parent
- **Non-transfer:** Unused parent budget does NOT transfer to children
- **Hard cap:** `child.max_depth = min(requested, parent.max_depth - 1)`

---

## 3. ENFORCEMENT MECHANISM

### 3.1 Enforcement Points

| Point | When | What | How |
|-------|------|------|-----|
| Pre-dispatch check | Before `task` call | Budget available? | **Code-enforced** — atomic predicate |
| At-increment | During `task` call | Lineage chain updated | **Code-enforced** — atomic update |
| At-completion | After agent returns | Depth decremented, cleanup | **Code-enforced** — guaranteed decrement |
| Orphan detection | Background monitor | Hung agents cleaned | **Code-enforced** — timeout monitor |
| Session limit | Per session aggregate | Total session budget | **Code-enforced** — counter |

### 3.2 Enforcement Flow

```
AGENT ATTEMPTS SUB-DISPATCH
         │
         ▼
┌─────────────────────────┐
│ 1. CHECK: depth < max_depth? │
└─────────────────────────┘
         │
    NO ◄─┼── YES
    │   │
    │   ▼
    │ ┌─────────────────────────┐
    │ │ 2. CHECK: fan_out <     │
    │ │    parent.max_fan_out?   │
    │ └─────────────────────────┘
    │         │
    │    NO ◄─┼── YES
    │    │    │
    │    │    ▼
    │    │ ┌─────────────────────────┐
    │    │ │ 3. CHECK: session count │
    │    │ │    < session_budget?    │
    │    │ └─────────────────────────┘
    │    │         │
    │    │    NO ◄─┼── YES
    │    │    │    │
    │    │    │    ▼
    │    │    │ ATOMIC: increment depth,
    │    │    │         append to lineage,
    │    │    │         increment session count
    │    │    │
    │    │    ▼
    │    │ SPAWN SUB-AGENT
    │    │
    ▼    ▼
REJECTED: BudgetExceeded error
         │
         ▼
   ┌─────────────┐
   │ LOG EVENT   │ ──► Audit trail
   └─────────────┘
```

### 3.3 Code-Enforcement Boundary

**All enforcement is code-enforced.** The enforcement module must be implemented as a Python module that wraps the `task` dispatch call. Agents MUST NOT have direct access to the `task` primitive — they must call it through the guard.

**Untrusted code path:** Agent prompt → Guard wrapper → task tool  
**Trusted code path:** Guard validates budget BEFORE calling task tool  

---

## 4. ERROR RESPONSE MODEL

### 4.1 Error Code Taxonomy

| Code | Name | HTTP Equivalent | Meaning |
|------|------|-----------------|---------|
| `RB_DEPTH_EXCEEDED` | DepthExceeded | 403 | `current_depth >= max_depth` |
| `RB_FAN_OUT_EXCEEDED` | FanOutExceeded | 403 | `direct_children >= max_fan_out` |
| `RB_SESSION_EXCEEDED` | SessionBudgetExceeded | 403 | `total_subagents >= session_budget` |
| `RB_ORPHAN_DETECTED` | OrphanAgent | 404 | Parent died leaving child alive |
| `RB_LINEAGE_TAMPERED` | LineageTamper | 403 | HMAC signature mismatch |
| `RB_TIMEOUT` | AgentTimeout | 408 | Agent exceeded timeout_per_agent |
| `RB_CIRCULAR_LOOP` | CircularLoop | 403 | Circular dispatch detected |

### 4.2 Error Response Format

```python
@dataclass
class RecursionGuardError:
    code: str                    # RB_* error code
    message: str                  # Human-readable explanation
    details: dict                # Debug info (depth, max, lineage snippet)
    agent_id: str                # Agent attempting dispatch
    timestamp: float              # Unix timestamp
    lineage_chain: list[str]      # Current lineage (truncated to 5 levels)
    recommended_action: str      # e.g., "retry with reduced depth"
    recoverable: bool            # Whether retry is sensible
```

### 4.3 Error Response to Agent

When an agent's sub-dispatch is rejected:

1. **Tool call FAILS** — the `task` tool returns the `RecursionGuardError` as an exception
2. **Agent sees:** `RecursionGuardError(code="RB_DEPTH_EXCEEDED", message="Budget exceeded at depth 3 of max_depth 3", recoverable=False)`
3. **Agent CANNOT catch/handle the error** — it is a hard failure at the harness level
4. **Agent CANNOT retry** — `recoverable=False` indicates retry will fail immediately

### 4.4 Recovery from Budget Exceeded

**NOT POSSIBLE within the same session.** Once `RB_DEPTH_EXCEEDED` or `RB_SESSION_EXCEEDED` is hit:
- Agent must complete its current task with remaining capabilities
- No sub-agents can be spawned
- Next dispatch must be at a shallower depth or with higher budget declared at session start

---

## 5. RESET CONDITIONS

### 5.1 Reset Triggers

| Trigger | When | Scope | Effect |
|---------|------|-------|--------|
| Task completion | Agent returns | Per-agent | Agent's budget context invalidated |
| Session end | Session timeout or explicit close | Session-wide | All budgets reset, lineage cleared |
| Hard limit | Session reaches max_subagents | Session-wide | Session terminated |
| Orphan cleanup | Parent dies | Orphan agent | Orphan marked, escalation triggered |
| Administrative reset | Operator command | Session-wide | Immediate reset with audit log |

### 5.2 Reset Behavior for In-Flight Sub-Agents

**When a parent is reset (completes or dies):**

1. **If parent completes normally:** All children continue until completion or their own timeout
2. **If parent dies (timeout, crash):** Children become orphans → enter orphan handling
3. **Orphan handling:** 
   - Orphan's budget context frozen (cannot spawn more)
   - Orphan marked with `RB_ORPHAN_DETECTED` on next dispatch attempt
   - Orphan terminates after current step completes
   - Audit event logged

### 5.3 Budget State Persistence

Budget state is **NOT persisted to disk** between sessions. Each session starts fresh. This prevents budget manipulation via state files.

---

## 6. EDGE CASES AND ATTACK SCENARIOS

### 6.1 Sub-Agent Outlives Parent

**Attack:** Agent A spawns Agent B, then A completes before B. B continues spawning.

**Defense:**
- Parent completion does NOT free child's budget — child inherits frozen context
- Orphan detection: if parent dies, child's next dispatch attempt fails with `RB_ORPHAN_DETECTED`
- Background monitor checks parent liveness and marks children as orphans

**Implementation:**
```python
def check_orphan(child_agent_id: str) -> bool:
    parent_id = lineage[child_agent_id].parent_id
    return not is_agent_alive(parent_id)  # Parent dead = orphan
```

### 6.2 Circular Dispatch Loops (A → B → A)

**Attack:** Agent A dispatches B, B dispatches A (same prompt or re-spawned), creating infinite loop.

**Defense:**
- Lineage chain is a directed acyclic graph (DAG) by construction
- Before spawn: check if `target_agent_id` already exists in lineage chain
- If yes: `RB_CIRCULAR_LOOP` error
- HMAC signature makes it impossible to spoof a different lineage

**Implementation:**
```python
def detect_circular_dispatch(new_agent_id: str, lineage: LineageChain) -> bool:
    return new_agent_id in lineage.agent_ids  # Already in chain = circular
```

### 6.3 Dynamically Generated Agent Names

**Attack:** Agent generates unique names like `agent_1709234567` to evade tracking.

**Defense:**
- Lineage tracks by **immutable internal ID**, not by agent name
- The internal ID is assigned at dispatch time by the guard, not chosen by the agent
- Agent name is cosmetic; internal ID is the binding
- Names can be arbitrary; lineage is based on dispatch order and parent references

**Implementation:**
```python
# Agent name is read-only metadata; lineage uses:
internal_id = uuid.uuid5(lineage_namespace, f"{parent_id}:{dispatch_order}")
```

### 6.4 Budget Inheritance Across Re-Dispatches

**Attack:** Agent claims to have remaining budget from a "prior session" to get higher limits.

**Defense:**
- Budget is session-scoped and cannot be transferred
- Re-dispatch of same agent creates NEW lineage entry
- Previous session's budget is already consumed or expired
- Lineage chain includes session_id; cross-session lineage is impossible

### 6.5 Race Conditions in Concurrent Sub-Dispatches

**Attack:** Two sub-agents dispatch children simultaneously, each seeing the other's dispatch as not-yet-happened, both proceeding.

**Defense:**
- All budget operations use atomic compare-and-swap (CAS) operations
- Python: `threading.Lock` for single-process; Redis `WATCH`/`MULTI` for cross-process
- Depth increment is ACID: `UPDATE budget SET depth = depth + 1 WHERE depth < max_depth AND version = expected_version`
- If CAS fails: operation is retried once, then rejected

### 6.6 HMAC Signature Bypass

**Attack:** Agent attempts to modify its lineage signature to claim higher privileges.

**Defense:**
- Lineage chain is signed with a secret key held ONLY by the guard module
- Agent never has access to the signing key
- Signature verification happens atomically inside the guard before any dispatch
- Tampering = `RB_LINEAGE_TAMPERED` error

---

## 7. AUDIT AND REPORTING

### 7.1 Required Audit Events

| Event | When | Contents |
|-------|------|----------|
| `BUDGET_DECLARED` | Session start | session_id, initial_depth, session_budget |
| `DISPATCH_ATTEMPT` | Sub-dispatch called | agent_id, target_depth, remaining_budget |
| `DISPATCH_APPROVED` | Budget check passes | lineage_chain (full), timestamp |
| `DISPATCH_REJECTED` | Budget check fails | agent_id, code, details, attempted_depth |
| `AGENT_COMPLETED` | Agent returns | agent_id, depth, actual_duration |
| `AGENT_TIMEOUT` | Timeout exceeded | agent_id, last_depth, waited_seconds |
| `ORPHAN_DETECTED` | Parent death discovered | orphan_id, parent_id, timestamp |
| `SESSION_RESET` | Session ends | session_id, total_agents, total_duration |

### 7.2 Audit Log Format

```python
@dataclass
class AuditEvent:
    event_type: str              # BUDGET_DECLARED, DISPATCH_ATTEMPT, etc.
    timestamp: float             # Unix timestamp (monotonic)
    session_id: str              # Session identifier
    agent_id: str                # Agent causing event (None for session events)
    depth: int                   # Depth at event time
    payload: dict                # Event-specific data
    signature: str               # HMAC of event for tamper detection
```

### 7.3 Operator Inspection Interface

**Metrics endpoint (harness-level):**
```python
def get_session_status(session_id: str) -> SessionStatus:
    """
    Returns current session status for monitoring.
    """
    current_depth: int           # Max depth reached in session
    total_agents: int            # Total agents spawned in session
    active_agents: int           # Currently running agents
    budget_remaining: dict      # Per-depth budget consumption
    lineage_snapshot: list        # Current lineage chains (truncated)
```

**Blocking report (on violation):**
```python
def get_violation_report(session_id: str) -> ViolationReport:
    """
    Returns detailed violation report for security review.
    """
    violations: list[RecursionGuardError]  # All violations in session
    attack_indicators: list[str]  # Suspicious patterns detected
    lineage_graph: dict          # Full lineage as directed graph
```

---

## 8. MODULE API SPECIFICATION

### 8.1 Core Classes

```python
class RecursionGuard:
    """
    Main enforcement module. Wraps task dispatch.
    ALL sub-agent spawns must go through this guard.
    """
    
    def __init__(self, secret_key: str, session_config: SessionConfig):
        """
        Initialize guard with session configuration.
        
        Args:
            secret_key: HMAC signing key (NEVER exposed to agents)
            session_config: Initial session budget settings
        """
    
    def dispatch(self, agent_id: str, prompt: str, budget: ChainingBudget) -> TaskResult:
        """
        Dispatches agent with budget enforcement.
        
        Returns:
            TaskResult on success
            
        Raises:
            RecursionGuardError on budget violation
        """
    
    def check_budget(self, agent_id: str, requested_budget: ChainingBudget) -> BudgetCheckResult:
        """
        Pre-flight check without dispatching.
        """
    
    def get_status(self, session_id: str) -> SessionStatus:
        """
        Operator status inspection.
        """
    
    def reset_session(self, session_id: str, reason: str) -> None:
        """
        Administrative session reset with audit.
        """


@dataclass
class ChainingBudget:
    """Budget declaration for an agent dispatch."""
    max_depth: int
    max_fan_out: int
    session_budget: int
    timeout_per_agent: float
    parent_budget_id: str
    lineage_signature: str


@dataclass
class RecursionGuardError:
    """Raised when budget enforcement rejects a dispatch."""
    code: str
    message: str
    details: dict
    agent_id: str
    timestamp: float
    lineage_chain: list[str]
    recommended_action: str
    recoverable: bool


@dataclass
class AuditEvent:
    """Single audit log entry."""
    event_type: str
    timestamp: float
    session_id: str
    agent_id: Optional[str]
    depth: int
    payload: dict
    signature: str
```

### 8.2 Integration Points

**With agent event loop:**
```python
# BEFORE: Direct task dispatch (UNSAFE)
result = task(agent="sub_agent", prompt="...")

# AFTER: Guard-wrapped dispatch (SAFE)
guard = RecursionGuard(secret_key=..., session_config=...)
try:
    result = guard.dispatch(agent_id="sub_agent", prompt="...", budget=my_budget)
except RecursionGuardError as e:
    # Handle violation
    log_audit(e)
    respond_to_user(f"Dispatch rejected: {e.code}")
```

**Integration requirements:**
1. `task` tool is NOT directly accessible to agents — only through guard
2. Guard is instantiated at session start by harness
3. Guard uses threading locks for atomic depth tracking
4. Guard emits audit events to a write-only audit log

---

## 9. PROMPT-VS-CODE CLASSIFICATION SUMMARY

| Behavior | Classification | Justification |
|----------|---------------|--------------|
| Budget limit enforcement | **Code-enforced** | Security-critical; LLMs will violate if prompt-only |
| Depth increment/decrement | **Code-enforced** | Atomic operation; prompt would race |
| Lineage chain management | **Code-enforced** | Tamper-evident; prompt would leak key |
| HMAC signature verification | **Code-enforced** | Cryptographic; no prompt substitute |
| Circular dispatch detection | **Code-enforced** | Deterministic predicate; no LLM input |
| Orphan detection | **Code-enforced** | Background monitor; no prompt |
| Audit logging | **Code-enforced** | Write-only; agents cannot suppress logs |
| Agent personality/preferences | Prompt-enforced | Non-critical; style guidance only |

**Total enforcement code-enforced:** 8/8 (100%)  
**Prompt-enforced component:** 0

---

## 10. ADVERSARIAL SELF-CHECK

**Scenarios attempted to break enforcement:**

1. **"I'll just spawn one more"** — Rejected at pre-flight check
2. **"My name is different"** — Lineage uses internal ID, not name
3. **"I'll wait for my parent to die"** — Orphan detection freezes child
4. **"I'll dispatch myself"** — Circular detection catches A→A
5. **"I'll guess the HMAC key"** — Key held only by guard, not in prompt
6. **"I'll spawn from two threads at once"** — CAS prevents race condition
7. **"I'll claim my parent's budget"** — Budget non-transferable; lineage signed
8. **"I'll rename to evade tracking"** — Internal ID immutable, name cosmetic

**Conclusion:** All attack vectors addressed by code-enforced invariants. No prose fallback. No prompt trust.

---

## 11. IMPLEMENTATION REQUIREMENTS

### 11.1 Security Requirements

1. HMAC secret key must be in memory only — never logged, never in prompt
2. Lineage chain must be append-only (no in-place modification)
3. Audit log must be write-only for agents — no read-back of full chain
4. Depth counter must be atomic — no read-modify-write race

### 11.2 Performance Requirements

1. Budget check must complete in < 1ms
2. Lineage chain traversal must be O(1) for depth lookup
3. Circular detection must be O(depth) worst case
4. Session must support 1000+ concurrent agents

### 11.3 Reliability Requirements

1. Hard limit reached → session immediately terminated
2. Timeout → agent forcibly terminated, depth decremented
3. Guard crash → session terminated, audit preserved
4. No state loss on crash (audit log flushed)

---

**END OF SPECIFICATION**