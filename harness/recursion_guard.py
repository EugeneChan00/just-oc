"""
harness/recursion_guard.py

Thread-safe, security-critical recursion-bound enforcement module.

This module is the authoritative enforcement point for all agent chaining budgets
in the system. Every sub-agent dispatch passes through this module before
execution begins.

PLANE ALLOCATION:
- Control plane: dispatch() — synchronous pre-dispatch gating
- Permission plane: budget check gate (depth, fan-out, session, HMAC)
- Context plane: lineage chain readable for audit
- Execution plane: actual dispatch to task tool
- Evaluation plane: deterministic predicate for violation detection

SECURITY INVARIANTS (code-enforced, not prompt-enforced):
1. HMAC secret key held only in guard — never logged, never exposed
2. Lineage chain append-only — no in-place modification
3. Atomic depth tracking via threading.Lock
4. Pre-flight checks BEFORE dispatch — never after
5. Audit log write-only for agents — agents cannot suppress logs
6. Circular dispatch detection — check if agent_id already in lineage chain

WRITE BOUNDARY: harness/recursion_guard.py ONLY.
No modifications to any other file.
"""

from __future__ import annotations

import hmac
import threading
import time
import uuid
from dataclasses import dataclass, field, is_dataclass, fields as dataclass_fields
from typing import Optional

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

_AUDIT_LOG_MAX_ENTRIES: int = 10000

# Error codes
RB_DEPTH_EXCEEDED: str = "RB_DEPTH_EXCEEDED"
RB_FAN_OUT_EXCEEDED: str = "RB_FAN_OUT_EXCEEDED"
RB_SESSION_EXCEEDED: str = "RB_SESSION_EXCEEDED"
RB_ORPHAN_DETECTED: str = "RB_ORPHAN_DETECTED"
RB_LINEAGE_TAMPERED: str = "RB_LINEAGE_TAMPERED"
RB_TIMEOUT: str = "RB_TIMEOUT"
RB_CIRCULAR_LOOP: str = "RB_CIRCULAR_LOOP"

# Audit event types
EV_BUDGET_DECLARED: str = "BUDGET_DECLARED"
EV_DISPATCH_ATTEMPT: str = "DISPATCH_ATTEMPT"
EV_DISPATCH_APPROVED: str = "DISPATCH_APPROVED"
EV_DISPATCH_REJECTED: str = "DISPATCH_REJECTED"
EV_AGENT_COMPLETED: str = "AGENT_COMPLETED"
EV_AGENT_TIMEOUT: str = "AGENT_TIMEOUT"
EV_ORPHAN_DETECTED: str = "ORPHAN_DETECTED"
EV_SESSION_RESET: str = "SESSION_RESET"


# ------------------------------------------------------------------------------
# Session Configuration
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionConfig:
    """Initial session budget settings.

    Attributes
    ----------
    session_id : str
        Unique identifier for this session.
    max_depth : int
        Maximum nesting depth allowed for the session root.
    max_fan_out : int
        Maximum direct children per agent in this session.
    session_budget : int
        Total sub-agents allowed in this session.
    timeout_per_agent : float
        Seconds before an agent is considered hung.
    """

    session_id: str
    max_depth: int = 10
    max_fan_out: int = 5
    session_budget: int = 100
    timeout_per_agent: float = 300.0


# ------------------------------------------------------------------------------
# Result Types
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskResult:
    """Result of a successful agent dispatch.

    Attributes
    ----------
    dispatch_id : str
        UUID of the dispatch.
    agent_id : str
        Agent that was dispatched.
    session_id : str
        Session identifier.
    depth : int
        Depth at which agent was dispatched.
    lineage_chain : list[str]
        Lineage chain at time of dispatch (truncated to 5 levels).
    """

    dispatch_id: str
    agent_id: str
    session_id: str
    depth: int
    lineage_chain: list[str]


@dataclass(frozen=True)
class BudgetCheckResult:
    """Result of a pre-flight budget check.

    Attributes
    ----------
    allowed : bool
        True if the dispatch would be allowed.
    code : Optional[str]
        Error code if not allowed.
    message : str
        Human-readable explanation.
    remaining_depth : int
        Remaining depth budget.
    remaining_fan_out : int
        Remaining fan-out at current parent.
    remaining_session : int
        Remaining session sub-agent budget.
    """

    allowed: bool
    code: Optional[str] = None
    message: str = ""
    remaining_depth: int = 0
    remaining_fan_out: int = 0
    remaining_session: int = 0


