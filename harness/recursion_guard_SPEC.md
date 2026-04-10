# Recursion-Bound Enforcement Module — Design Specification

## Document Info

- **Status**: Authoritative design specification
- **Module**: `harness/recursion_guard.py`
- **Test file**: `tests/test_recursion_guard.py`
- **Security classification**: Security-critical

---

## 1. RECURSION TRACKING MODEL

### 1.1 Tracking Scope: Per-Chain State

Depth is tracked **per dispatch chain**, keyed by `(session_id, root_task_id)`. Each chain has an independent `RecursionTracker` instance. This provides:
- **Isolation**: A runaway chain cannot affect unrelated chains
- **Auditability**: Each user session or root task has a clean, inspectable state
- **Reset cleanliness**: Destroying a tracker (`reset_root`) leaves no residue

### 1.2 Depth Increment/Decrement Semantics

| Event | Action |
|-------|--------|
| Agent begins execution | `increment_depth(task_id, budget)` — increments depth counter for the task |
| Agent completes (any outcome) | `decrement_depth(task_id)` — decrements, clamped to 0 |
| Sub-agent registered as active | `register_subagent(parent_task_id, task_id)` — increments concurrent counter |
| Sub-agent completes | `unregister_subagent(parent_task_id, task_id)` — decrements concurrent counter, clamped to 0 |

**Depth is not inherited across sibling chains.** When agent A dispatches B and C in sequence, B completing does not affect C's depth — each is independently tracked via `task_id`.

### 1.3 What Happens at Each Nesting Level

- **Depth 0**: Root agent. No sub-agents allowed unless `max_depth >= 1` and `max_concurrent >= 1`.
- **Depth 1..max_depth-1**: Intermediate agents. Can dispatch up to `max_concurrent` simultaneous sub-agents.
- **At max_depth**: No further dispatches allowed. `check_dispatch` raises `RecursionLimitExceeded`.

---

## 2. BUDGET DECLARATION SYNTAX

### 2.1 Structure: `ChainingBudget` dataclass (immutable)

```python
@dataclass(frozen=True)
class ChainingBudget:
    max_depth: int                    # Max nesting depth (1 = no sub-agents)
    max_concurrent_subagents: int     # Max simultaneous active sub-agents
    budget_id: str                     # Immutable identifier for audit logging
    parent_budget_id: str | None       # Link to parent's budget for cycle detection
```

### 2.2 Declaration Sites

| Location | Syntax |
|----------|--------|
| **Dispatch time** (primary) | `ChainingBudget(...)` passed to `check_dispatch()`, `increment_depth()`, `register_subagent()` |
| **Factory (convenience)** | `RecursionGuard.make_default_budget(budget_id, parent_budget_id)` → `max_depth=1, max_concurrent=0` (default deny) |
| **Factory (child)** | `RecursionGuard.make_child_budget(parent_budget, budget_id, decrement=True)` → `max_depth = parent.max_depth - 1` |

### 2.3 Default Deny Policy

**Code-enforced constant**: `_DEFAULT_MAX_DEPTH = 1`, `_DEFAULT_MAX_CONCURRENT = 0`

Without an explicit budget, sub-agents are **forbidden by default**. This prevents silent unbounded chaining from misconfigured agents.

---

## 3. ENFORCEMENT MECHANISM

### 3.1 Enforcement Point: Synchronous Pre-Dispatch Gate

`RecursionGuard.check_dispatch(task_id, agent_name, parent_task_id, budget, session_id, root_task_id)` is the **sole enforcement point**. It is called **before** any sub-agent begins execution.

### 3.2 Enforcement Order (atomic under lock)

1. **Cycle detection** (via `budget_id` chain traversal) — checked FIRST to catch the most dangerous attack
2. **Depth limit check** — `requested_depth > budget.max_depth`
3. **Concurrent limit check** — `parent_active + 1 > budget.max_concurrent_subagents`

All three checks occur within a single `tracker._lock` acquisition, making the check atomic.

### 3.3 Violation Outcomes

| Violation | Exception | Code |
|-----------|-----------|------|
| Depth exceeded | `RecursionLimitExceeded` | `DEPTH_EXCEEDED` |
| Concurrent exceeded | `RecursionLimitExceeded` | `CONCURRENT_EXCEEDED` |
| Circular dispatch | `CircularDispatchError` | `CIRCULAR_DISPATCH_DETECTED` |

---

## 4. ERROR RESPONSE MODEL

### 4.1 Exception Hierarchy

```
RecursionLimitExceeded (base)
├── code: "RECURSION_LIMIT_EXCEEDED"
├── retryable: False (always)
├── Fields: budget_id, current_depth, requested_depth, max_depth, active_subagents, max_concurrent, agent_name, session_id, root_task_id
└── message: structured human+parser readable string

CircularDispatchError (extends RecursionLimitExceeded)
├── code: "CIRCULAR_DISPATCH_DETECTED"
├── cycle_budget_ids: list[str]  # The detected cycle segment
└── message: includes full budget chain for audit

ParentCancelled
├── code: "PARENT_CANCELLED"
├── retryable: False (always)
└── message: indicates budget was forcefully reset
```

