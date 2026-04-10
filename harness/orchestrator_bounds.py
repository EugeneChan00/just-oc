"""
orchestrator_bounds.py

Deterministic recursion bounds enforcement for orchestrator agent tree.

PLANE ALLOCATION:
- Control plane: spawn gating — all spawn requests pass through bounds check
  before reaching the execution plane. Bounds check is a hard gate: rejected
  requests do not reach the dispatcher.
- Execution plane: tree state tracking — actual tracking of parent-child
  relationships, depth, and fan-out counters maintained in this module.

PROMPT-VS-CODE CLASSIFICATION (per-constraint justification):

1. MAXIMUM DEPTH LIMIT (3 levels, 0-indexed: depths 0, 1, 2 valid) -> CODE-ENFORCED
   Justification: Depth comparison requires exact integer comparison (depth < max_depth).
   An LLM reasoning about "depth" in prose could miscount levels or apply the wrong
   index. Code enforcement guarantees the off-by-one boundary is exact and immutable.

2. FAN-OUT LIMIT AT DEPTH 0 (max 3 sub-agents) -> CODE-ENFORCED
   Justification: Fan-out tracking requires precise counter arithmetic (children spawned
   < max_children). A prose instruction like "don't spawn too many" leaves the threshold
   ambiguous. Code enforcement defines exactly 3 and checks via integer comparison.

3. FAN-OUT LIMIT AT DEPTH 1 (max 1 sub-sub-agent per sub-agent) -> CODE-ENFORCED
   Justification: Per-parent fan-out requires stateful counter tracking per node, not
   a global limit. Prose cannot track per-parent state across multiple spawn calls.
   Code enforcement maintains a counter per parent and rejects any parent exceeding limit.

4. FAN-OUT LIMIT AT DEPTH 2 (max 0 — no further spawns) -> CODE-ENFORCED
   Justification: A hard cap of 0 requires a deterministic equality check (children == 0).
   Prose like "cannot spawn anything more" leaves "anything" ambiguous to an LLM.
   Code enforcement is exact: any non-zero value is a rejection.

5. STRUCTURED REJECTION ON BOUNDS EXCEEDANCE -> CODE-ENFORCED
   Justification: A rejection response must carry machine-readable reason codes and field
   values for the harness to log and act upon. Prose rejection ("that's not allowed")
   cannot be parsed by the harness. Code enforcement returns a typed SpawnResult dataclass
   with structured fields.

6. GLOBAL STATE TRACKING ACROSS TREE -> CODE-ENFORCED
   Justification: The harness must track the entire tree, not just local context, because
   fan-out limits apply per-parent. If parent A spawns 1 child and parent B spawns 1 child,
   both are valid independently. Only code can maintain this per-parent state persistently
   across multiple spawn calls and different code paths. Prose-enforced tracking would
   require the LLM to maintain consistent state from memory, which it cannot do reliably.

7. OBSERVABLE TERMINATION QUERY -> CODE-ENFORCED
   Justification: The harness must be able to query "can any node still spawn?" to detect
   when the tree is fully expanded without re-entering the agent. This requires a pure
   state query function that returns a deterministic boolean. Prose-enforced termination
   would require the agent to self-report, which cannot be trusted. Code enforcement
   provides can_spawn() as a guaranteed-consistent query.

WRITE BOUNDARY: harness/orchestrator_bounds.py ONLY.
No modifications to any other file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import threading

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------

MAX_DEPTH: int = 3  # 0-indexed: depths 0, 1, 2 are valid; depth 3 is REJECTED

MAX_FAN_OUT_BY_DEPTH: dict[int, int] = {
    0: 3,  # Orchestrator (depth 0) can spawn up to 3 sub-agents
    1: 1,  # Each sub-agent (depth 1) can spawn up to 1 sub-sub-agent
    2: 0,  # Sub-sub-agents (depth 2) cannot spawn further agents
}

# Sentinel ID for the orchestrator root node
_ORCHESTRATOR_ROOT_ID: str = "__orchestrator_root__"


# ------------------------------------------------------------------------------
# Enums and Data Structures
# ------------------------------------------------------------------------------


class SpawnRejectionReasonCode(Enum):
    """Machine-readable reason codes for spawn rejections."""

    DEPTH_EXCEEDED = "depth_exceeded"
    FAN_OUT_EXCEEDED = "fan_out_exceeded"
    PARENT_NOT_FOUND = "parent_not_found"
    INVALID_DEPTH = "invalid_depth"


@dataclass(frozen=True)
class SpawnRequest:
    """A spawn request from a parent agent.

    Attributes
    ----------
    parent_id : str
        The instance_id of the parent agent requesting the spawn.
        Use __orchestrator_root__ for the orchestrator itself.
    depth : int
        The depth level of the parent making the request.
        0 = orchestrator, 1 = sub-agent, 2 = sub-sub-agent.
    """

    parent_id: str
    depth: int


@dataclass(frozen=True)
class SpawnResult:
    """Structured result from a spawn bounds check.

    Attributes
    ----------
    allowed : bool
        True if the spawn is allowed, False if rejected.
    reason_code : Optional[SpawnRejectionReasonCode]
        The reason for rejection, if rejected.
    message : str
        Human-readable message for logging and debugging.
    max_depth : int
        Echo back of MAX_DEPTH for audit trail.
    max_fan_out_by_depth : dict[int, int]
        Echo back of MAX_FAN_OUT_BY_DEPTH for audit trail.
    """

    allowed: bool
    reason_code: Optional[SpawnRejectionReasonCode] = None
    message: str = ""
    max_depth: int = MAX_DEPTH
    max_fan_out_by_depth: dict[int, int] = field(
        default_factory=lambda: MAX_FAN_OUT_BY_DEPTH.copy()
    )


@dataclass
class NodeState:
    """Mutable state for a single node in the tree.

    Tracks children spawned from this node for fan-out enforcement.
    Thread-safe via the lock on the parent OrchestratorBounds instance.
    """

    node_id: str
    depth: int
    children: list[str] = field(default_factory=list)

    @property
    def fan_out(self) -> int:
        """Return the number of children spawned from this node."""
        return len(self.children)

    @property
    def fan_out_limit(self) -> int:
        """Return the fan-out limit for this node's depth."""
        return MAX_FAN_OUT_BY_DEPTH.get(self.depth, 0)

    @property
    def can_spawn_more(self) -> bool:
        """Return True if this node can still spawn children."""
        return self.fan_out < self.fan_out_limit


