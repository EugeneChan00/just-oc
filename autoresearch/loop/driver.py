"""
autoresearch.loop.driver

Eval harness driver. Runs agents against spec prompts, evaluates via LLM judge,
scores via hierarchy (sub_metric → metric → category → composite → run),
writes results.jsonl, prints rich table summary.
Optimization loop: reads program.md, feeds scores to optimizer agent, applies edits.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path
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
from autoresearch.harness.scorer import full_breakdown, score_run, format_score_summary
from autoresearch.loop.config import parse_args, EXIT_COMPLETED, EXIT_AGENT_NOT_FOUND, EXIT_OPENCODE_NOT_FOUND


console = Console()
AGENT_DIR = Path(".opencode/agents")


class EvalDriver:
    """Coordinates eval runs: spec → agent → evaluator → results → optimizer."""

    def __init__(self, args):
        self.args = args
        self.runner = Runner(timeout=args.timeout)
        self.spec_reader = SpecReader()
        self.evaluator = Evaluator(self.runner)
        self.results_writer = ResultsWriter()
        self.scaffolder = Scaffolder()
        self.runtime_log = RuntimeLog()
        self.verbose = args.verbose
        self.round_history: list[dict] = []  # stores {round, run_id, scores, breakdown}

    def _log(self, msg: str) -> None:
        if self.verbose:
            console.print(f"[dim]{msg}[/dim]")

    def _generate_run_id(self, iteration: int = 1) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"run-{ts}-{iteration}"

    # ── Eval prompt ──────────────────────────────────────────────

    def eval_prompt(
        self, agent_name: str, category: str, prompt_data: dict,
        prompt_index: int, sub_metrics: list[dict], scaffold_path: str | None,
    ) -> dict[str, dict]:
        """Run one agent prompt and evaluate. Returns {numeric_id: {description, result}}."""
        prompt_text = prompt_data["prompt"]
        self._log(f"  [{category}] prompt {prompt_index}: {prompt_text[:80]}...")
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

        if result and result.stdout:
            self.runtime_log.log_raw_ndjson(agent_name, category, prompt_index, result.stdout)
        self.runtime_log.log_agent_response(
            agent_name, category, prompt_index,
            parsed["text"], parsed.get("task_calls", []), parsed.get("tool_calls", []),
            parsed.get("tokens"), parsed.get("error"), run_elapsed,
        )

        eval_start = time.time()
        eval_result = self.evaluator.evaluate_category(
            category=category, prompt_text=prompt_text,
            agent_response=parsed["text"], parsed_events=parsed,
            sub_metric_defs=sub_metrics,
        )
        eval_elapsed = time.time() - eval_start

        self.runtime_log.log_eval_result(agent_name, category, prompt_index, eval_result, eval_elapsed)

        if self.verbose:
            passes = sum(1 for v in eval_result.values() if v.get("result") is True)
            console.print(f"  [{category}] {passes}/9 ({run_elapsed:.1f}s + {eval_elapsed:.1f}s eval)")

        return eval_result

    # ── Eval agent (full pass) ───────────────────────────────────

    def eval_agent(self, agent_name: str, run_id: str) -> tuple[dict, float]:
        """Run full eval: 3 categories × 1 prompt each (expandable to 10).

        Returns (merged_27_results, composite_score).
        """
        console.print(f"\n[bold]Evaluating: {agent_name}[/bold]")
        scaffold_path = self.scaffolder.scaffold(agent_name, run_id)
        log_path = self.runtime_log.start(agent_name, run_id)
        self.runtime_log.log_scaffold(agent_name, str(scaffold_path))
        self._log(f"Log: {log_path}")

        all_results: dict[str, dict] = {}
        prompt_composites: list[float] = []

        for category in CATEGORIES:
            console.print(f"  Category: [cyan]{category}[/cyan]")
            prompts = self.spec_reader.get_prompts(agent_name, category)
            sub_metrics = self.spec_reader.get_sub_metric_definitions(agent_name, category)

            if not prompts:
                continue

            # Run first prompt per category (expand to all 10 for full eval)
            prompt_result = self.eval_prompt(
                agent_name, category, prompts[0], 0, sub_metrics, str(scaffold_path)
            )
            for nid, val in prompt_result.items():
                all_results[nid] = val

        # Compute scores
        breakdown = full_breakdown(all_results)
        prompt_composites.append(breakdown["composite"])
        run_score = score_run(prompt_composites)

        if self.verbose:
            console.print(f"\n[bold]Scores:[/bold]")
            console.print(format_score_summary(breakdown))
            console.print(f"[bold]Run score: {run_score:.3f}[/bold]")

        self.runtime_log.close()
        self.scaffolder.cleanup(scaffold_path)
        self.results_writer.write(agent_name, run_id, all_results)

        return all_results, run_score

    # ── Multi-agent eval ─────────────────────────────────────────

    def eval_all_sync(self, agents: list[str], run_id: str) -> list[tuple[dict, float]]:
        """Run eval for multiple agents sequentially."""
        return [self.eval_agent(agent, run_id) for agent in agents]

    # ── Optimization loop ────────────────────────────────────────

    def load_agent_prompt(self, agent_name: str) -> str:
        """Read markdown body from agent file (after YAML frontmatter)."""
        path = AGENT_DIR / f"{agent_name}.md"
        content = path.read_text()
        parts = content.split("\n---\n", maxsplit=2)
        if len(parts) < 3:
            raise ValueError(f"Agent file {path} missing YAML frontmatter")
        return parts[2].strip()

    def save_agent_prompt(self, agent_name: str, new_prompt: str, backup_round: int | None = None) -> None:
        """Write markdown body, preserving YAML frontmatter."""
        path = AGENT_DIR / f"{agent_name}.md"
        content = path.read_text()
        parts = content.split("\n---\n", maxsplit=2)
        frontmatter = parts[0] + "\n---\n"

        if backup_round is not None:
            backup_dir = Path(f"autoresearch/results/{agent_name}/backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"round_{backup_round}.md").write_text(content)

        path.write_text(frontmatter + "\n" + new_prompt + "\n")

    def build_optimizer_prompt(self, agent_name: str, current_prompt: str, program_text: str) -> str:
        """Build the prompt sent to the optimizer agent."""
        # Last 5 rounds
        last_5 = self.round_history[-5:]
        last_5_text = json.dumps(last_5, indent=2) if last_5 else "No previous rounds."

        # Top 3 rounds by score
        sorted_rounds = sorted(self.round_history, key=lambda r: r.get("run_score", 0), reverse=True)
        top_3 = sorted_rounds[:3]
        top_3_text = json.dumps(top_3, indent=2) if top_3 else "No rounds yet."

        return f"""{program_text}