### 4.2 Agent Recovery from Budget Exceeded

- **No retry.** `retryable = False` is enforced in code, not prose.
- The agent receives the structured exception with all context fields.
- The harness must not attempt to re-dispatch the same sub-agent.
- `ParentCancelled` signals to the sub-agent that its parent chain is gone — it should terminate.

### 4.3 Silent vs Loud Failure

- **Pre-dispatch rejection**: Loud — raises exception, audit logged with `DISPATCH_REJECTED`
- **Audit log**: All decisions (approved and rejected) are logged
- **No silent passes**: A dispatch that passes all checks still generates an audit entry

---

## 5. RESET CONDITIONS

### 5.1 Reset Triggers

| Reset Type | Scope | Use Case |
|------------|-------|----------|
| `reset_budget(budget_id, session_id, root_task_id)` | Budget + all descendants | Parent cancelled; cascading cleanup |
| `reset_root(session_id, root_task_id)` | Entire chain | Session end; task completion |
| Monitor orphan detection | Per-budget | Alert-only (80% utilization threshold) |

### 5.2 Reset Behavior

- **Depth counters** for affected task_ids are clamped to 0
- **Active subagent counters** are clamped to 0
- **Budget registry** entries are removed
- **Affected task_ids** are returned to caller for `ParentCancelled` delivery

### 5.3 In-Flight Sub-Agents During Reset

When `reset_budget(parent_budget_id)` is called:
1. All descendant budgets are found via BFS on `parent_budget_id` chain
2. All their task_ids are collected
3. Each task's depth is clamped to 0
4. Any subsequent `check_dispatch` from those tasks raises `ParentCancelled` or `RecursionLimitExceeded`
5. **Delivery of `ParentCancelled` to in-flight sub-agents is the caller's responsibility** — the guard raises the signal; the harness must propagate it

### 5.4 Budget Reset Between Runs

- `reset_root` cleans up the entire tracker — no residual state between runs
- Each test fixture uses unique `(session_id, root_task_id)` to avoid cross-test pollution

---

## 6. EDGE CASES AND ATTACK SCENARIOS

### 6.1 Sub-Agent That Outlives Its Parent

**Attack vector**: Parent completes and is cleaned up; child sub-agent is still running.

**Defense**: `ParentCancelled` exception. The parent calls `reset_budget`, which removes the child's budget from the registry. If the child later attempts a dispatch, `check_dispatch` will raise because its budget is no longer registered. The background monitor also alerts at 80% utilization to surface anomalies.

### 6.2 Circular Dispatch Loops (A→B→A, A→B→C→A)

**Attack vector**: Agent A dispatches B, which dispatches back to A.

**Defense**: Cycle detection via immutable `budget_id` chain traversal. The `parent_budget_id` of each budget forms an immutable linked list. `check_cycle()` traverses this chain and detects any cycle before the dispatch executes. This is checked **before** depth or concurrent limits.

**A→B→C→A detection**: When C tries to dispatch to A, C's budget has `parent_budget_id = B`. B's budget has `parent_budget_id = A`. Traversing from C: C → B → A → (A again) → cycle detected.

### 6.3 Dynamically Generated Agent Names to Evade Tracking

**Attack vector**: Attacker generates new agent names dynamically to avoid detection (e.g., "agent_1", "agent_2", or random UUIDs).

**Defense**: Depth tracking is by **`task_id`**, not by `agent_name`. The `task_id` is assigned by the harness at dispatch time and is independent of the agent's self-reported name. The guard only tracks `task_id → depth` and `parent_task_id → active_subagent_count` mappings. `agent_name` is used **only** for audit logging human readability.

### 6.4 Budget Inheritance Across Re-Dispatches

**Scenario**: Agent A dispatches B (depth 1). B completes. A dispatches C.

**Defense**: Depth is tracked per `task_id`. B completing does not affect A's depth — A's depth remains 0 (root level). When A dispatches C, the depth check uses A's current depth (0), not a historical value. The `task_id` space is flat; there is no "re-use" of task IDs.

### 6.5 Race Conditions in Concurrent Sub-Dispatches

**Attack vector**: Two threads dispatch simultaneously from the same parent, racing to exceed `max_concurrent`.

**Defense**: All mutations to tracker state (depth counters, active subagent counters, budget registration) are protected by `threading.RLock`. The check-and-increment for concurrent subagents is atomic within the lock. The concurrent test (`test_race_concurrent_dispatches`) verifies that with `max_concurrent=1`, launching two threads simultaneously results in exactly one success and one rejection — never two successes.

---

