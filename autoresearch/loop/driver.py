"""
autoresearch.loop.driver

Eval harness driver. Runs agents against spec prompts, evaluates via LLM judge,
writes results.jsonl, prints rich table summary.
"""

import subprocess
import sys
import time
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from autoresearch.harness.runner import Runner
from autoresearch.harness.event_listener import EventParser
from autoresearch.harness.spec_reader import SpecReader, CATEGORIES
from autoresearch.harness.evaluator import Evaluator
from autoresearch.harness.results_writer import ResultsWriter
from autoresearch.harness.scaffolder import Scaffolder
from autoresearch.harness.runtime_log import RuntimeLog
from autoresearch.loop.config import parse_args, EXIT_COMPLETED, EXIT_AGENT_NOT_FOUND, EXIT_OPENCODE_NOT_FOUND


console = Console()


class EvalDriver:
    """Coordinates eval runs: spec → agent → evaluator → results."""

    def __init__(self, args):
        self.args = args
        self.runner = Runner(timeout=args.timeout)
        self.spec_reader = SpecReader()
        self.evaluator = Evaluator(self.runner)
        self.results_writer = ResultsWriter()
        self.scaffolder = Scaffolder()
        self.runtime_log = RuntimeLog()
        self.verbose = args.verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            console.print(f"[dim]{msg}[/dim]")

    def _generate_run_id(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"run-{ts}-1"

    def eval_prompt(
        self,
        agent_name: str,
        category: str,
        prompt_data: dict,
        prompt_index: int,
        sub_metrics: list[dict],
        scaffold_path: str | None,
    ) -> dict[str, dict]:
        """Run one agent prompt and evaluate it.

        Returns: {numeric_id: {description, result}}
        """
        prompt_text = prompt_data["prompt"]
        self._log(f"  [{category}] Running prompt {prompt_index}: {prompt_text[:80]}...")

        # Log agent run start
        self.runtime_log.log_agent_run(agent_name, category, prompt_index, prompt_text)

        run_start = time.time()
        result = None
        try:
            result = self.runner.run(agent_name, prompt_text, cwd=scaffold_path)
            parsed = EventParser.parse(result.stdout)
        except subprocess.TimeoutExpired:
            self._log(f"  [{category}] TIMEOUT")
            parsed = {"text": "", "task_calls": [], "tool_calls": [], "tokens": None, "error": "timeout"}
        run_elapsed = time.time() - run_start

        if parsed.get("error"):
            self._log(f"  [{category}] Error: {parsed['error']}")

        self._log(f"  [{category}] Response: {parsed['text'][:100]}...")
        self._log(f"  [{category}] Task calls: {len(parsed.get('task_calls', []))}, Tool calls: {len(parsed.get('tool_calls', []))}")

        # Log raw NDJSON and agent response
        if result and result.stdout:
            self.runtime_log.log_raw_ndjson(agent_name, category, prompt_index, result.stdout)
        self.runtime_log.log_agent_response(
            agent_name, category, prompt_index,
            parsed["text"], parsed.get("task_calls", []), parsed.get("tool_calls", []),
            parsed.get("tokens"), parsed.get("error"), run_elapsed,
        )

        # Evaluate via LLM judge
        eval_start = time.time()
        eval_result = self.evaluator.evaluate_category(
            category=category,
            prompt_text=prompt_text,
            agent_response=parsed["text"],
            parsed_events=parsed,
            sub_metric_defs=sub_metrics,
        )
        eval_elapsed = time.time() - eval_start

        # Log eval result
        self.runtime_log.log_eval_result(agent_name, category, prompt_index, eval_result, eval_elapsed)

        if self.verbose:
            passes = sum(1 for v in eval_result.values() if v.get("result") is True)
            console.print(f"  [{category}] Score: {passes}/9 ({run_elapsed:.1f}s run, {eval_elapsed:.1f}s eval)")

        return eval_result

    def eval_agent(self, agent_name: str, run_id: str) -> dict[str, dict]:
        """Run full eval for one agent: 3 categories × 10 prompts each.

        Returns the merged 27-field result record.
        """
        console.print(f"\n[bold]Evaluating: {agent_name}[/bold]")
        scaffold_path = self.scaffolder.scaffold(agent_name, run_id)
        self.runtime_log.log_scaffold(agent_name, str(scaffold_path))
        self._log(f"Scaffold: {scaffold_path}")

        # Start runtime log for this agent
        log_path = self.runtime_log.start(agent_name, run_id)
        self._log(f"Runtime log: {log_path}")

        all_results: dict[str, dict] = {}

        for category in CATEGORIES:
            console.print(f"  Category: [cyan]{category}[/cyan]")
            prompts = self.spec_reader.get_prompts(agent_name, category)
            sub_metrics = self.spec_reader.get_sub_metric_definitions(agent_name, category)

            if not prompts:
                self._log(f"  No prompts for {category}, skipping")
                continue

            # Run first prompt only for now (can expand to all 10 later)
            # Using first prompt as representative eval
            prompt_result = self.eval_prompt(
                agent_name, category, prompts[0], 0, sub_metrics, str(scaffold_path)
            )

            # Merge into all_results
            for nid, val in prompt_result.items():
                all_results[nid] = val

        self.runtime_log.close()
        self.scaffolder.cleanup(scaffold_path)
        self.results_writer.write(agent_name, run_id, all_results)
        return all_results

    def eval_all_sync(self, agents: list[str], run_id: str) -> list[dict]:
        """Run eval for multiple agents sequentially."""
        results = []
        for agent in agents:
            result = self.eval_agent(agent, run_id)
            results.append(result)
        return results

    def print_summary(self, agents: list[str], results: list[dict]) -> None:
        """Print rich table with pass/fail counts per agent per category."""
        table = Table(title="Eval Results")
        table.add_column("Agent", style="bold")
        table.add_column("Accuracy (9)", justify="center")
        table.add_column("Rejection (9)", justify="center")
        table.add_column("Delegation (9)", justify="center")
        table.add_column("Total (27)", justify="center")

        for agent, result in zip(agents, results):
            acc = sum(1 for k, v in result.items() if k.startswith("1.") and v.get("result") is True)
            rej = sum(1 for k, v in result.items() if k.startswith("2.") and v.get("result") is True)
            dlg = sum(1 for k, v in result.items() if k.startswith("3.") and v.get("result") is True)
            total = acc + rej + dlg

            # Color coding
            def color(n, max_n):
                if n >= max_n * 0.8:
                    return f"[green]{n}/{max_n}[/green]"
                elif n >= max_n * 0.5:
                    return f"[yellow]{n}/{max_n}[/yellow]"
                return f"[red]{n}/{max_n}[/red]"

            table.add_row(agent, color(acc, 9), color(rej, 9), color(dlg, 9), color(total, 27))

        console.print()
        console.print(table)


def main():
    args = parse_args()

    # Check opencode binary
    try:
        subprocess.run(["opencode", "--version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        console.print("[red]Error: opencode binary not found[/red]")
        sys.exit(EXIT_OPENCODE_NOT_FOUND)

    driver = EvalDriver(args)

    # Resolve agent list
    if args.agent == "all":
        agents = driver.spec_reader.list_agents()
    else:
        agents = [args.agent]

    # Validate agents exist
    for agent in agents:
        try:
            driver.spec_reader.load_agent_specs(agent)
        except FileNotFoundError:
            console.print(f"[red]Error: spec files not found for agent '{agent}'[/red]")
            sys.exit(EXIT_AGENT_NOT_FOUND)

    run_id = args.run_id or driver._generate_run_id()
    console.print(f"[bold]AutoResearch Eval[/bold] | run_id={run_id} | agents={len(agents)}")

    # Run evals
    start = time.time()
    results = driver.eval_all_sync(agents, run_id)
    elapsed = time.time() - start

    # Print summary
    driver.print_summary(agents, results)
    console.print(f"\n[dim]Completed in {elapsed:.1f}s[/dim]")

    sys.exit(EXIT_COMPLETED)


if __name__ == "__main__":
    main()
