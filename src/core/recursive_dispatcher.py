"""
recursive_dispatcher.py

Dispatcher for spawning sub-agents via the task tool.
Handles the mechanics of sub-agent lifecycle management.
"""

import asyncio
from typing import Any, Optional

from src.agents.sub_agent_registry import SubAgentRegistry


class RecursiveDispatcher:
    """
    Dispatches sub-agents via the task tool.

    This class handles the mechanics of spawning sub-agents:
    - Creates task tool calls
    - Manages sub-agent lifecycle
    - Returns results to the caller
    """

    def __init__(self, registry: Optional[SubAgentRegistry] = None):
        self.registry = registry or SubAgentRegistry()

    async def dispatch(
        self, agent_type: str, task_payload: Any, instance_id: str
    ) -> Any:
        """
        Dispatch a sub-agent via the task tool.

        Args:
            agent_type: Type of agent to spawn
            task_payload: Task to assign
            instance_id: Unique instance identifier

        Returns:
            The result from the sub-agent
        """
        # In a real implementation, this would use the task tool
        # For now, this is a placeholder that simulates sub-agent behavior

        # The actual task tool call would look like:
        # task(
        #     subagent=agent_type,
        #     prompt=task_payload,
        #     task_id=instance_id
        # )

        # Simulate async sub-agent execution
        # In reality, this would be an actual task tool call
        await asyncio.sleep(0)  # Yield control

        # Placeholder return - actual implementation would return
        # the sub-agent's result from the task tool call
        return {
            "instance_id": instance_id,
            "agent_type": agent_type,
            "status": "completed",
            "result": None,  # Actual result from sub-agent
        }

    async def dispatch_batch(self, dispatches: list[dict[str, Any]]) -> list[Any]:
        """
        Dispatch multiple sub-agents in parallel.

        Args:
            dispatches: List of dispatch specs, each containing
                       agent_type, task_payload, instance_id

        Returns:
            List of results from each sub-agent
        """
        tasks = [
            self.dispatch(
                agent_type=d["agent_type"],
                task_payload=d["task_payload"],
                instance_id=d["instance_id"],
            )
            for d in dispatches
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