## 7. AUDIT AND REPORTING

### 7.1 Audit Event Types

| Event | When |
|-------|------|
| `DISPATCH_APPROVED` | `check_dispatch` passes all checks |
| `DISPATCH_REJECTED` | `check_dispatch` raises due to depth/concurrent/cycle |
| `AGENT_COMPLETED` | `decrement_depth` called |
| `BUDGET_RESET` | `reset_budget` or `reset_root` called |
| `CYCLE_DETECTED` | Cycle found in budget chain (same as REJECTED but for cycle) |
| `ALERT_BUDGET_ANOMALY` | Monitor detects 80%+ utilization on any budget |

### 7.2 Audit Log Structure: `BudgetAuditEntry`

Every entry contains: `timestamp`, `event`, `budget_id`, `parent_budget_id`, `task_id`, `agent_name`, `depth`, `active_subagents`, `max_depth`, `max_concurrent`, `session_id`, `root_task_id`, `rejection_code`.

### 7.3 Log Persistence

- **Location**: `harness/recursion_audit.jsonl`
- **Format**: JSON Lines (one JSON object per line)
- **Rotation**: 10MB max file size, then SHA-256 checksum written to `.sha256` sidecar, file truncated
- **Tamper-evidence**: SHA-256 checksum at log rotation provides integrity verification

### 7.4 Query API for Operators

| Method | Returns |
|--------|---------|
| `get_current_depth(task_id, session_id, root_task_id)` | Current depth for a task |
| `get_active_subagents(parent_task_id, session_id, root_task_id)` | Active subagent count for parent |
| `get_budget_state(budget_id, session_id, root_task_id)` | Current ChainingBudget state |
| `get_audit_trail(session_id, root_task_id)` | In-memory audit entries for chain |
| `get_live_dispatch_tree(root_task_id)` | All session trees for a root task |
| `get_all_live_dispatch_trees()` | All chains across all sessions |

---

## PLANE ALLOCATION SUMMARY

| Component | Plane |
|-----------|-------|
| `check_dispatch()` | **Control plane** — synchronous pre-dispatch gate |
| `increment_depth` / `decrement_depth` | **Execution plane** — task lifecycle tracking |
| `register_subagent` / `unregister_subagent` | **Execution plane** — fan-out tracking |
| `reset_budget` / `reset_root` | **Control plane** — termination and cleanup |
| `RecursionTracker` (per-chain state) | **Context/memory plane** — chain state |
| `BudgetAuditEntry` logging | **Evaluation/feedback plane** — audit trail |
| `monitor_loop` | **Monitor plane** — async anomaly detection |
| `CircularDispatchError` / `RecursionLimitExceeded` | **Permission/policy plane** — enforcement result |

---

## PROMPT-VS-CODE CLASSIFICATION SUMMARY

| Behavior | Classification | Justification |
|----------|---------------|---------------|
| Max depth limit enforcement | **Code-enforced** | Integer comparison is exact; prose cannot guarantee off-by-one |
| Max concurrent subagent limit | **Code-enforced** | Counter arithmetic is precise; prose cannot track across calls |
| Default deny (no budget = forbidden) | **Code-enforced** | Constant defaults ensure no silent chaining |
| Circular dispatch detection | **Code-enforced** | Immutable budget_id chain traversal; prose cannot detect |
| Orphan detection | **Code-enforced** | Background monitor requires code; prose self-reporting untrustworthy |
| Structured error response | **Code-enforced** | Machine-readable fields for audit parsing |
| Audit log integrity (SHA-256) | **Code-enforced** | Tamper-evidence requires cryptographic integrity |
| Budget declaration syntax | **Code-enforced** | Frozen dataclass enforces immutability of budget_id chain |

---

## INTEGRATION POINTS

The module integrates with the agent event loop at these points:

1. **Before sub-agent dispatch**: Call `check_dispatch()` — raises if violation
2. **When sub-agent starts execution**: Call `increment_depth()` + `register_subagent()`
3. **When sub-agent completes** (finally block): Call `decrement_depth()` + `unregister_subagent()`
4. **When parent cancels**: Call `reset_budget(parent_budget_id)` — raises `ParentCancelled` for descendants
5. **When session ends**: Call `reset_root(session_id, root_task_id)`

---

## SECURITY CRITICAL REQUIREMENTS

1. **Default deny is absolute**: No sub-agents allowed without explicit `ChainingBudget`
2. **Cycle detection is pre-depth**: Circular dispatches are caught before depth checking
3. **Errors are not retryable**: `retryable = False` is enforced in code
4. **All decisions are audited**: Both approvals and rejections
5. **Tamper-evident logs**: SHA-256 checksums at rotation boundaries
6. **Thread-safe by design**: All state mutations protected by `RLock`
7. **Budget chain is immutable**: `ChainingBudget` is `frozen=True`; `budget_id` cannot be changed post-creation