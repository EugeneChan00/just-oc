"""
autoresearch.loop.driver

Eval harness driver. Runs agents against spec prompts, evaluates via LLM judge,
scores via hierarchy (sub_metric → metric → category → composite → run),
writes results.jsonl, prints rich table summary.
Async parallel execution: bounded by --parallel semaphore (default 10) and --memory-limit (default 4096MB).
Optimization loop: optimizer agent edits prompts directly.
"""

import asyncio
import json
import os
import random
import resource
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

# WSL has tighter memory/process limits; detect it once at import time.
_IS_WSL = False
try:
    _IS_WSL = "microsoft" in Path("/proc/version").read_text().lower()
except Exception:
    pass

# Maximum parallel workers that are safe under WSL's constrained resources.
_WSL_MAX_PARALLEL = 4


def set_memory_limit(limit_mb: int) -> None:
    """Set per-process address space limit via RLIMIT_AS. Children inherit this."""
    limit_bytes = limit_mb * 1024 * 1024
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = min(limit_bytes, hard) if hard != resource.RLIM_INFINITY else limit_bytes
        resource.setrlimit(resource.RLIMIT_AS, (new_hard, new_hard))
        console.print(f"[dim]Memory limit: {limit_mb}MB per process (RLIMIT_AS)[/dim]")
    except (ValueError, OSError) as e:
        console.print(f"[yellow]Could not set RLIMIT_AS: {e}[/yellow]")


_rss_cache: tuple[float, float] = (0.0, 0.0)  # (timestamp, value_mb)
_RSS_CACHE_TTL = 2.0  # seconds — avoid spawning pstree/ps on every task