@dataclass
class SessionStatus:
    """Current session status for operator inspection.

    Attributes
    ----------
    session_id : str
        Session identifier.
    current_depth : int
        Maximum depth reached in session.
    total_agents : int
        Total agents spawned in session.
    active_agents : int
        Currently running agents.
    budget_remaining : dict
        Per-depth budget consumption.
    lineage_snapshot : list
        Current lineage chains (truncated).
    """

    session_id: str
    current_depth: int = 0
    total_agents: int = 0
    active_agents: int = 0
    budget_remaining: dict = field(default_factory=dict)
    lineage_snapshot: list = field(default_factory=list)


# ------------------------------------------------------------------------------
# Data Structures
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainingBudget:
    """Budget declaration for an agent dispatch.

    Attributes
    ----------
    max_depth : int
        Maximum nesting depth allowed.
    max_fan_out : int
        Maximum direct children per agent.
    session_budget : int
        Total sub-agents allowed in session.
    timeout_per_agent : float
        Seconds before agent is considered hung.
    parent_budget_id : str
        ID of parent's budget context.
    lineage_signature : str
        HMAC-signed lineage chain.
    """

    max_depth: int
    max_fan_out: int
    session_budget: int
    timeout_per_agent: float
    parent_budget_id: str
    lineage_signature: str


