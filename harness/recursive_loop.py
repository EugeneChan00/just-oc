"""
recursive_loop.py

Event loop harness for the recursive_orchestrator agent.
Implements unbounded recursive spawning with retry logic.

This harness implements the recursive_orchestrator's event loop:
- Spawns sub-agents via the task tool
- Tracks active sub-agents and their status
- Retries failed sub-agents up to 3 times
- Collects results and synthesizes on completion
- No depth limit, no fan-out cap, no global timeout, no circuit breaker
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from src.core.recursive_dispatcher import RecursiveDispatcher
from src.agents.sub_agent_registry import SubAgentRegistry, RegistryStatus
from src.core.termination_guard import TerminationGuard


class SubAgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXHAUSTED = "exhausted"  # Failed after max retries


@dataclass
class SubAgentResult:
    """Result from a sub-agent."""

    agent_id: str
    status: SubAgentStatus
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    completed_at: Optional[float] = None


@dataclass
class OrchestrationContext:
    """Context maintained across the orchestration lifecycle."""

    task_id: str
    task_payload: Any
    started_at: float = field(default_factory=time.time)
    sub_agents: dict[str, SubAgentResult] = field(default_factory=dict)
    synthesis: Any = None

    @property
    def total_sub_agents(self) -> int:
        return len(self.sub_agents)

    @property
    def completed_sub_agents(self) -> int:
        return sum(
            1
            for r in self.sub_agents.values()
            if r.status in (SubAgentStatus.COMPLETED, SubAgentStatus.EXHAUSTED)
        )

    @property
    def failed_sub_agents(self) -> int:
        return sum(
            1 for r in self.sub_agents.values() if r.status == SubAgentStatus.EXHAUSTED
        )


class RecursiveEventLoop:
    """
    Event loop for recursive orchestration.

    Key characteristics (per design mandate):
    - NO depth limit
    - NO fan-out cap
    - NO global timeout
    - NO circuit breaker or deadman's switch
    - 3 retries per failed sub-agent (code-enforced)
    """

    MAX_RETRIES: int = 3  # Code-enforced retry limit

    def __init__(
        self,
        dispatcher: Optional[RecursiveDispatcher] = None,
        registry: Optional[SubAgentRegistry] = None,
        termination_guard: Optional[TerminationGuard] = None,
    ):
        self.dispatcher = dispatcher or RecursiveDispatcher()
        self.registry = registry or SubAgentRegistry()
        # termination_guard is a no-op stub per design mandate
        self.termination_guard = termination_guard or TerminationGuard.noop()
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._context: Optional[OrchestrationContext] = None

    async def run(self, task_payload: Any) -> Any:
        """
        Run the orchestration loop.

        Args:
            task_payload: The task to orchestrate

        Returns:
            Synthesized result from all sub-agents
        """
        # Initialize context
        self._context = OrchestrationContext(
            task_id=f"orchestration_{time.time()}", task_payload=task_payload
        )

        # The orchestrator agent performs task decomposition
        # and calls spawn_sub_agent for each sub-task
        # This method waits for all sub-agents and synthesizes

        # Wait for all spawned sub-agents to complete
        await self._wait_for_completion()

        # Synthesize results
        synthesis = self._synthesize_results()

        return synthesis

    def _ensure_context(self) -> OrchestrationContext:
        """Ensure context is initialized. Lazily initializes if not yet set."""
        if self._context is None:
            self._context = OrchestrationContext(
                task_id=f"orchestration_{time.time()}", task_payload=None
            )
        return self._context

    async def spawn_sub_agent(
        self, agent_type: str, task_payload: Any, instance_id: Optional[str] = None
    ) -> str:
        """
        Spawn a sub-agent.

        Args:
            agent_type: Type of agent to spawn (e.g., 'backend_developer_worker', 'recursive_orchestrator')
            task_payload: Task to assign to the sub-agent
            instance_id: Optional unique identifier for this instance

        Returns:
            Agent instance ID
        """
        ctx = self._ensure_context()

        if instance_id is None:
            instance_id = f"{agent_type}_{time.time()}_{len(ctx.sub_agents)}"

        # Register the sub-agent
        ctx.sub_agents[instance_id] = SubAgentResult(
            agent_id=instance_id, status=SubAgentStatus.PENDING
        )

        # Register in the sub-agent registry
        self.registry.register(instance_id, agent_type, task_payload)

        # Create and track the asyncio task
        task = asyncio.create_task(
            self._run_sub_agent(instance_id, agent_type, task_payload)
        )
        self._active_tasks[instance_id] = task

        return instance_id

    async def _run_sub_agent(
        self, instance_id: str, agent_type: str, task_payload: Any
    ) -> SubAgentResult:
        """
        Run a single sub-agent with retry logic.

        Retry logic is CODE-ENFORCED - exactly 3 retries before marking as exhausted.
        """
        # Context must be initialized (spawn_sub_agent calls _ensure_context first)
        ctx = self._ensure_context()
        result = ctx.sub_agents[instance_id]
        result.status = SubAgentStatus.RUNNING

        retry_count = 0

        while retry_count < self.MAX_RETRIES:
            try:
                # Dispatch the sub-agent via the dispatcher
                agent_result = await self.dispatcher.dispatch(
                    agent_type=agent_type,
                    task_payload=task_payload,
                    instance_id=instance_id,
                )

                # Success
                result.status = SubAgentStatus.COMPLETED
                result.result = agent_result
                result.retry_count = retry_count
                result.completed_at = time.time()
                # Use RegistryStatus for registry operations (different enum type)
                self.registry.update_status(instance_id, RegistryStatus.COMPLETED)
                return result

            except Exception as e:
                retry_count += 1
                result.retry_count = retry_count

                if retry_count >= self.MAX_RETRIES:
                    # Exhausted retries - mark as failed
                    result.status = SubAgentStatus.EXHAUSTED
                    result.error = str(e)
                    result.completed_at = time.time()
                    # Use RegistryStatus for registry operations (different enum type)
                    self.registry.update_status(instance_id, RegistryStatus.EXHAUSTED)
                    return result

                # Retry - log and continue
                self.registry.increment_retry(instance_id)
                await asyncio.sleep(0)  # Yield control

        # Should not reach here, but safety fallback
        result.status = SubAgentStatus.EXHAUSTED
        return result

    async def _wait_for_completion(self):
        """
        Wait for all active sub-agents to complete.

        No timeout - waits until all sub-agents return.
        No circuit breaker - waits regardless of how long it takes.
        """
        while self._active_tasks:
            # Wait for any task to complete
            done, pending = await asyncio.wait(
                self._active_tasks.values(), return_when=asyncio.FIRST_COMPLETED
            )

            # Remove completed tasks from tracking
            for task in done:
                # Find which instance this task belongs to
                for instance_id, t in list(self._active_tasks.items()):
                    if t == task:
                        del self._active_tasks[instance_id]
                        break

            # Continue waiting for pending tasks
            # Note: We don't break early - we wait for ALL tasks

    def _synthesize_results(self) -> Any:
        """
        Synthesize results from all sub-agents.

        This is a prompt-enforced behavior - the actual synthesis logic
        lives in the orchestrator agent's system prompt. This method
        just collects and structures the results for the agent.
        """
        # Context must be initialized (run() or _ensure_context() must have been called)
        ctx = self._ensure_context()

        results = {
            "synthesis_timestamp": time.time(),
            "total_sub_agents": ctx.total_sub_agents,
            "completed": ctx.completed_sub_agents,
            "failed": ctx.failed_sub_agents,
            "sub_agent_results": {},
        }

        for instance_id, result in ctx.sub_agents.items():
            results["sub_agent_results"][instance_id] = {
                "status": result.status.value,
                "result": result.result,
                "error": result.error,
                "retry_count": result.retry_count,
                "completed_at": result.completed_at,
            }

        return results

    def get_active_count(self) -> int:
        """Return the number of active (non-completed) sub-agents."""
        return len(self._active_tasks)

    def get_context(self) -> OrchestrationContext:
        """Return the current orchestration context."""
        # Context may be None if never initialized - return a new empty context
        if self._context is None:
            self._context = OrchestrationContext(
                task_id=f"orchestration_{time.time()}", task_payload=None
            )
        return self._context


class RecursiveOrchestrationHarness:
    """
    Top-level harness for running recursive orchestration.

    This is the entry point for running a recursive_orchestrator agent.
    """

    def __init__(self):
        self.event_loop = RecursiveEventLoop()

    async def execute(self, task_payload: Any) -> Any:
        """
        Execute a task via recursive orchestration.

        Args:
            task_payload: The task to execute

        Returns:
            Synthesized result
        """
        return await self.event_loop.run(task_payload)

    def get_event_loop(self) -> RecursiveEventLoop:
        """Return the event loop instance."""
        return self.event_loop