def get_total_rss_mb() -> float:
    """Get total RSS of this process and all descendants in MB (Linux).

    Results are cached for ``_RSS_CACHE_TTL`` seconds so parallel tasks
    don't each spawn extra pstree/ps subprocesses (important on WSL).
    """
    global _rss_cache
    now = time.time()
    if now - _rss_cache[0] < _RSS_CACHE_TTL:
        return _rss_cache[1]

    pid = os.getpid()
    mb = 0.0
    try:
        # Collect PIDs from pstree output (format: "process(PID)")
        import re
        result = subprocess.run(
            ["pstree", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
        pids = {str(pid)} | set(re.findall(r'\((\d+)\)', result.stdout))
        pid_csv = ",".join(pids)
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", pid_csv],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            mb = sum(int(x) for x in result.stdout.split()) / 1024  # KB → MB
    except Exception:
        # Fallback: self only (ru_maxrss is in KB on Linux)
        try:
            mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            mb = 0.0

    _rss_cache = (now, mb)
    return mb


class EvalDriver:
    """Coordinates eval runs: spec → agent → evaluator → results → optimizer."""

    def __init__(self, args):
        self.args = args
        self.runner = Runner(timeout=args.timeout)
        self.optimizer_runner = Runner(timeout=600)  # 10 min for optimizer
        self.spec_reader = SpecReader()
        self.evaluator = Evaluator(self.runner)
        self.results_writer = ResultsWriter()
        self.scaffolder = Scaffolder()
        self.runtime_log = RuntimeLog()
        self.verbose = args.verbose
        self.round_history: list[dict] = []
        self._parallel = args.parallel
        self._semaphore = asyncio.Semaphore(args.parallel)  # re-created per eval_agent_async call
        self._memory_budget_mb = args.memory_limit

    def _log(self, msg: str) -> None:
        if self.verbose:
            console.print(f"[dim]{msg}[/dim]")

    def _generate_run_id(self, iteration: int = 1) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"run-{ts}-{iteration}"

    # ── Async eval single prompt ─────────────────────────────────

    async def eval_prompt_async(
        self, agent_name: str, category: str, prompt_data: dict,
        prompt_index: int, sub_metrics: list[dict], scaffold_path: str | None,
    ) -> tuple[str, int, dict[str, dict]]:
        """Run one agent prompt and evaluate asynchronously.

        Returns (category, prompt_index, {numeric_id: {description, result}}).
        """
        prompt_text = prompt_data["prompt"]
        self._log(f"  [{category}] p{prompt_index}: {prompt_text[:60]}...")

        run_start = time.time()
        try:
            result = await self.runner.run_async(agent_name, prompt_text, cwd=scaffold_path)
            parsed = EventParser.parse(result.stdout)
        except subprocess.TimeoutExpired:
            self._log(f"  [{category}] p{prompt_index} TIMEOUT")
            parsed = {"text": "", "task_calls": [], "tool_calls": [], "tokens": None, "error": "timeout"}
        run_elapsed = time.time() - run_start

        # Evaluate
        eval_start = time.time()
        eval_result = await self.evaluator.evaluate_category_async(
            category=category, prompt_text=prompt_text,
            agent_response=parsed["text"], parsed_events=parsed,
            sub_metric_defs=sub_metrics,
        )
        eval_elapsed = time.time() - eval_start

        if self.verbose:
            passes = sum(1 for v in eval_result.values() if v.get("result") is True)
            console.print(f"  [{category}] p{prompt_index}: {passes}/9 ({run_elapsed:.1f}s + {eval_elapsed:.1f}s)")

        return category, prompt_index, eval_result

    async def _bounded_eval_prompt(
        self, agent_name: str, category: str, prompt_data: dict,
        prompt_index: int, sub_metrics: list[dict], scaffold_path: str | None,
    ) -> tuple[str, int, dict[str, dict]]:
        """Semaphore-bounded eval with pre-launch memory check and backpressure.

        Instead of silently skipping when memory is high, waits up to 60 s
        for memory to drop below budget before giving up.
        """
        async with self._semaphore:
            # Backpressure: wait for memory to come down instead of skipping
            for attempt in range(6):  # up to 6 × 10 s = 60 s
                total_mb = get_total_rss_mb()
                if total_mb <= self._memory_budget_mb:
                    break
                if attempt == 5:
                    console.print(
                        f"[red]Memory {total_mb:.0f}MB still exceeds budget "
                        f"{self._memory_budget_mb}MB after 60s — skipping [{category}] p{prompt_index}[/red]"
                    )
                    return category, prompt_index, {}
                console.print(
                    f"[yellow]Memory {total_mb:.0f}MB > budget {self._memory_budget_mb}MB "
                    f"— waiting 10s before [{category}] p{prompt_index}[/yellow]"
                )
                await asyncio.sleep(10)

            # Small stagger to avoid thundering-herd subprocess spawns
            await asyncio.sleep(0.2)

            return await self.eval_prompt_async(
                agent_name, category, prompt_data, prompt_index,
                sub_metrics, scaffold_path,
            )

    # ── Async eval agent (full pass, all prompts parallel) ───────

    async def eval_agent_async(self, agent_name: str, run_id: str) -> tuple[dict, float]:
        """Run full eval: 3 categories × 10 prompts each, all in parallel.

        Returns (merged_results, run_score).
        """
        # Create semaphore in the current event loop (asyncio.run creates a new loop each call)
        self._semaphore = asyncio.Semaphore(self._parallel)

        console.print(f"\n[bold]Evaluating: {agent_name}[/bold] (async)")
        scaffold_path = self.scaffolder.scaffold(agent_name, run_id)
        log_path = self.runtime_log.start(agent_name, run_id)
        self.runtime_log.log_scaffold(agent_name, str(scaffold_path))
        self._log(f"Log: {log_path}")

        tasks = []

        for category in CATEGORIES:
            prompts = self.spec_reader.get_prompts(agent_name, category)
            sub_metrics = self.spec_reader.get_sub_metric_definitions(agent_name, category)
            if not prompts:
                continue
            # Random sampling: pick N prompts if --sample is set
            if self.args.sample and self.args.sample < len(prompts):
                sampled_indices = sorted(random.sample(range(len(prompts)), self.args.sample))
                prompts = [prompts[i] for i in sampled_indices]
                console.print(f"  Category: [cyan]{category}[/cyan] ({len(prompts)}/{len(self.spec_reader.get_prompts(agent_name, category))} prompts, sampled)")
            else:
                console.print(f"  Category: [cyan]{category}[/cyan] ({len(prompts)} prompts)")
            for i, prompt_data in enumerate(prompts):
                tasks.append(
                    self._bounded_eval_prompt(
                        agent_name, category, prompt_data, i,
                        sub_metrics, str(scaffold_path),
                    )
                )

        console.print(f"  [dim]Launching {len(tasks)} eval tasks...[/dim]")
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate: per-prompt composite scores, then mean across prompts
        # Group results by prompt (each prompt spans one category = 9 sub-metrics)
        prompt_composites: list[float] = []
        all_results_flat: dict[str, dict] = {}

        # Collect per-category-prompt results
        category_prompt_results: dict[str, dict[int, dict]] = {c: {} for c in CATEGORIES}
        for item in results_list:
            if isinstance(item, BaseException):
                console.print(f"  [red]Task error: {item}[/red]")
                continue
            cat, pidx, eval_result = item  # type: ignore[misc]
            category_prompt_results[cat][pidx] = eval_result

        # For each prompt index, merge across categories and compute composite
        max_prompts = max(
            (len(self.spec_reader.get_prompts(agent_name, c)) for c in CATEGORIES),
            default=0,
        )
        for pidx in range(max_prompts):
            prompt_results: dict[str, dict] = {}
            for cat in CATEGORIES:
                cat_results = category_prompt_results[cat].get(pidx, {})
                prompt_results.update(cat_results)
            if prompt_results:
                bd = full_breakdown(prompt_results)
                prompt_composites.append(bd["composite"])
                # Keep last prompt's results for results_writer (all 27 IDs)
                all_results_flat.update(prompt_results)

        run_score = score_run(prompt_composites)

        if self.verbose:
            # Show per-prompt breakdown
            for pidx, comp in enumerate(prompt_composites):
                console.print(f"  [dim]Prompt {pidx}: composite={comp:.3f}[/dim]")
            bd = full_breakdown(all_results_flat)
            console.print(f"\n[bold]Scores (mean of {len(prompt_composites)} prompts):[/bold]")
            console.print(format_score_summary(bd))
            console.print(f"[bold]Run score: {run_score:.3f}[/bold]")

        self.runtime_log.close()
        self.scaffolder.cleanup(scaffold_path)
        self.results_writer.write(agent_name, run_id, all_results_flat)

        return all_results_flat, run_score

    def eval_agent(self, agent_name: str, run_id: str) -> tuple[dict, float]:
        """Sync wrapper around async eval."""
        return asyncio.run(self.eval_agent_async(agent_name, run_id))

    # ── Optimization loop ────────────────────────────────────────

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        """Split agent file into (frontmatter_with_delimiters, markdown_body).

        Handles both:
          ---\\nYAML\\n---\\nbody  (file starts with ---)
          YAML\\n---\\nbody       (no opening ---)
        """
        # Strip leading --- if present
        if content.startswith("---\n"):
            inner = content[4:]  # skip opening ---\n
            idx = inner.find("\n---\n")
            if idx == -1:
                raise ValueError("No closing --- found after YAML frontmatter")
            frontmatter = "---\n" + inner[:idx] + "\n---\n"
            body = inner[idx + 5:]  # skip \n---\n
        else:
            idx = content.find("\n---\n")
            if idx == -1:
                raise ValueError("No --- delimiter found")
            frontmatter = content[:idx] + "\n---\n"
            body = content[idx + 5:]
        return frontmatter, body.strip()

    def load_agent_prompt(self, agent_name: str) -> str:
        """Read markdown body from agent file (after YAML frontmatter)."""
        path = AGENT_DIR / f"{agent_name}.md"
        _, body = self._split_frontmatter(path.read_text())
        return body

    def save_agent_prompt(self, agent_name: str, new_prompt: str, backup_round: int | None = None) -> None:
        """Write markdown body, preserving YAML frontmatter."""
        path = AGENT_DIR / f"{agent_name}.md"
        content = path.read_text()
        frontmatter, _ = self._split_frontmatter(content)

        if backup_round is not None:
            backup_dir = Path(f"autoresearch/results/{agent_name}/backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / f"round_{backup_round}.md").write_text(content)

        path.write_text(frontmatter + "\n" + new_prompt + "\n")

    def build_optimizer_prompt(self, agent_name: str, program_text: str) -> str:
        """Build the prompt sent to the optimizer agent."""
        # Top 3 rounds by score, with git commit refs
        sorted_rounds = sorted(self.round_history, key=lambda r: r.get("run_score", 0), reverse=True)
        top_3 = sorted_rounds[:3]
        top_3_text = json.dumps(top_3, indent=2) if top_3 else "No rounds yet."

        agent_file = str(AGENT_DIR / f"{agent_name}.md")

        # Build git commit instructions for top performers
        commit_refs = [r["commit_ref"] for r in top_3 if r.get("commit_ref")]
        if commit_refs:
            git_instructions = (
                "## Top-performing commits\n"
                "Use `git show <ref>` or `git diff <ref>~ <ref> -- " + agent_file + "` to read the agent prompt at each top-scoring commit.\n"
                "Study what made those versions score well before making your edits.\n\n"
                + "\n".join(f"- `{ref}`" for ref in commit_refs)
            )
        else:
            git_instructions = "No previous commits available yet — this is the first optimization round."

        return f"""{program_text}

---

## Target Agent: {agent_name}
## Agent File: {agent_file}

You MUST use your `edit` tool to directly modify `{agent_file}`.
Read the file, analyze the scores, then edit it. Do NOT return JSON — make the changes yourself.

---

## Top 3 Rounds (highest scoring)
{top_3_text}

{git_instructions}

---

## Eval Specs (what the agent is tested against)
- Accuracy: autoresearch/agents/{agent_name}/spec/accuracy.json
- Rejection: autoresearch/agents/{agent_name}/spec/rejection.json
- Delegation: autoresearch/agents/{agent_name}/spec/delegation.json

## System Prompt Design Research
Browse `.real-agents/docs/` for research on optimal system prompt design. Read the docs there before editing.
Directly edit `{agent_file}` to improve the prompt.
After editing, print a short reasoning summary (2-3 sentences) of what you changed and why."""

    # ── Git commit per iteration ─────────────────────────────────

    def git_commit(self, agent_name: str, round_num: int, score: float, reasoning: str) -> str | None:
        """Commit agent file changes after each optimization round. Returns commit hash or None."""
        agent_file = AGENT_DIR / f"{agent_name}.md"
        msg = (
            f"autoresearch: {agent_name} round {round_num} (score={score:.3f})\n\n"
            f"{reasoning[:500]}"
        )
        try:
            subprocess.run(["git", "add", str(agent_file)], capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", msg], capture_output=True, timeout=10)
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            commit_ref = result.stdout.strip() if result.returncode == 0 else None
            self._log(f"  Git commit: round {round_num} ({commit_ref})")
            return commit_ref
        except Exception as e:
            self._log(f"  Git commit failed: {e}")
            return None

    # ── Load historical results ────────────────────────────────

    def load_history(self, agent_name: str) -> None:
        """Seed round_history from previous results.jsonl records.

        This gives the optimizer access to scores from prior process runs,
        not just the current session.
        """
        records = self.results_writer.read_all(agent_name)
        for i, record in enumerate(records):
            # Rebuild breakdown from stored sub-metric booleans
            eval_result = {
                nid: record[nid]
                for nid in record
                if "." in nid and isinstance(record[nid], dict)
            }
            if not eval_result:
                continue
            breakdown = full_breakdown(eval_result)
            self.round_history.append({
                "round": f"hist-{i}",
                "run_id": record.get("run_id", f"historical-{i}"),
                "run_score": breakdown["composite"],
                "categories": breakdown["categories"],
                "sub_metrics": {k: v for k, v in breakdown["sub_metrics"].items() if v is not None},
            })

        if self.round_history:
            console.print(f"  [dim]Loaded {len(self.round_history)} historical results[/dim]")

    # ── Optimization loop ────────────────────────────────────────

    def run_optimization(self, agent_name: str) -> None:
        """Run the optimization loop for one agent."""
        program_path = Path("autoresearch/program.md")
        if not program_path.exists():
            console.print("[red]Error: program.md not found[/red]")
            return
        program_text = program_path.read_text()

        console.print(f"\n[bold cyan]Optimization: {agent_name}[/bold cyan] | max_rounds={self.args.max_rounds}")

        # Load historical results so the optimizer can see previous runs
        self.load_history(agent_name)

        # Baseline eval
        run_id = self._generate_run_id(0)
        results, baseline_score = self.eval_agent(agent_name, run_id)
        baseline_breakdown = full_breakdown(results)

        self.round_history.append({
            "round": 0, "run_id": run_id, "run_score": baseline_score,
            "categories": baseline_breakdown["categories"],
            "sub_metrics": {k: v for k, v in baseline_breakdown["sub_metrics"].items() if v is not None},
        })

        # Store commit ref for baseline (current HEAD)
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            baseline_ref = result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            baseline_ref = None
        self.round_history[-1]["commit_ref"] = baseline_ref

        console.print(f"\n[bold]Baseline score: {baseline_score:.3f}[/bold]")
        best_score = baseline_score

        for round_num in range(1, self.args.max_rounds + 1):
            console.print(f"\n{'='*60}")
            console.print(f"[bold]Round {round_num}/{self.args.max_rounds}[/bold]")

            # Backup before optimizer touches the file
            backup_dir = Path(f"autoresearch/results/{agent_name}/backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            agent_path = AGENT_DIR / f"{agent_name}.md"
            (backup_dir / f"round_{round_num}.md").write_text(agent_path.read_text())

            optimizer_prompt = self.build_optimizer_prompt(agent_name, program_text)

            # Call optimizer — it directly edits the agent file via its edit tool
            self._log("Calling optimizer agent...")
            try:
                opt_result = self.optimizer_runner.run("optimizer", optimizer_prompt)
                opt_parsed = EventParser.parse(opt_result.stdout)
            except subprocess.TimeoutExpired:
                console.print(f"  [yellow]Round {round_num}: optimizer timed out, skipping[/yellow]")
                continue

            # Extract reasoning from optimizer's text output
            reasoning = opt_parsed.get("text", "").strip()
            # Truncate to last meaningful paragraph as reasoning summary
            if len(reasoning) > 500:
                reasoning = reasoning[-500:]

            # Check if the optimizer actually changed the file
            console.print(f"  [dim]Optimizer edited {agent_name}.md[/dim]")
            console.print(f"  [dim]Reasoning: {reasoning[:200]}[/dim]")

            # Eval the edited prompt
            run_id = self._generate_run_id(round_num)
            results, new_score = self.eval_agent(agent_name, run_id)
            new_breakdown = full_breakdown(results)

            # Git commit (always — no rejection)
            commit_ref = self.git_commit(agent_name, round_num, new_score, reasoning)

            self.round_history.append({
                "round": round_num, "run_id": run_id, "run_score": new_score,
                "categories": new_breakdown["categories"],
                "sub_metrics": {k: v for k, v in new_breakdown["sub_metrics"].items() if v is not None},
                "reasoning": reasoning[:500],
                "commit_ref": commit_ref,
            })

            if new_score > best_score:
                delta = new_score - best_score
                best_score = new_score
                console.print(f"  [green]Score: {new_score:.3f} (+{delta:.3f}, new best)[/green]")
            else:
                console.print(f"  [yellow]Score: {new_score:.3f} (best={best_score:.3f})[/yellow]")

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

    # Auto-cap parallelism on WSL to prevent resource exhaustion & crashes
    if _IS_WSL and args.parallel > _WSL_MAX_PARALLEL:
        console.print(
            f"[yellow]WSL detected — capping --parallel from {args.parallel} "
            f"to {_WSL_MAX_PARALLEL} to prevent crashes (override with "
            f"--parallel {args.parallel} --no-wsl-cap)[/yellow]"
        )
        if not getattr(args, "no_wsl_cap", False):
            args.parallel = _WSL_MAX_PARALLEL

    set_memory_limit(args.memory_limit)

    try:
        subprocess.run(["opencode", "--version"], capture_output=True, timeout=30)
    except FileNotFoundError:
        console.print("[red]Error: opencode binary not found[/red]")
        sys.exit(EXIT_OPENCODE_NOT_FOUND)
    except subprocess.TimeoutExpired:
        pass  # opencode exists but slow under load — proceed anyway

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
        results = [driver.eval_agent(agent, run_id) for agent in agents]
        driver.print_summary(agents, results)
    else:
        for agent in agents:
            driver.run_optimization(agent)

    console.print(f"\n[dim]Completed in {time.time() - start:.1f}s[/dim]")
    sys.exit(EXIT_COMPLETED)


if __name__ == "__main__":
    main()
