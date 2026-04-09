"""
termination_guard.py

Termination guard implementation.

PER DESIGN MANDATE: This is a NO-OP stub.
The lead's explicit position is that circuit breakers and deadman's switches
would corrupt partial results and create more problems than they solve.

This file exists for interface compliance and to make the design intent explicit.
In a production system, this would be replaced with actual monitoring/alerting
in a follow-up iteration.
"""


class TerminationGuard:
    """
    No-op termination guard.

    Per design mandate:
    - NO circuit breaker
    - NO deadman's switch
    - NO premature termination of deep agent trees

    The lead's position is that external monitoring and alerting (added in
    a follow-up iteration) will catch runaway trees before they cause
    production impact.
    """

    @staticmethod
    def noop() -> "TerminationGuard":
        """
        Create a no-op termination guard.

        Returns:
            A TerminationGuard instance that does nothing
        """
        return TerminationGuard()

    def should_terminate(self) -> bool:
        """
        Check if the orchestration should terminate.

        PER DESIGN MANDATE: Always returns False.
        No circuit breaker, no timeout, no resource-based termination.

        Returns:
            Always False
        """
        return False

    def should_terminate_depth(self, depth: int) -> bool:
        """
        Check if the orchestration should terminate based on depth.

        PER DESIGN MANDATE: Always returns False.
        No depth limit.

        Args:
            depth: Current depth in the agent tree

        Returns:
            Always False
        """
        return False

    def should_terminate_fanout(self, fanout: int) -> bool:
        """
        Check if the orchestration should terminate based on fan-out.

        PER DESIGN MANDATE: Always returns False.
        No fan-out cap.

        Args:
            fanout: Current number of parallel sub-agents

        Returns:
            Always False
        """
        return False

    def should_terminate_timeout(self, elapsed: float) -> bool:
        """
        Check if the orchestration should terminate based on timeout.

        PER DESIGN MANDATE: Always returns False.
        No global timeout.

        Args:
            elapsed: Elapsed time in seconds

        Returns:
            Always False
        """
        return False

    def record_subagent_spawn(self, instance_id: str, depth: int):
        """
        Record that a sub-agent was spawned.

        PER DESIGN MANDATE: No-op. No tracking.

        Args:
            instance_id: Sub-agent instance ID
            depth: Depth at which it was spawned
        """
        pass

    def record_subagent_complete(self, instance_id: str):
        """
        Record that a sub-agent completed.

        PER DESIGN MANDATE: No-op. No tracking.

        Args:
            instance_id: Sub-agent instance ID
        """
        pass

    def get_stats(self) -> dict:
        """
        Get termination guard statistics.

        PER DESIGN MANDATE: Returns empty stats.

        Returns:
            Empty dictionary
        """
        return {
            "has_circuit_breaker": False,
            "has_timeout": False,
            "has_depth_limit": False,
            "has_fanout_limit": False,
            "note": "No-op implementation per design mandate",
        }