class RecursionGuardError(Exception):
    """Raised when budget enforcement rejects a dispatch.

    Attributes
    ----------
    code : str
        RB_* error code.
    message : str
        Human-readable explanation.
    details : dict
        Debug info (depth, max, lineage snippet).
    agent_id : str
        Agent attempting dispatch.
    timestamp : float
        Unix timestamp.
    lineage_chain : list[str]
        Current lineage (truncated to 5 levels).
    recommended_action : str
        e.g., "retry with reduced depth".
    recoverable : bool
        Whether retry is sensible.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: dict,
        agent_id: str,
        timestamp: float,
        lineage_chain: list[str],
        recommended_action: str,
        recoverable: bool,
    ):
        self.code = code
        self.message = message
        self.details = details
        self.agent_id = agent_id
        self.timestamp = timestamp
        self.lineage_chain = lineage_chain
        self.recommended_action = recommended_action
        self.recoverable = recoverable
        super().__init__(self.message)


@dataclass(frozen=True)
class AuditEvent:
    """Single audit log entry.

    Attributes
    ----------
    event_type : str
        BUDGET_DECLARED, DISPATCH_ATTEMPT, etc.
    timestamp : float
        Unix timestamp (monotonic).
    session_id : str
        Session identifier.
    agent_id : Optional[str]
        Agent causing event (None for session events).
    depth : int
        Depth at event time.
    payload : dict
        Event-specific data.
    signature : str
        HMAC of event for tamper detection.
    """

    event_type: str
    timestamp: float
    session_id: str
    agent_id: Optional[str]
    depth: int
    payload: dict[str, object]
    signature: str


# ------------------------------------------------------------------------------
# Internal Lineage Entry
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class LineageEntry:
    """Immutable lineage entry for a single agent in the chain.

    Attributes
    ----------
    dispatch_id : str
        UUID of this dispatch.
    agent_id : str
        Agent identifier.
    parent_dispatch_id : Optional[str]
        Parent's dispatch UUID, None for root.
    depth : int
        Depth level of this agent.
    created_at : float
        Unix timestamp when entry was created.
    """

    dispatch_id: str
    agent_id: str
    parent_dispatch_id: Optional[str]
    depth: int
    created_at: float


# ------------------------------------------------------------------------------
# RecursionGuard
# ------------------------------------------------------------------------------


class RecursionGuard:
    """
    Main enforcement module. Wraps task dispatch.

    ALL sub-agent spawns must go through this guard. The guard:
    1. Verifies HMAC signature on lineage chain before any dispatch
    2. Checks depth, fan-out, and session budget limits atomically
    3. Detects circular dispatch loops
    4. Emits audit events for every dispatch attempt (approved and rejected)
    5. Tracks orphan agents when parents die

    Thread safety: All state mutations are protected by threading.Lock.
    The guard is a singleton — use get_instance() to access.
    """

    _instance: Optional["RecursionGuard"] = None
    _init_lock = threading.RLock()

    def __init__(self, secret_key: str, session_config: SessionConfig):
        """
        Initialize guard with session configuration.

        Parameters
        ----------
        secret_key : str
            HMAC signing key (NEVER exposed to agents).
        session_config : SessionConfig
            Initial session budget settings.
        """
        self._secret_key: str = secret_key
        self._session_config: SessionConfig = session_config
        self._lock = threading.Lock()

        # Session state
        self._lineage: list[LineageEntry] = []  # ordered, append-only
        self._lineage_dict: dict[str, LineageEntry] = {}  # dispatch_id -> entry
        self._active_dispatches: dict[str, LineageEntry] = {}  # dispatch_id -> entry

        # Counters
        self._total_subagents: int = 0
        self._max_depth_reached: int = 0
        self._children_per_parent: dict[str, int] = {}  # parent_dispatch_id -> count

        # Per-agent timeout tracking
        self._agent_start_times: dict[str, float] = {}

        # Audit log
        self._audit_log: list[AuditEvent] = []

        # Orphan tracking
        self._orphaned_dispatches: set[str] = set()

    # --------------------------------------------------------------------------
    # Singleton Access
    # --------------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls, secret_key: str = "", session_config: Optional[SessionConfig] = None
    ) -> "RecursionGuard":
        """Return the singleton instance. Thread-safe."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    if session_config is None:
                        session_config = SessionConfig(session_id=str(uuid.uuid4()))
                    cls._instance = cls(
                        secret_key=secret_key, session_config=session_config
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance. For testing only."""
        with cls._init_lock:
            cls._instance = None

    # --------------------------------------------------------------------------
    # HMAC / Signature
    # --------------------------------------------------------------------------

    def _compute_lineage_hmac(self, lineage_chain: list[str]) -> str:
        """Compute HMAC-SHA256 of lineage chain."""
        chain_str = "|".join(lineage_chain)
        return hmac.new(
            self._secret_key.encode("utf-8"),
            chain_str.encode("utf-8"),
            digestmod="sha256",
        ).hexdigest()

    def _sign_event(self, event_data: dict) -> str:
        """Compute HMAC-SHA256 of event data."""
        import json

        data_str = json.dumps(event_data, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            self._secret_key.encode("utf-8"),
            data_str.encode("utf-8"),
            digestmod="sha256",
        ).hexdigest()

    def _truncate_lineage(self, lineage: list[LineageEntry]) -> list[str]:
        """Truncate lineage to 5 levels for error reporting."""
        return [entry.agent_id for entry in lineage[-5:]]

    def _get_agent_ids_in_lineage(self) -> set[str]:
        """Get set of all agent_ids currently in lineage."""
        return {entry.agent_id for entry in self._lineage}

    # --------------------------------------------------------------------------
    # Core Dispatch API
    # --------------------------------------------------------------------------

    def dispatch(
        self, agent_id: str, prompt: str, budget: ChainingBudget
    ) -> TaskResult:
        """
        Dispatches agent with budget enforcement.

        Parameters
        ----------
        agent_id : str
            Agent identifier for this dispatch.
        prompt : str
            Prompt to send to the agent.
        budget : ChainingBudget
            Declared chaining budget for this dispatch.

        Returns
        -------
        TaskResult
            On success, returns task result with dispatch details.

        Raises
        ------
        RecursionGuardError
            On budget violation or security check failure.
        """
        timestamp = time.time()
        session_id = self._session_config.session_id

        # Pre-flight: check budget without modifying state
        check_result = self.check_budget(agent_id, budget)
        if not check_result.allowed:
            # code is always non-None when allowed=False (enforced by check_budget)
            error_code: str = (
                check_result.code if check_result.code is not None else "RB_UNKNOWN"
            )
            self._emit_audit(
                EV_DISPATCH_REJECTED,
                timestamp,
                session_id,
                agent_id,
                self._max_depth_reached,
                {
                    "code": error_code,
                    "message": check_result.message,
                    "budget": budget,
                },
            )
            raise RecursionGuardError(
                code=error_code,
                message=check_result.message,
                details={
                    "depth": self._max_depth_reached,
                    "max_depth": budget.max_depth,
                    "budget": budget,
                },
                agent_id=agent_id,
                timestamp=timestamp,
                lineage_chain=self._truncate_lineage(self._lineage),
                recommended_action=self._get_recommended_action(error_code),
                recoverable=self._is_recoverable(error_code),
            )

        # All checks passed — atomically update state and dispatch
        with self._lock:
            dispatch_id = str(uuid.uuid4())
            parent_entry: Optional[LineageEntry] = None

            if (
                budget.parent_budget_id
                and budget.parent_budget_id in self._lineage_dict
            ):
                parent_entry = self._lineage_dict[budget.parent_budget_id]

            # Determine depth
            if parent_entry is None:
                depth = 0
            else:
                depth = parent_entry.depth + 1

            # Create lineage entry (immutable, append-only)
            entry = LineageEntry(
                dispatch_id=dispatch_id,
                agent_id=agent_id,
                parent_dispatch_id=parent_entry.dispatch_id if parent_entry else None,
                depth=depth,
                created_at=timestamp,
            )

            # Append to lineage (append-only list)
            self._lineage.append(entry)
            self._lineage_dict[dispatch_id] = entry
            self._active_dispatches[dispatch_id] = entry

            # Update counters
            self._total_subagents += 1
            self._max_depth_reached = max(self._max_depth_reached, depth)
            self._children_per_parent[dispatch_id] = 0

            # Increment parent's child count
            if parent_entry:
                current_count = self._children_per_parent.get(
                    parent_entry.dispatch_id, 0
                )
                self._children_per_parent[parent_entry.dispatch_id] = current_count + 1

            # Track agent start time for timeout
            self._agent_start_times[dispatch_id] = timestamp

            lineage_chain = self._truncate_lineage(self._lineage)

            # Emit audit event
            self._emit_audit(
                EV_DISPATCH_APPROVED,
                timestamp,
                session_id,
                agent_id,
                depth,
                {
                    "dispatch_id": dispatch_id,
                    "parent_dispatch_id": entry.parent_dispatch_id,
                    "lineage_chain": lineage_chain,
                    "budget": {
                        "max_depth": budget.max_depth,
                        "max_fan_out": budget.max_fan_out,
                        "session_budget": budget.session_budget,
                    },
                },
            )

            return TaskResult(
                dispatch_id=dispatch_id,
                agent_id=agent_id,
                session_id=session_id,
                depth=depth,
                lineage_chain=lineage_chain,
            )

    def check_budget(
        self, agent_id: str, requested_budget: ChainingBudget
    ) -> BudgetCheckResult:
        """
        Pre-flight check without dispatching.

        Parameters
        ----------
        agent_id : str
            Agent identifier to check.
        requested_budget : ChainingBudget
            Budget to validate against.

        Returns
        -------
        BudgetCheckResult
            Pre-flight check result.
        """
        with self._lock:
            # 1. Circular dispatch detection: is agent_id already in lineage?
            agent_ids_in_lineage = self._get_agent_ids_in_lineage()
            if agent_id in agent_ids_in_lineage:
                return BudgetCheckResult(
                    allowed=False,
                    code=RB_CIRCULAR_LOOP,
                    message=f"Agent '{agent_id}' already in lineage chain — circular dispatch detected.",
                    remaining_depth=0,
                    remaining_fan_out=0,
                    remaining_session=0,
                )

            # 2. HMAC signature verification
            # Build current lineage chain for signature verification
            current_chain = [entry.agent_id for entry in self._lineage]
            expected_sig = self._compute_lineage_hmac(current_chain)
            if expected_sig != requested_budget.lineage_signature:
                # Signature mismatch — could be tampering or invalid signature on root dispatch
                if current_chain:
                    # Non-empty chain: any mismatch is tampering
                    return BudgetCheckResult(
                        allowed=False,
                        code=RB_LINEAGE_TAMPERED,
                        message="Lineage HMAC signature mismatch — chain may have been tampered.",
                        remaining_depth=0,
                        remaining_fan_out=0,
                        remaining_session=0,
                    )
                else:
                    # Root dispatch with empty chain: verify signature matches empty chain
                    empty_sig = self._compute_lineage_hmac([])
                    if requested_budget.lineage_signature != empty_sig:
                        return BudgetCheckResult(
                            allowed=False,
                            code=RB_LINEAGE_TAMPERED,
                            message="Lineage HMAC signature mismatch on root dispatch.",
                            remaining_depth=0,
                            remaining_fan_out=0,
                            remaining_session=0,
                        )

            # 3. Depth check
            parent_entry: Optional[LineageEntry] = None
            if (
                requested_budget.parent_budget_id
                and requested_budget.parent_budget_id in self._lineage_dict
            ):
                parent_entry = self._lineage_dict[requested_budget.parent_budget_id]

            current_depth = parent_entry.depth + 1 if parent_entry else 0

            if current_depth >= requested_budget.max_depth:
                return BudgetCheckResult(
                    allowed=False,
                    code=RB_DEPTH_EXCEEDED,
                    message=f"Depth {current_depth} >= max_depth {requested_budget.max_depth}.",
                    remaining_depth=max(0, requested_budget.max_depth - current_depth),
                    remaining_fan_out=self._get_remaining_fan_out(
                        parent_entry, requested_budget
                    ),
                    remaining_session=max(
                        0, requested_budget.session_budget - self._total_subagents
                    ),
                )

            # 4. Fan-out check
            remaining_fan_out = self._get_remaining_fan_out(
                parent_entry, requested_budget
            )
            if remaining_fan_out <= 0:
                return BudgetCheckResult(
                    allowed=False,
                    code=RB_FAN_OUT_EXCEEDED,
                    message=f"Parent has no remaining fan-out capacity.",
                    remaining_depth=max(0, requested_budget.max_depth - current_depth),
                    remaining_fan_out=0,
                    remaining_session=max(
                        0, requested_budget.session_budget - self._total_subagents
                    ),
                )

            # 5. Session budget check
            if self._total_subagents >= requested_budget.session_budget:
                return BudgetCheckResult(
                    allowed=False,
                    code=RB_SESSION_EXCEEDED,
                    message=f"Session budget exhausted: {self._total_subagents} >= {requested_budget.session_budget}.",
                    remaining_depth=max(0, requested_budget.max_depth - current_depth),
                    remaining_fan_out=remaining_fan_out,
                    remaining_session=0,
                )

            # 6. Orphan detection — check if parent's dispatch_id is orphaned
            if requested_budget.parent_budget_id:
                if requested_budget.parent_budget_id in self._orphaned_dispatches:
                    return BudgetCheckResult(
                        allowed=False,
                        code=RB_ORPHAN_DETECTED,
                        message=f"Parent dispatch '{requested_budget.parent_budget_id}' is orphaned — parent died before child.",
                        remaining_depth=0,
                        remaining_fan_out=0,
                        remaining_session=0,
                    )

            # All checks passed
            return BudgetCheckResult(
                allowed=True,
                message="Budget check passed.",
                remaining_depth=max(0, requested_budget.max_depth - current_depth),
                remaining_fan_out=remaining_fan_out,
                remaining_session=max(
                    0, requested_budget.session_budget - self._total_subagents
                ),
            )

    def get_status(self, session_id: str) -> SessionStatus:
        """
        Operator status inspection.

        Parameters
        ----------
        session_id : str
            Session identifier to query.

        Returns
        -------
        SessionStatus
            Current session status.
        """
        with self._lock:
            # Build per-depth budget remaining
            budget_remaining = {}
            for depth_val in range(self._session_config.max_depth + 1):
                # Count active agents at this depth
                active_at_depth = sum(
                    1
                    for entry in self._active_dispatches.values()
                    if entry.depth == depth_val
                )
                budget_remaining[depth_val] = {
                    "active": active_at_depth,
                    "max": self._session_config.max_depth,
                }

            # Lineage snapshot (truncated)
            lineage_snapshot = [
                {
                    "dispatch_id": entry.dispatch_id,
                    "agent_id": entry.agent_id,
                    "depth": entry.depth,
                    "parent_dispatch_id": entry.parent_dispatch_id,
                }
                for entry in self._lineage[-10:]
            ]

            return SessionStatus(
                session_id=session_id,
                current_depth=self._max_depth_reached,
                total_agents=self._total_subagents,
                active_agents=len(self._active_dispatches),
                budget_remaining=budget_remaining,
                lineage_snapshot=lineage_snapshot,
            )

    def reset_session(self, session_id: str, reason: str) -> None:
        """
        Administrative session reset with audit.

        Parameters
        ----------
        session_id : str
            Session to reset.
        reason : str
            Reason for reset.
        """
        with self._lock:
            # Emit reset audit event for each active dispatch
            for entry in list(self._active_dispatches.values()):
                self._emit_audit(
                    EV_SESSION_RESET,
                    time.time(),
                    session_id,
                    entry.agent_id,
                    entry.depth,
                    {
                        "reason": reason,
                        "dispatch_id": entry.dispatch_id,
                    },
                )

            # Mark all active dispatches as orphaned
            for dispatch_id in self._active_dispatches:
                self._orphaned_dispatches.add(dispatch_id)

            # Clear state
            self._lineage.clear()
            self._lineage_dict.clear()
            self._active_dispatches.clear()
            self._total_subagents = 0
            self._max_depth_reached = 0
            self._children_per_parent.clear()
            self._agent_start_times.clear()

            # Emit session-level reset event
            self._emit_audit(
                EV_SESSION_RESET,
                time.time(),
                session_id,
                None,  # session-level event
                0,
                {"reason": reason},
            )

    # --------------------------------------------------------------------------
    # Agent Lifecycle
    # --------------------------------------------------------------------------

    def complete_dispatch(self, dispatch_id: str) -> None:
        """
        Mark a dispatch as complete, cleaning up state.

        Parameters
        ----------
        dispatch_id : str
            The dispatch_id to complete.
        """
        with self._lock:
            entry = self._active_dispatches.get(dispatch_id)
            if entry is None:
                return  # Already completed

            # Remove from active dispatches
            del self._active_dispatches[dispatch_id]

            # Remove start time tracking
            self._agent_start_times.pop(dispatch_id, None)

            # Emit completion audit
            self._emit_audit(
                EV_AGENT_COMPLETED,
                time.time(),
                self._session_config.session_id,
                entry.agent_id,
                entry.depth,
                {
                    "dispatch_id": dispatch_id,
                    "duration": time.time() - entry.created_at,
                },
            )

    def mark_timed_out(self, dispatch_id: str) -> RecursionGuardError:
        """
        Mark an agent as timed out.

        Parameters
        ----------
        dispatch_id : str
            The dispatch_id that timed out.

        Returns
        -------
        RecursionGuardError
            The timeout error.
        """
        with self._lock:
            entry = self._active_dispatches.get(dispatch_id)
            if entry is None:
                raise ValueError(f"Dispatch {dispatch_id} not found")

            self._emit_audit(
                EV_AGENT_TIMEOUT,
                time.time(),
                self._session_config.session_id,
                entry.agent_id,
                entry.depth,
                {"dispatch_id": dispatch_id},
            )

            return RecursionGuardError(
                code=RB_TIMEOUT,
                message=f"Agent '{entry.agent_id}' exceeded timeout of {self._session_config.timeout_per_agent}s.",
                details={
                    "dispatch_id": dispatch_id,
                    "timeout": self._session_config.timeout_per_agent,
                },
                agent_id=entry.agent_id,
                timestamp=time.time(),
                lineage_chain=self._truncate_lineage(self._lineage),
                recommended_action="Retry with fresh agent or increase timeout.",
                recoverable=True,
            )

    def mark_orphan(self, dispatch_id: str) -> None:
        """
        Mark a dispatch as orphaned when its parent dies.

        Parameters
        ----------
        dispatch_id : str
            The dispatch_id to mark as orphan.
        """
        with self._lock:
            if dispatch_id not in self._orphaned_dispatches:
                self._orphaned_dispatches.add(dispatch_id)
                entry = self._lineage_dict.get(dispatch_id)
                if entry:
                    self._emit_audit(
                        EV_ORPHAN_DETECTED,
                        time.time(),
                        self._session_config.session_id,
                        entry.agent_id,
                        entry.depth,
                        {"dispatch_id": dispatch_id},
                    )

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _get_remaining_fan_out(
        self, parent_entry: Optional[LineageEntry], budget: ChainingBudget
    ) -> int:
        """Calculate remaining fan-out for parent."""
        if parent_entry is None:
            # Root dispatch — use session max_fan_out
            return self._session_config.max_fan_out

        current_children = self._children_per_parent.get(parent_entry.dispatch_id, 0)
        return max(0, budget.max_fan_out - current_children)

    def _is_recoverable(self, code: str) -> bool:
        """Determine if an error is recoverable."""
        recoverable_codes = {RB_TIMEOUT, RB_FAN_OUT_EXCEEDED}
        return code in recoverable_codes

    def _get_recommended_action(self, code: str) -> str:
        """Get recommended action for error code."""
        actions = {
            RB_DEPTH_EXCEEDED: "Complete current task without spawning more sub-agents.",
            RB_FAN_OUT_EXCEEDED: "Wait for child agents to complete before spawning more.",
            RB_SESSION_EXCEEDED: "Start a new session for additional agents.",
            RB_ORPHAN_DETECTED: "Restart from a higher-level agent.",
            RB_LINEAGE_TAMPERED: "Request a fresh lineage signature from parent.",
            RB_TIMEOUT: "Retry with increased timeout or simpler task.",
            RB_CIRCULAR_LOOP: "Use a different agent identifier.",
        }
        return actions.get(code, "Unknown error — consult administrator.")

    def _make_serializable(self, obj):
        """Recursively convert dataclasses to dicts for JSON serialization."""
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        elif is_dataclass(obj) and not isinstance(obj, type):
            return {
                f.name: self._make_serializable(getattr(obj, f.name))
                for f in dataclass_fields(obj)
            }
        else:
            return obj

    def _emit_audit(
        self,
        event_type: str,
        timestamp: float,
        session_id: str,
        agent_id: Optional[str],
        depth: int,
        payload: dict,
    ) -> None:
        """Emit an audit event with HMAC signature."""
        # Convert dataclasses in payload to dicts for JSON serialization
        serializable_payload = self._make_serializable(payload)
        event_data = {
            "event_type": event_type,
            "timestamp": timestamp,
            "session_id": session_id,
            "agent_id": agent_id,
            "depth": depth,
            "payload": serializable_payload,
        }
        signature = self._sign_event(event_data)

        event = AuditEvent(
            event_type=event_type,
            timestamp=timestamp,
            session_id=session_id,
            agent_id=agent_id,
            depth=depth,
            payload=serializable_payload,  # type: ignore[literal-required]
            signature=signature,
        )

        self._audit_log.append(event)

        # FIFO eviction
        if len(self._audit_log) > _AUDIT_LOG_MAX_ENTRIES:
            self._audit_log = self._audit_log[-_AUDIT_LOG_MAX_ENTRIES:]

    def get_audit_log(self, limit: int = 100) -> list[AuditEvent]:
        """
        Return last N audit log entries.

        Parameters
        ----------
        limit : int
            Maximum number of entries to return.

        Returns
        -------
        list[AuditEvent]
            Last N audit entries.
        """
        with self._lock:
            return list(self._audit_log[-limit:])

    # --------------------------------------------------------------------------
    # Representation
    # --------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"RecursionGuard(session={self._session_config.session_id}, "
            f"total_agents={self._total_subagents}, "
            f"active={len(self._active_dispatches)}, "
            f"max_depth={self._max_depth_reached})"
        )


# ------------------------------------------------------------------------------
# Module-level convenience
# ------------------------------------------------------------------------------


def get_recursion_guard(
    secret_key: str = "", session_config: Optional[SessionConfig] = None
) -> RecursionGuard:
    """Return the RecursionGuard singleton instance.

    Parameters
    ----------
    secret_key : str
        HMAC signing key. Only used on first call.
    session_config : SessionConfig
        Session config. Only used on first call.

    Returns
    -------
    RecursionGuard
        The singleton instance.
    """
    return RecursionGuard.get_instance(
        secret_key=secret_key, session_config=session_config
    )