# ------------------------------------------------------------------------------
# OrchestratorBounds — Main API
# ------------------------------------------------------------------------------


class OrchestratorBounds:
    """
    Deterministic recursion bounds enforcement for orchestrator tree.

    This class tracks the entire tree state and enforces:
    - Maximum depth: 3 levels (depths 0, 1, 2 valid; depth 3 rejected)
    - Maximum fan-out per depth level: [3, 1, 0]
    - Per-parent fan-out tracking (not global across a depth level)
    - Observable termination query via can_spawn_any()

    Thread safety: This class uses a threading.Lock to serialize access to
    shared state. Concurrent spawn attempts from multiple sub-agents at the
    same depth will be serialized. The harness MUST NOT call check_spawn()
    or record_spawn() concurrently from the same OrchestratorBounds instance
    without external serialization — this lock does not make the class
    fully thread-safe for all patterns, but it does prevent race conditions
    on the counter updates.

    If the harness uses async concurrency (asyncio), spawn calls must be
    serialized externally, or a asyncio.Lock must be used instead of
    threading.Lock. This module uses threading.Lock for simplicity;
    the harness is responsible for ensuring serialized access in async context.
    """

    def __init__(self) -> None:
        """Initialize the bounds tracker with the orchestrator root node at depth 0."""
        self._lock = threading.Lock()
        self._nodes: dict[str, NodeState] = {}
        # Initialize the orchestrator root node
        self._nodes[_ORCHESTRATOR_ROOT_ID] = NodeState(
            node_id=_ORCHESTRATOR_ROOT_ID,
            depth=0,
            children=[],
        )

    # --------------------------------------------------------------------------
    # Core API
    # --------------------------------------------------------------------------

    def check_spawn(self, request: SpawnRequest) -> SpawnResult:
        """
        Check if a spawn request is allowed under the current bounds.

        This method is idempotent — it does NOT modify state. It only
        returns whether a spawn WOULD be allowed. Call record_spawn()
        to actually record a successful spawn.

        Parameters
        ----------
        request : SpawnRequest
            The spawn request to validate.

        Returns
        -------
        SpawnResult
            allowed=True if the spawn is permitted.
            allowed=False with reason_code if the spawn exceeds bounds.
        """
        with self._lock:
            # --- Constraint 1: Depth limit ---
            # Off-by-one check: depth 3 is the first invalid level.
            # Valid depths are 0, 1, 2. Request depth is the PARENT's depth.
            # If parent is at depth 2, child would be at depth 3 (INVALID).
            if request.depth >= MAX_DEPTH:
                return SpawnResult(
                    allowed=False,
                    reason_code=SpawnRejectionReasonCode.DEPTH_EXCEEDED,
                    message=(
                        f"depth {request.depth} is at or beyond maximum allowed "
                        f"depth {MAX_DEPTH - 1}; child spawn would be at depth "
                        f"{request.depth + 1} which exceeds bounds"
                    ),
                )

            # --- Constraint 2 & 3: Fan-out limit per parent ---
            parent_state = self._nodes.get(request.parent_id)
            if parent_state is None:
                return SpawnResult(
                    allowed=False,
                    reason_code=SpawnRejectionReasonCode.PARENT_NOT_FOUND,
                    message=f"parent_id '{request.parent_id}' not found in tree state",
                )

            # Check per-parent fan-out limit
            fan_out_limit = parent_state.fan_out_limit
            if parent_state.fan_out >= fan_out_limit:
                return SpawnResult(
                    allowed=False,
                    reason_code=SpawnRejectionReasonCode.FAN_OUT_EXCEEDED,
                    message=(
                        f"parent '{request.parent_id}' at depth {request.depth} "
                        f"has already spawned {parent_state.fan_out} child(ren); "
                        f"fan-out limit for depth {request.depth} is {fan_out_limit}"
                    ),
                )

            # All checks passed
            return SpawnResult(
                allowed=True,
                message=(
                    f"spawn allowed: parent '{request.parent_id}' at depth "
                    f"{request.depth}, current fan-out {parent_state.fan_out}, "
                    f"limit {fan_out_limit}"
                ),
            )

    def record_spawn(self, request: SpawnRequest, child_id: str) -> SpawnResult:
        """
        Record a successful spawn, updating tree state.

        This method MODIFIES STATE. It MUST be called AFTER check_spawn()
        returns allowed=True and AFTER the actual spawn succeeds (or at
        least after the harness has dispatched it). If check_spawn() was
        not called first, this method will still succeed but the caller
        loses the protection of the bounds check.

        Parameters
        ----------
        request : SpawnRequest
            The spawn request that was validated and allowed.
        child_id : str
            The instance_id assigned to the newly spawned child agent.

        Returns
        -------
        SpawnResult
            The result of the recording (always success if called correctly).

        Raises
        ------
        RuntimeError
            If check_spawn() was not called and returned allowed=True
            before calling this method (defensive; prevents caller error).
        """
        with self._lock:
            # Re-verify under lock to catch concurrent race conditions
            # between check_spawn() and record_spawn() calls
            check_result = self._check_spawn_locked(request)
            if not check_result.allowed:
                # This should never happen if caller follows protocol
                raise RuntimeError(
                    f"record_spawn called without prior allowed check: "
                    f"{check_result.message}"
                )

            parent_state = self._nodes[request.parent_id]
            parent_state.children.append(child_id)

            child_depth = request.depth + 1
            self._nodes[child_id] = NodeState(
                node_id=child_id,
                depth=child_depth,
                children=[],
            )

            return SpawnResult(
                allowed=True,
                message=(
                    f"spawn recorded: child '{child_id}' added under parent "
                    f"'{request.parent_id}' at depth {child_depth}"
                ),
            )

    def can_spawn_any(self) -> bool:
        """
        Observable termination query: can any node in the current tree still spawn?

        Returns True if there exists at least one node in the tree that has not
        yet reached its fan-out limit AND is not at the maximum depth.

        This allows the harness to detect tree completeness without re-entering
        the agent. Returns False when the tree is fully expanded (all nodes at
        all valid depths have exhausted their fan-out).

        Returns
        -------
        bool
            True if at least one node can still spawn, False if tree is complete.
        """
        with self._lock:
            for node in self._nodes.values():
                # A node can spawn if:
                # 1. It is not at max depth (depth < MAX_DEPTH - 1 means it can spawn children)
                # 2. It has not exhausted its fan-out
                if node.depth < MAX_DEPTH - 1 and node.can_spawn_more:
                    return True
                # Special case for depth MAX_DEPTH - 1: can it spawn at all?
                # At depth MAX_DEPTH - 1 = 2, can_spawn_more is False because limit is 0.
                # So the above check correctly returns False for depth 2 nodes.
                if node.depth == MAX_DEPTH - 1 and node.can_spawn_more:
                    return True
            return False

    def get_node_state(self, node_id: str) -> Optional[NodeState]:
        """Return the NodeState for a given node_id, or None if not found."""
        with self._lock:
            return self._nodes.get(node_id)

    def get_tree_stats(self) -> dict:
        """
        Return current tree statistics for debugging and audit.

        Returns
        -------
        dict
            Dictionary with depth_counts, fan_out_by_depth, total_nodes.
        """
        with self._lock:
            depth_counts: dict[int, int] = {}
            fan_out_totals: dict[int, int] = {}
            for node in self._nodes.values():
                depth_counts[node.depth] = depth_counts.get(node.depth, 0) + 1
                fan_out_totals[node.depth] = (
                    fan_out_totals.get(node.depth, 0) + node.fan_out
                )
            return {
                "total_nodes": len(self._nodes),
                "depth_counts": depth_counts,
                "fan_out_totals_by_depth": fan_out_totals,
                "max_depth_reached": max(
                    (n.depth for n in self._nodes.values()), default=0
                ),
                "can_spawn_any": self._can_spawn_any_locked(),
            }

    # --------------------------------------------------------------------------
    # Internal helpers (must be called while holding _lock)
    # --------------------------------------------------------------------------

    def _check_spawn_locked(self, request: SpawnRequest) -> SpawnResult:
        """Locked version of check_spawn for internal use."""
        if request.depth >= MAX_DEPTH:
            return SpawnResult(
                allowed=False,
                reason_code=SpawnRejectionReasonCode.DEPTH_EXCEEDED,
                message=f"depth {request.depth} exceeds maximum {MAX_DEPTH - 1}",
            )
        parent_state = self._nodes.get(request.parent_id)
        if parent_state is None:
            return SpawnResult(
                allowed=False,
                reason_code=SpawnRejectionReasonCode.PARENT_NOT_FOUND,
                message=f"parent_id '{request.parent_id}' not found",
            )
        fan_out_limit = parent_state.fan_out_limit
        if parent_state.fan_out >= fan_out_limit:
            return SpawnResult(
                allowed=False,
                reason_code=SpawnRejectionReasonCode.FAN_OUT_EXCEEDED,
                message=(
                    f"parent at depth {request.depth} has {parent_state.fan_out} "
                    f"children, limit is {fan_out_limit}"
                ),
            )
        return SpawnResult(allowed=True)

    def _can_spawn_any_locked(self) -> bool:
        """Locked version of can_spawn_any for internal use."""
        for node in self._nodes.values():
            if node.can_spawn_more and node.depth < MAX_DEPTH - 1:
                return True
            if node.depth == MAX_DEPTH - 1 and node.can_spawn_more:
                return True
        return False


