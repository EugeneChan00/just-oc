"""
autoresearch.loop.config

CLI argument parsing for the eval harness.
"""

import argparse
from typing import Optional

EXIT_COMPLETED = 0
EXIT_AGENT_NOT_FOUND = 1
EXIT_OPENCODE_NOT_FOUND = 3


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="autoresearch",
        description="AutoResearch Eval Harness — run evals and optimize agent prompts",
    )
    p.add_argument("--agent", type=str, required=True,
                   help="Agent name (e.g., 'ceo', 'backend_developer_worker') or 'all'")
    p.add_argument("--run-id", type=str, default=None,
                   help="Run ID (auto-generated if omitted)")
    p.add_argument("--max-rounds", type=int, default=20,
                   help="Max optimization rounds (default: 20)")
    p.add_argument("--eval-only", action="store_true",
                   help="Run eval without optimization loop")
    p.add_argument("--parallel", type=int, default=10,
                   help="Max concurrent opencode runs (default: 10)")
    p.add_argument("--memory-limit", type=int, default=4096,
                   help="Total memory budget in MB for process tree (default: 4096)")
    p.add_argument("--verbose", action="store_true",
                   help="Print per-prompt scores to stdout")
    p.add_argument("--timeout", type=int, default=300,
                   help="Timeout per agent run in seconds (default: 300)")
    p.add_argument("--sample", type=int, default=None,
                   help="Randomly sample N prompts per category instead of all 10 (e.g., --sample 3)")
    return p


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    return build_argparser().parse_args(args)
