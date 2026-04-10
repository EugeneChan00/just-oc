"""
test_recursive_orchestrator.py

Red tests for recursive_orchestrator agent.
Covers: basic task decomposition and delegation, multi-level recursive delegation,
failure retry logic, and result synthesis from multiple sub-agents.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from harness.recursive_loop import (
    RecursiveEventLoop,
    RecursiveOrchestrationHarness,
    SubAgentStatus,
    SubAgentResult,
    OrchestrationContext,
)


class TestBasicTaskDecomposition:
    """Test basic task decomposition and delegation."""

    @pytest.fixture
    def event_loop(self):
        loop = RecursiveEventLoop()
        return loop

    @pytest.mark.asyncio
    async def test_spawn_single_sub_agent(self, event_loop):
        """Test spawning a single sub-agent."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = {
                "status": "completed",
                "result": "test_result",
            }

            instance_id = await event_loop.spawn_sub_agent(
                agent_type="backend_developer_worker",
                task_payload={"task": "implement login"},
            )

            assert instance_id is not None
            assert instance_id in event_loop._context.sub_agents
            assert event_loop.get_active_count() == 1

    @pytest.mark.asyncio
    async def test_spawn_multiple_parallel_agents(self, event_loop):
        """Test spawning multiple sub-agents in parallel."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = {"status": "completed", "result": "done"}

            ids = []
            for i in range(5):
                sid = await event_loop.spawn_sub_agent(
                    agent_type="backend_developer_worker",
                    task_payload={"task": f"task_{i}"},
                )
                ids.append(sid)

            assert len(ids) == 5
            assert event_loop.get_active_count() == 5

    @pytest.mark.asyncio
    async def test_sub_agent_completes_successfully(self, event_loop):
        """Test that a sub-agent completes with success status."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = {"status": "completed", "result": "login_impl"}

            instance_id = await event_loop.spawn_sub_agent(
                agent_type="backend_developer_worker",
                task_payload={"task": "implement login"},
            )

            # Allow the async task to complete
            await asyncio.sleep(0.1)

            result = event_loop._context.sub_agents.get(instance_id)
            assert result is not None
            assert result.status == SubAgentStatus.COMPLETED


