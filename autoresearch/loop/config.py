"""
autoresearch.loop.config

CLI argument parsing and configuration for the optimization loop.
"""

import argparse
import sys
from typing import Optional


# Exit codes
EXIT_COMPLETED = 0
EXIT_AGENT_NOT_FOUND = 1
EXIT_EVAL_PROMPTS_NOT_FOUND = 2
EXIT_OPENCODE_NOT_FOUND = 3
EXIT_BASELINE_ZERO = 4


def build_argparser() -> argparse.ArgumentParser:
    """
    Build and return the CLI argument parser.

    Returns:
        argparse.ArgumentParser configured for AutoResearch optimization loop.
    """
    parser = argparse.ArgumentParser(
        prog="autoresearch",
        description="AutoResearch optimization loop for OpenCode agent prompt improvement.",
    )

    parser.add_argument(
        "--agent",
        type=str,
        required=True,
        help="Agent name (must match _<name>_worker.md filename in .opencode/agents/)",
    )

    parser.add_argument(
        "--max-rounds",
        type=int,
        default=20,
        help="Maximum optimization iterations (default: 20)",
    )

    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.01,
        help="Minimum composite score delta to accept a change (default: 0.01)",
    )

    parser.add_argument(
        "--consecutive-no-improvement-cap",
        type=int,
        default=3,
        help="Stop after N rounds with < score_threshold improvement (default: 3)",
    )

    parser.add_argument(
        "--composite-weight",
        type=float,
        default=0.4,
        help="Weight of composite prompts in composite score, 0.0-1.0 (default: 0.4)",
    )

    parser.add_argument(
        "--stochastic-runs",
        type=int,
        default=3,
        help="Number of runs per eval prompt for stochastic handling (default: 3)",
    )

    parser.add_argument(
        "--eval-category",
        type=str,
        default="all",
        choices=["all", "standalone", "composite"],
        help="Which eval set to run: all, standalone, or composite (default: all)",
    )

    parser.add_argument(
        "--event-url",
        type=str,
        default="http://localhost:8000/events",
        help="Event stream endpoint URL for real-time viewer (default: http://localhost:8000/events)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print per-prompt scores to stdout (default: False)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Load prompts and compute baseline only, no optimization (default: False)",
    )

    return parser


def parse_args(args: Optional[list] = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: Optional list of arguments (for testing). If None, uses sys.argv.

    Returns:
        Parsed argparse.Namespace.
    """
    parser = build_argparser()
    return parser.parse_args(args)
