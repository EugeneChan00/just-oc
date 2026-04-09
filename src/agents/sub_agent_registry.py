"""
sub_agent_registry.py

Registry for tracking active sub-agents in the orchestration tree.
Provides state management for sub-agents without imposing limits.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RegistryStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


@dataclass
class SubAgentRecord:
    """Record of a sub-agent in the registry."""

    instance_id: str
    agent_type: str
    task_payload: Any
    status: RegistryStatus = RegistryStatus.PENDING
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    result: Any = None
    error: Optional[str] = None


class SubAgentRegistry:
    """
    Registry for tracking active sub-agents.

    This registry:
    - Tracks all active sub-agents in the orchestration tree
    - Records status, retry counts, and results
    - Does NOT impose any depth or fan-out limits
    - Does NOT implement timeouts or circuit breakers

    The registry is for observation and state management only.
    """

    def __init__(self):
        self._records: dict[str, SubAgentRecord] = {}
        self._children: dict[str, list[str]] = {}  # parent_id -> list of child_ids

    def register(
        self,
        instance_id: str,
        agent_type: str,
        task_payload: Any,
        parent_id: Optional[str] = None,
    ) -> SubAgentRecord:
        """
        Register a new sub-agent.

        Args:
            instance_id: Unique identifier for this sub-agent instance
            agent_type: Type of agent (e.g., 'backend_developer_worker')
            task_payload: Task being assigned
            parent_id: Optional parent sub-agent instance ID

        Returns:
            The created SubAgentRecord
        """
        record = SubAgentRecord(
            instance_id=instance_id, agent_type=agent_type, task_payload=task_payload
        )

        self._records[instance_id] = record

        if parent_id:
            if parent_id not in self._children:
                self._children[parent_id] = []
            self._children[parent_id].append(instance_id)

        return record

    def update_status(self, instance_id: str, status: RegistryStatus):
        """
        Update the status of a sub-agent.

        Args:
            instance_id: Sub-agent instance ID
            status: New status
        """
        if instance_id in self._records:
            self._records[instance_id].status = status
            self._records[instance_id].updated_at = datetime.now()

    def increment_retry(self, instance_id: str):
        """
        Increment the retry count for a sub-agent.

        Args:
            instance_id: Sub-agent instance ID
        """
        if instance_id in self._records:
            self._records[instance_id].retry_count += 1
            self._records[instance_id].updated_at = datetime.now()

    def set_result(self, instance_id: str, result: Any):
        """
        Set the result for a sub-agent.

        Args:
            instance_id: Sub-agent instance ID
            result: The result to set
        """
        if instance_id in self._records:
            self._records[instance_id].result = result
            self._records[instance_id].updated_at = datetime.now()

    def set_error(self, instance_id: str, error: str):
        """
        Set the error for a sub-agent.

        Args:
            instance_id: Sub-agent instance ID
            error: Error message
        """
        if instance_id in self._records:
            self._records[instance_id].error = error
            self._records[instance_id].updated_at = datetime.now()

    def get_record(self, instance_id: str) -> Optional[SubAgentRecord]:
        """
        Get the record for a sub-agent.

        Args:
            instance_id: Sub-agent instance ID

        Returns:
            SubAgentRecord if found, None otherwise
        """
        return self._records.get(instance_id)

    def get_all_records(self) -> dict[str, SubAgentRecord]:
        """
        Get all sub-agent records.

        Returns:
            Dictionary of all records keyed by instance_id
        """
        return self._records.copy()

    def get_children(self, parent_id: str) -> list[str]:
        """
        Get child sub-agent IDs for a parent.

        Args:
            parent_id: Parent sub-agent instance ID

        Returns:
            List of child instance IDs
        """
        return self._children.get(parent_id, []).copy()

    def get_active_count(self) -> int:
        """
        Get count of active (non-terminal) sub-agents.

        Returns:
            Number of active sub-agents
        """
        terminal_statuses = {RegistryStatus.COMPLETED, RegistryStatus.EXHAUSTED}
        return sum(
            1 for r in self._records.values() if r.status not in terminal_statuses
        )

    def get_total_count(self) -> int:
        """
        Get total count of registered sub-agents.

        Returns:
            Total number of registered sub-agents
        """
        return len(self._records)

    def get_failed_count(self) -> int:
        """
        Get count of failed sub-agents.

        Returns:
            Number of failed sub-agents
        """
        return sum(
            1 for r in self._records.values() if r.status == RegistryStatus.EXHAUSTED
        )

    def is_complete(self) -> bool:
        """
        Check if all sub-agents have reached terminal states.

        Returns:
            True if all sub-agents are COMPLETED or EXHAUSTED
        """
        terminal_statuses = {RegistryStatus.COMPLETED, RegistryStatus.EXHAUSTED}
        return all(r.status in terminal_statuses for r in self._records.values())