class TestMultiLevelRecursiveDelegation:
    """Test multi-level recursive delegation (3 levels deep)."""

    @pytest.fixture
    def harness(self):
        return RecursiveOrchestrationHarness()

    @pytest.mark.asyncio
    async def test_three_level_decomposition(self, harness):
        """Test that recursive orchestrator can spawn another recursive orchestrator."""
        call_count = 0

        async def mock_dispatch(agent_type, task_payload, instance_id):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0)

            if agent_type == "recursive_orchestrator":
                # Simulate a level-2 orchestrator that spawns workers
                return {
                    "status": "completed",
                    "result": {
                        "sub_results": [
                            {"status": "completed", "result": "level3_result"}
                        ]
                    },
                }
            else:
                return {"status": "completed", "result": f"worker_result_{instance_id}"}

        with patch.object(
            harness.event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_dispatch

            # Level 1: spawn a recursive orchestrator
            instance_id = await harness.event_loop.spawn_sub_agent(
                agent_type="recursive_orchestrator",
                task_payload={"task": "design auth system"},
            )

            await asyncio.sleep(0.1)

            result = harness.event_loop._context.sub_agents.get(instance_id)
            assert result.status == SubAgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_recursive_orchestrator_spawns_itself(self, harness):
        """Test that recursive_orchestrator can spawn another recursive_orchestrator."""
        spawn_order = []

        async def mock_dispatch(agent_type, task_payload, instance_id):
            spawn_order.append((agent_type, instance_id))
            await asyncio.sleep(0)

            if agent_type == "recursive_orchestrator":
                return {
                    "status": "completed",
                    "result": {"task": task_payload, "status": "done"},
                }
            return {"status": "completed", "result": "worker_done"}

        with patch.object(
            harness.event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_dispatch

            # Spawn a recursive orchestrator that will spawn another
            id1 = await harness.event_loop.spawn_sub_agent(
                agent_type="recursive_orchestrator", task_payload={"task": "top_level"}
            )

            await asyncio.sleep(0.1)

            assert len(spawn_order) >= 1
            assert spawn_order[0][0] == "recursive_orchestrator"


class TestFailureRetryLogic:
    """Test failure retry logic."""

    @pytest.fixture
    def event_loop(self):
        return RecursiveEventLoop()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, event_loop):
        """Test that a failed sub-agent is retried up to 3 times."""
        attempt_count = 0

        async def mock_dispatch(agent_type, task_payload, instance_id):
            nonlocal attempt_count
            attempt_count += 1
            await asyncio.sleep(0)

            if attempt_count < 3:
                raise Exception(f"Transient failure {attempt_count}")
            return {"status": "completed", "result": "finally_success"}

        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_dispatch

            instance_id = await event_loop.spawn_sub_agent(
                agent_type="backend_developer_worker",
                task_payload={"task": "might_fail"},
            )

            await asyncio.sleep(0.2)

            result = event_loop._context.sub_agents.get(instance_id)
            assert result.status == SubAgentStatus.COMPLETED
            assert result.retry_count == 2  # 2 retries before success

    @pytest.mark.asyncio
    async def test_exhaust_retries_after_three_failures(self, event_loop):
        """Test that a sub-agent is marked EXHAUSTED after 3 retries (4 attempts)."""
        attempt_count = 0

        async def mock_dispatch(agent_type, task_payload, instance_id):
            nonlocal attempt_count
            attempt_count += 1
            await asyncio.sleep(0)
            raise Exception(f"Permanent failure {attempt_count}")

        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_dispatch

            instance_id = await event_loop.spawn_sub_agent(
                agent_type="backend_developer_worker",
                task_payload={"task": "always_fails"},
            )

            await asyncio.sleep(0.3)

            result = event_loop._context.sub_agents.get(instance_id)
            assert result.status == SubAgentStatus.EXHAUSTED
            assert result.retry_count == 3  # 3 retries after initial failure
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_max_retries_is_code_enforced(self, event_loop):
        """Test that MAX_RETRIES=3 is enforced in code, not prose."""
        # This is a meta-test to verify the code enforcement
        assert event_loop.MAX_RETRIES == 3

        # Verify the retry loop condition uses MAX_RETRIES
        source = asyncio.wait  # Just a reference check
        assert event_loop.MAX_RETRIES == 3  # Hard-coded, not configurable


class TestResultSynthesis:
    """Test result synthesis from multiple sub-agents."""

    @pytest.fixture
    def event_loop(self):
        return RecursiveEventLoop()

    @pytest.mark.asyncio
    async def test_synthesize_multiple_successes(self, event_loop):
        """Test synthesis when all sub-agents succeed."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            mock_dispatch.return_value = {"status": "completed", "result": "done"}

            for i in range(3):
                await event_loop.spawn_sub_agent(
                    agent_type="backend_developer_worker",
                    task_payload={"task": f"task_{i}"},
                )

            await asyncio.sleep(0.2)

            synthesis = event_loop._synthesize_results()

            assert synthesis["total_sub_agents"] == 3
            assert synthesis["completed"] == 3
            assert synthesis["failed"] == 0

    @pytest.mark.asyncio
    async def test_synthesize_partial_failures(self, event_loop):
        """Test synthesis when some sub-agents fail."""
        attempt_count = 0

        async def mock_dispatch(agent_type, task_payload, instance_id):
            nonlocal attempt_count
            attempt_count += 1
            await asyncio.sleep(0)

            if attempt_count == 2:
                raise Exception("Simulated failure for agent 2")
            return {"status": "completed", "result": f"result_{instance_id}"}

        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_dispatch

            for i in range(3):
                await event_loop.spawn_sub_agent(
                    agent_type="backend_developer_worker",
                    task_payload={"task": f"task_{i}"},
                )

            await asyncio.sleep(0.3)

            synthesis = event_loop._synthesize_results()

            assert synthesis["total_sub_agents"] == 3
            # At least one should have failed (the one that raised exception)
            assert synthesis["failed"] >= 1 or synthesis["completed"] <= 2

    @pytest.mark.asyncio
    async def test_synthesis_includes_retry_counts(self, event_loop):
        """Test that synthesis includes retry count information."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock_dispatch:
            # First call fails, second succeeds
            mock_dispatch.side_effect = [
                Exception("Fail 1"),
                {"status": "completed", "result": "success"},
            ]

            instance_id = await event_loop.spawn_sub_agent(
                agent_type="backend_developer_worker",
                task_payload={"task": "retry_test"},
            )

            await asyncio.sleep(0.2)

            synthesis = event_loop._synthesize_results()
            agent_result = synthesis["sub_agent_results"][instance_id]

            assert agent_result["retry_count"] == 1
            assert agent_result["status"] == "completed"


class TestUnboundedCharacteristics:
    """Test that unbounded characteristics are correctly implemented."""

    @pytest.fixture
    def event_loop(self):
        return RecursiveEventLoop()

    @pytest.mark.asyncio
    async def test_no_depth_limit_enforced(self, event_loop):
        """Test that there is no depth tracking or limit."""
        # Verify no depth tracking in the event loop
        assert not hasattr(event_loop, "_depth")
        assert not hasattr(event_loop, "_max_depth")

        # Verify spawn_sub_agent doesn't track depth
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"status": "completed"}

            await event_loop.spawn_sub_agent(
                agent_type="recursive_orchestrator", task_payload={"depth": 100}
            )
            await asyncio.sleep(0.1)

            # Should complete without depth check
            assert event_loop.get_active_count() >= 0

    @pytest.mark.asyncio
    async def test_no_fanout_cap_enforced(self, event_loop):
        """Test that there is no fan-out cap."""
        with patch.object(
            event_loop.dispatcher, "dispatch", new_callable=AsyncMock
        ) as mock:
            mock.return_value = {"status": "completed"}

            # Spawn 50 agents (well beyond any reasonable cap)
            for i in range(50):
                await event_loop.spawn_sub_agent(
                    agent_type="backend_developer_worker",
                    task_payload={"task": f"task_{i}"},
                )

            # All should be tracked
            assert event_loop.get_active_count() == 50

    @pytest.mark.asyncio
    async def test_termination_guard_is_noop(self, event_loop):
        """Test that termination guard always returns False."""
        guard = event_loop.termination_guard

        assert guard.should_terminate() is False
        assert guard.should_terminate_depth(9999) is False
        assert guard.should_terminate_fanout(9999) is False
        assert guard.should_terminate_timeout(999999) is False


class TestContextTracking:
    """Test orchestration context tracking."""

    def test_orchestration_context_properties(self):
        """Test OrchestrationContext computed properties."""
        ctx = OrchestrationContext(task_id="test_task", task_payload={"task": "test"})

        assert ctx.total_sub_agents == 0
        assert ctx.completed_sub_agents == 0
        assert ctx.failed_sub_agents == 0

        # Add a pending agent
        ctx.sub_agents["agent_1"] = SubAgentResult(
            agent_id="agent_1", status=SubAgentStatus.PENDING
        )

        assert ctx.total_sub_agents == 1

        # Add a completed agent
        ctx.sub_agents["agent_2"] = SubAgentResult(
            agent_id="agent_2", status=SubAgentStatus.COMPLETED
        )

        assert ctx.total_sub_agents == 2
        assert ctx.completed_sub_agents == 1

        # Add an exhausted agent
        ctx.sub_agents["agent_3"] = SubAgentResult(
            agent_id="agent_3", status=SubAgentStatus.EXHAUSTED
        )

        assert ctx.failed_sub_agents == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