# ------------------------------------------------------------------------------
# Convenience helpers for harness integration
# ------------------------------------------------------------------------------


def make_spawn_request(parent_id: str, parent_depth: int) -> SpawnRequest:
    """Construct a SpawnRequest with the given parent_id and parent_depth."""
    return SpawnRequest(parent_id=parent_id, depth=parent_depth)


def check_and_record_spawn(
    bounds: OrchestratorBounds,
    parent_id: str,
    parent_depth: int,
    child_id: str,
) -> SpawnResult:
    """
    Convenience function: check bounds then record if allowed.

    This combines check_spawn() and record_spawn() in one atomic(ish) call
    (they are two separate operations under the lock, but this is the
    typical usage pattern).

    Parameters
    ----------
    bounds : OrchestratorBounds
        The bounds tracker instance.
    parent_id : str
        The parent's instance_id.
    parent_depth : int
        The parent's depth.
    child_id : str
        The child's assigned instance_id.

    Returns
    -------
    SpawnResult
        allowed=True and message if recorded.
        allowed=False with reason_code if rejected.
    """
    request = make_spawn_request(parent_id, parent_depth)
    check_result = bounds.check_spawn(request)
    if not check_result.allowed:
        return check_result
    return bounds.record_spawn(request, child_id)


# ------------------------------------------------------------------------------
# Usage Example (for harness integration reference)
# ------------------------------------------------------------------------------
"""
Typical harness integration pattern:

    bounds = OrchestratorBounds()

    # Orchestrator spawns sub-agents
    for i in range(3):
        result = check_and_record_spawn(
            bounds,
            parent_id=__orchestrator_root__,
            parent_depth=0,
            child_id=f"sub_agent_{i}",
        )
        if not result.allowed:
            # Log rejection, do not spawn
            print(f"SPAWN REJECTED: {result.message}")
        else:
            # Dispatch sub_agent_{i} via task tool
            pass

    # Sub-agent spawns its sub-sub-agent
    result = check_and_record_spawn(
        bounds,
        parent_id="sub_agent_0",
        parent_depth=1,
        child_id="sub_sub_agent_0",
    )

    # Sub-sub-agent CANNOT spawn (depth 2 -> limit 0)
    result = bounds.check_spawn(
        SpawnRequest(parent_id="sub_sub_agent_0", depth=2)
    )
    # result.allowed == False, reason_code == FAN_OUT_EXCEEDED

    # Termination check
    if not bounds.can_spawn_any():
        print("Tree fully expanded; no more spawns possible")
"""