---

## Target Agent: {agent_name}

## Current Prompt (markdown body)
{current_prompt}

---

## Last 5 Rounds (most recent first)
{last_5_text}

## Top 3 Rounds (highest scoring)
{top_3_text}

---

Now analyze the score history, identify the weakest sub-metrics, and propose targeted edits.
Return ONLY the JSON object with "reasoning" and "edits" fields."""

    # ── Diff-based edit application ──────────────────────────────

    def apply_edits(self, prompt: str, edits: list[dict]) -> tuple[str, int]:
        """Apply a list of {old_text, new_text} edits to the prompt.

        Returns (modified_prompt, edits_applied_count).
        """
        applied = 0
        for edit in edits:
            old_text = edit.get("old_text", "")
            new_text = edit.get("new_text", "")
            if old_text and old_text in prompt:
                prompt = prompt.replace(old_text, new_text, 1)
                applied += 1
        return prompt, applied

    # ── Git commit per iteration ─────────────────────────────────

    def git_commit(self, agent_name: str, round_num: int, score: float, reasoning: str, accepted: bool) -> None:
        """Commit agent file changes after each optimization round."""
        agent_file = AGENT_DIR / f"{agent_name}.md"
        status = "accepted" if accepted else "rejected"
        msg = (
            f"autoresearch: {agent_name} round {round_num} ({status}, score={score:.3f})\n\n"
            f"{reasoning[:500]}"
        )
        try:
            subprocess.run(["git", "add", str(agent_file)], capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", msg], capture_output=True, timeout=10)
            self._log(f"  Git commit: round {round_num} ({status})")
        except Exception as e:
            self._log(f"  Git commit failed: {e}")

    # ── Optimization loop ────────────────────────────────────────

    def run_optimization(self, agent_name: str) -> None:
        """Run the optimization loop for one agent."""
        program_path = Path("autoresearch/program.md")
        if not program_path.exists():
            console.print("[red]Error: program.md not found[/red]")
            return
        program_text = program_path.read_text()

        console.print(f"\n[bold cyan]Optimization: {agent_name}[/bold cyan] | max_rounds={self.args.max_rounds}")

        # Baseline eval
        run_id = self._generate_run_id(0)
        results, baseline_score = self.eval_agent(agent_name, run_id)
        baseline_breakdown = full_breakdown(results)

        self.round_history.append({
            "round": 0, "run_id": run_id, "run_score": baseline_score,
            "categories": baseline_breakdown["categories"],
            "sub_metrics": {k: v for k, v in baseline_breakdown["sub_metrics"].items() if v is not None},
        })

        console.print(f"\n[bold]Baseline score: {baseline_score:.3f}[/bold]")
        best_score = baseline_score

        for round_num in range(1, self.args.max_rounds + 1):
            console.print(f"\n{'='*60}")
            console.print(f"[bold]Round {round_num}/{self.args.max_rounds}[/bold]")

            current_prompt = self.load_agent_prompt(agent_name)
            optimizer_prompt = self.build_optimizer_prompt(agent_name, current_prompt, program_text)

            # Call optimizer
            self._log("Calling optimizer agent...")
            try:
                opt_result = self.runner.run("optimizer", optimizer_prompt)
                opt_parsed = EventParser.parse(opt_result.stdout)
            except subprocess.TimeoutExpired:
                console.print(f"  [yellow]Round {round_num}: optimizer timed out, skipping[/yellow]")
                continue

            # Parse optimizer response — expect {reasoning, edits}
            reasoning = ""
            edits = []
            # Try extracting JSON with edits array
            for pattern in [
                r"```json\s*(\{.*?\})\s*```",
                r"```\s*(\{.*?\})\s*```",
                r"(\{[^{}]*\"edits\"[^{}]*\[.*?\][^{}]*\})",
            ]:
                match = re.search(pattern, opt_parsed["text"], re.DOTALL)
                if match:
                    try:
                        obj = json.loads(match.group(1))
                        reasoning = obj.get("reasoning", "")
                        edits = obj.get("edits", [])
                        break
                    except (json.JSONDecodeError, IndexError):
                        continue

            # Fallback: try parsing entire text as JSON
            if not edits:
                try:
                    obj = json.loads(opt_parsed["text"].strip())
                    reasoning = obj.get("reasoning", "")
                    edits = obj.get("edits", [])
                except json.JSONDecodeError:
                    pass

            if not edits:
                console.print(f"  [yellow]Round {round_num}: optimizer returned no edits, skipping[/yellow]")
                continue

            console.print(f"  [dim]Reasoning: {reasoning[:200]}[/dim]")
            console.print(f"  [dim]Edits proposed: {len(edits)}[/dim]")

            # Apply diff-based edits
            proposed_prompt, applied_count = self.apply_edits(current_prompt, edits)

            if applied_count == 0:
                console.print(f"  [yellow]Round {round_num}: no edits matched, skipping[/yellow]")
                continue

            console.print(f"  [dim]Edits applied: {applied_count}/{len(edits)}[/dim]")

            # Backup and write
            self.save_agent_prompt(agent_name, proposed_prompt, backup_round=round_num)

            # Eval the edited prompt
            run_id = self._generate_run_id(round_num)
            results, new_score = self.eval_agent(agent_name, run_id)
            new_breakdown = full_breakdown(results)

            self.round_history.append({
                "round": round_num, "run_id": run_id, "run_score": new_score,
                "categories": new_breakdown["categories"],
                "sub_metrics": {k: v for k, v in new_breakdown["sub_metrics"].items() if v is not None},
                "reasoning": reasoning[:500],
                "edits_proposed": len(edits),
                "edits_applied": applied_count,
            })

            # Accept or reject
            accepted = new_score > best_score
            if accepted:
                delta = new_score - best_score
                best_score = new_score
                console.print(f"  [green]ACCEPTED: {new_score:.3f} (+{delta:.3f})[/green]")
            else:
                self.save_agent_prompt(agent_name, current_prompt)
                console.print(f"  [red]REJECTED: {new_score:.3f} (best={best_score:.3f})[/red]")

            # Git commit after each round
            self.git_commit(agent_name, round_num, new_score, reasoning, accepted)

        console.print(f"\n[bold]Optimization complete. Best score: {best_score:.3f}[/bold]")

    # ── Summary table ────────────────────────────────────────────

    def print_summary(self, agents: list[str], results: list[tuple[dict, float]]) -> None:
        """Print rich table with scores per agent."""
        table = Table(title="Eval Results")
        table.add_column("Agent", style="bold")
        table.add_column("Accuracy", justify="center")
        table.add_column("Rejection", justify="center")
        table.add_column("Delegation", justify="center")
        table.add_column("Composite", justify="center")

        for agent, (result, run_score) in zip(agents, results):
            bd = full_breakdown(result)

            def fmt(val):
                if val is None:
                    return "[dim]N/A[/dim]"
                if val >= 0.8:
                    return f"[green]{val:.3f}[/green]"
                if val >= 0.5:
                    return f"[yellow]{val:.3f}[/yellow]"
                return f"[red]{val:.3f}[/red]"

            table.add_row(
                agent,
                fmt(bd["categories"].get("accuracy")),
                fmt(bd["categories"].get("rejection")),
                fmt(bd["categories"].get("delegation")),
                fmt(bd["composite"]),
            )

        console.print()
        console.print(table)


def main():
    args = parse_args()

    try:
        subprocess.run(["opencode", "--version"], capture_output=True, timeout=5)
    except FileNotFoundError:
        console.print("[red]Error: opencode binary not found[/red]")
        sys.exit(EXIT_OPENCODE_NOT_FOUND)

    driver = EvalDriver(args)

    if args.agent == "all":
        agents = driver.spec_reader.list_agents()
    else:
        agents = [args.agent]

    for agent in agents:
        try:
            driver.spec_reader.load_agent_specs(agent)
        except FileNotFoundError:
            console.print(f"[red]Error: spec files not found for agent '{agent}'[/red]")
            sys.exit(EXIT_AGENT_NOT_FOUND)

    run_id = args.run_id or driver._generate_run_id()
    console.print(f"[bold]AutoResearch[/bold] | run_id={run_id} | agents={len(agents)} | mode={'eval-only' if args.eval_only else 'optimize'}")

    start = time.time()

    if args.eval_only:
        results = driver.eval_all_sync(agents, run_id)
        driver.print_summary(agents, results)
    else:
        for agent in agents:
            driver.run_optimization(agent)

    console.print(f"\n[dim]Completed in {time.time() - start:.1f}s[/dim]")
    sys.exit(EXIT_COMPLETED)


if __name__ == "__main__":
    main()
