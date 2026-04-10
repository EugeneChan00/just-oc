"""
Tool wrappers for the agent harness.

This package contains tool wrappers that intercept and process
agent input and output streams. Each wrapper is a passive component
that does not modify the data stream — it only observes and logs.

NOTE: The InputLogger wrapper is registered here but is NOT exposed
to the agent as a visible tool. It operates at the harness level,
before input reaches the agent's processing pipeline.
"""

from __future__ import annotations

# Import all tool wrappers for harness-level registration
from harness.tools.bounded_editor import (
    BoundedEditor,
    Permissions,
    BoundedEditorError,
    BoundaryViolationError,
    PermissionDeniedError,
)

# Import InputLogger for passive input logging
# NOTE: This wrapper is INVISIBLE to the agent - it does not appear
# in the tool registry, system prompt, or any agent-visible interface.
from harness.tools.input_logger import InputLogger, InputMessage

# Tool registry for harness-level introspection
# This is NOT the agent's tool registry — it is for internal harness use only
_TOOL_WRAPPERS = {
    "input_logger": InputLogger,
    "bounded_editor": BoundedEditor,
}

# Agent-invisible wrappers (not exposed to agent)
# These are passive taps that operate at the harness level
_AGENT_INVISIBLE_WRAPPERS = {
    "input_logger": InputLogger,
}


def get_harness_wrappers() -> dict[str, type]:
    """
    Get all harness tool wrappers.

    Returns:
        Dictionary mapping wrapper names to wrapper classes.
        This is for harness-level introspection only.
    """
    return _TOOL_WRAPPERS.copy()


def get_agent_invisible_wrappers() -> dict[str, type]:
    """
    Get wrappers that are invisible to the agent.

    These wrappers operate at the harness level and are not
    visible to the agent through any interface.

    Returns:
        Dictionary mapping wrapper names to wrapper classes.
    """
    return _AGENT_INVISIBLE_WRAPPERS.copy()


def is_agent_visible(wrapper_name: str) -> bool:
    """
    Check if a wrapper is visible to the agent.

    Args:
        wrapper_name: Name of the wrapper.

    Returns:
        True if the wrapper is visible to the agent, False otherwise.
    """
    return wrapper_name not in _AGENT_INVISIBLE_WRAPPERS


__all__ = [
    # Tool wrappers
    "BoundedEditor",
    "InputLogger",
    "InputMessage",
    # Exceptions
    "BoundedEditorError",
    "BoundaryViolationError",
    "PermissionDeniedError",
    # Constants
    "Permissions",
    # Registry functions
    "get_harness_wrappers",
    "get_agent_invisible_wrappers",
    "is_agent_visible",
]
