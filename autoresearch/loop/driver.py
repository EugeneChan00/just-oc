"""
autoresearch.loop.driver

Optimization loop driver for AutoResearch.
Orchestrates round execution, convergence checking, and results output.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoresearch.harness.runner import Runner
from autoresearch.harness.event_listener import EventListener
from autoresearch.harness.subagent_detector import SubagentDetector
from autoresearch.harness.evaluator import Evaluator, Category, EvalResult


@dataclass
class RoundResult:
    """Result of a single optimization round."""

    round_number: int
    prompt_preview: str  # first 100 chars
    composite_score: float
    standalone_score: float
    composite_score_ex: float
    overall_std: float
    accepted: bool
    confusion_matrix: Dict[str, int]
    rejection_recall: float
    false_acceptance_rate: float
    category_scores: Dict[str, float]
    tools_used: List[str]
    subagent_selected: Optional[str]
    prompt_length: int
    eval_results: List[Dict[str, Any]]


class OptimizationDriver:
    """Orchestrates the prompt optimization loop."""

    # OpenCode agent file path template
    AGENT_FILE_TEMPLATE = ".opencode/agents/{name}_worker.md"

    # Results directory template
    RESULTS_DIR_TEMPLATE = "autoresearch/results/{agent_name}"

    # Eval prompts directory template
    EVAL_PROMPTS_DIR = "autoresearch/agents/{agent_name}/eval_prompts"

    def __init__(self, args: argparse.Namespace):
        """
        Initialize OptimizationDriver.

        Args:
            args: Parsed CLI arguments from config.parse_args().
        """
        self.args = args
        self.agent_name = args.agent

        # Initialize harness components
        self.runner = Runner()
        self.listener = EventListener()
        self.detector = SubagentDetector()
        self.evaluator = Evaluator()

        # State
        self.rounds: List[RoundResult] = []
        self.best_prompt: Optional[str] = None
        self.current_prompt: Optional[str] = None
        self.baseline_score: float = 0.0

        # Results directory
        self.results_dir = Path(
            self.RESULTS_DIR_TEMPLATE.format(agent_name=self.agent_name)
        )
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Agent file path
        self.agent_file = Path(self.AGENT_FILE_TEMPLATE.format(name=self.agent_name))

        # Program file path
        self.program_file = Path("autoresearch/program.md")

        # Eval prompts directory
        self.eval_prompts_dir = Path(
            self.EVAL_PROMPTS_DIR.format(agent_name=self.agent_name)
        )

        # Event emission
        self.event_url = args.event_url
        self._event_file: Optional[Path] = None

    def load_agent_prompt(self) -> str:
        """
        Read markdown body from .opencode/agents/<name>_worker.md.

        Reads the file, splits on --- (frontmatter delimiter), and returns
        the content after the second --- (markdown body).

        Returns:
            The markdown body of the agent prompt.

        Raises:
            FileNotFoundError: If agent file not found.
        """
        if not self.agent_file.exists():
            raise FileNotFoundError(f"Agent file not found: {self.agent_file}")

        content = self.agent_file.read_text()

        # Split on first --- after opening ---
        # Format: ---\n[frontmatter]\n---\n[markdown body]
        parts = content.split("\n---\n", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid agent file format: {self.agent_file}")

        markdown_body = parts[2].strip()
        self.current_prompt = markdown_body
        return markdown_body

    def save_agent_prompt(self, prompt: str, backup: bool = True) -> None:
        """
        Write markdown body to agent file. Backup existing first.

        Preserves YAML frontmatter, replaces only markdown body.

        Args:
            prompt: New markdown body to write.
            backup: If True, backup existing file before writing.
        """
        if not self.agent_file.exists():
            raise FileNotFoundError(f"Agent file not found: {self.agent_file}")

        content = self.agent_file.read_text()

        # Extract frontmatter (everything before second ---)
        parts = content.split("\n---\n", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid agent file format: {self.agent_file}")

        frontmatter = parts[0] + "\n---\n"

        # Create backup if requested
        if backup:
            self._create_backup()

        # Write new content
        new_content = frontmatter + prompt + "\n"
        self.agent_file.write_text(new_content)
        self.current_prompt = prompt

    def _create_backup(self) -> None:
        """Create a backup of the current agent file."""
        if not self.agent_file.exists():
            return

        backup_dir = self.results_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        round_num = len(self.rounds) + 1
        backup_name = f"backup_round_{round_num}.md"
        backup_path = backup_dir / backup_name

        shutil.copy2(self.agent_file, backup_path)

    def build_optimizer_prompt(
        self,
        program_text: str,
        current_prompt: str,
        round_data: Dict[str, Any],
    ) -> str:
        """
        Build the full prompt to send to the optimizer agent.
        Concatenates program.md + current prompt + round performance data.

        Args:
            program_text: Content of program.md.
            current_prompt: Current agent prompt.
            round_data: Round performance data dict.

        Returns:
            Full optimizer prompt string.
        """
        # Format round data as JSON for readability
        round_data_str = json.dumps(round_data, indent=2)

        prompt = f"{program_text}\n\n---\n\n{current_prompt}\n\n---\n\n{round_data_str}"
        return prompt

    def get_round_summary_data(
        self, round_num: int, prev_score: float
    ) -> Dict[str, Any]:
        """
        Build round performance data dict for the optimizer prompt.
        Includes: composite_score, standalone_score, category_scores,
        confusion_matrix (tp/tn/fp/fn), rejection_recall, false_acceptance_rate.

        Args:
            round_num: Current round number.
            prev_score: Previous round's composite score (baseline if first round).

        Returns:
            Dict with round performance data.
        """
        cm = self.evaluator.confusion_matrix
        confusion_matrix = {"tp": cm.tp, "tn": cm.tn, "fp": cm.fp, "fn": cm.fn}

        # Get last round's scores if available
        if self.rounds:
            last_round = self.rounds[-1]
            composite_score = last_round.composite_score
            standalone_score = last_round.standalone_score
            category_scores = last_round.category_scores
        else:
            composite_score = prev_score
            standalone_score = prev_score
            category_scores = {
                "rejection": 0.0,
                "delegation": 0.0,
                "compliance": 0.0,
                "accuracy": 0.0,
            }

        return {
            "round_number": round_num,
            "prev_score": prev_score,
            "composite_score": composite_score,
            "standalone_score": standalone_score,
            "category_scores": category_scores,
            "confusion_matrix": confusion_matrix,
            "rejection_recall": self.evaluator.rejection_recall(),
            "false_acceptance_rate": self.evaluator.false_acceptance_rate(),
        }

    def parse_optimizer_ndjson(self, ndjson_stdout: str) -> Tuple[str, str]:
        """
        Parse NDJSON stdout from optimizer agent.
        Returns (proposed_prompt, reasoning).
        Scans for the final JSON object with both 'reasoning' and 'prompt' fields.

        Args:
            ndjson_stdout: Raw stdout from optimizer agent (NDJSON format).

        Returns:
            Tuple of (proposed_prompt, reasoning).

        Raises:
            ValueError: If no valid JSON object with both fields is found.
        """
        proposed_prompt = None
        reasoning = None

        for line in ndjson_stdout.strip().split("\n"):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "reasoning" in obj and "prompt" in obj:
                    proposed_prompt = obj["prompt"]
                    reasoning = obj["reasoning"]
            except json.JSONDecodeError:
                continue

        if proposed_prompt is None or reasoning is None:
            raise ValueError(
                "No JSON object with both 'reasoning' and 'prompt' fields found in optimizer output"
            )

        return proposed_prompt, reasoning

    def validate_proposed_prompt(self, prompt: str) -> bool:
        """
        Returns True if prompt is non-empty string between 1 and 32000 characters.

        Args:
            prompt: Proposed prompt to validate.

        Returns:
            True if valid, False otherwise.
        """
        return isinstance(prompt, str) and 1 <= len(prompt) <= 32000

    def _restore_from_backup(self) -> None:
        """
        Restore agent prompt from the most recent backup.
        """
        backup_dir = self.results_dir / "backups"
        if not backup_dir.exists():
            return

        # Find most recent backup
        backups = sorted(
            backup_dir.glob("backup_round_*.md"), key=lambda p: p.stat().st_mtime
        )
        if not backups:
            return

        latest_backup = backups[-1]
        content = latest_backup.read_text()

        # Extract markdown body (after second ---)
        parts = content.split("\n---\n", 2)
        if len(parts) < 3:
            return

        markdown_body = parts[2].strip()

        # Write back to agent file
        # Read original to preserve frontmatter
        if self.agent_file.exists():
            original_content = self.agent_file.read_text()
            orig_parts = original_content.split("\n---\n", 2)
            if len(orig_parts) >= 3:
                frontmatter = orig_parts[0] + "\n---\n"
                new_content = frontmatter + markdown_body + "\n"
                self.agent_file.write_text(new_content)
                self.current_prompt = markdown_body

    def _restore_and_skip_round(self, round_num: int, reason: str) -> RoundResult:
        """
        Create an error/abort RoundResult when optimization cannot proceed.
        Restores from backup if available.

        Args:
            round_num: Current round number.
            reason: Reason for skipping (e.g., "parse_error", "invalid_prompt", "zero_score").

        Returns:
            RoundResult with composite_score=0, accepted=False.
        """
        print(f"Skipping round {round_num}: {reason}", file=sys.stderr)
        self._restore_from_backup()

        # Reload current prompt after restore
        current_prompt = self.load_agent_prompt() if self.agent_file.exists() else ""

        round_result = RoundResult(
            round_number=round_num,
            prompt_preview=current_prompt[:100],
            composite_score=0.0,
            standalone_score=0.0,
            composite_score_ex=0.0,
            overall_std=0.0,
            accepted=False,
            confusion_matrix={"tp": 0, "tn": 0, "fp": 0, "fn": 0},
            rejection_recall=0.0,
            false_acceptance_rate=0.0,
            category_scores={
                "rejection": 0.0,
                "delegation": 0.0,
                "compliance": 0.0,
                "accuracy": 0.0,
            },
            tools_used=[],
            subagent_selected=None,
            prompt_length=len(current_prompt),
            eval_results=[],
        )

        self.rounds.append(round_result)
        return round_result

    def load_program(self) -> str:
        """
        Load program.md (shared optimizer instructions).

        Returns:
            Content of program.md.
        """
        if not self.program_file.exists():
            raise FileNotFoundError(f"program.md not found: {self.program_file}")
        return self.program_file.read_text()

    def load_eval_prompts(self) -> List[Dict[str, Any]]:
        """
        Load all eval prompts from autoresearch/agents/<agent-name>/eval_prompts/.

        Returns:
            List of dicts with 'prompt', 'expected_output', and 'category' fields.
        """
        eval_prompts = []

        if not self.eval_prompts_dir.exists():
            # Eval prompts directory doesn't exist - return empty
            # This may be expected if eval prompts haven't been generated yet
            return eval_prompts

        # Load standalone prompts
        standalone_dir = self.eval_prompts_dir / "standalone"
        if standalone_dir.exists():
            for category in ["rejection", "delegation", "compliance", "accuracy"]:
                category_dir = standalone_dir / category
                if category_dir.exists():
                    for jsonl_file in sorted(category_dir.glob("*.jsonl")):
                        try:
                            prompts = self._load_jsonl(jsonl_file, category)
                            eval_prompts.extend(prompts)
                        except Exception as e:
                            print(
                                f"Warning: Failed to load {jsonl_file}: {e}",
                                file=sys.stderr,
                            )

        # Load composite prompts
        composite_dir = self.eval_prompts_dir / "composite"
        if composite_dir.exists():
            for jsonl_file in sorted(composite_dir.glob("*.jsonl")):
                try:
                    prompts = self._load_jsonl(jsonl_file, "composite")
                    eval_prompts.extend(prompts)
                except Exception as e:
                    print(f"Warning: Failed to load {jsonl_file}: {e}", file=sys.stderr)

        return eval_prompts

    def _load_jsonl(self, path: Path, category: str) -> List[Dict[str, Any]]:
        """
        Load prompts from a .jsonl file.

        Args:
            path: Path to .jsonl file.
            category: Category for these prompts.

        Returns:
            List of dicts with prompt, expected_output, category.
        """
        prompts = []
        content = path.read_text()
        for line in content.strip().split("\n"):
            if not line:
                continue
            try:
                obj = json.loads(line)
                prompts.append(
                    {
                        "prompt": obj.get("prompt", ""),
                        "expected_output": obj.get("expected_output", ""),
                        "category": category,
                    }
                )
            except json.JSONDecodeError:
                continue
        return prompts

    def compute_baseline(self) -> float:
        """
        Run current prompt on all eval prompts, return composite score.

        Returns:
            Baseline composite score.

        Raises:
            ValueError: If baseline score is 0.
        """
        print(f"Computing baseline score for agent '{self.agent_name}'...")

        # Load current prompt
        current_prompt = self.load_agent_prompt()

        # Load eval prompts
        eval_prompts = self.load_eval_prompts()

        if not eval_prompts:
            print(
                "Warning: No eval prompts found. Baseline score will be 0.",
                file=sys.stderr,
            )
            return 0.0

        # Run evaluation
        results = self._run_evaluation(current_prompt, eval_prompts)

        # Compute composite score
        composite, standalone, composite_ex, std = self._compute_scores(results)

        self.baseline_score = composite
        print(
            f"Baseline score: {composite:.4f} (standalone={standalone:.4f}, composite={composite_ex:.4f})"
        )

        if composite == 0:
            raise ValueError("Baseline score is 0 - no viable starting point")

        return composite

    def _run_evaluation(
        self, prompt_text: str, eval_prompts: List[Dict[str, Any]]
    ) -> List[EvalResult]:
        """
        Run agent on all eval prompts and collect results.

        Args:
            prompt_text: The agent prompt to evaluate.
            eval_prompts: List of eval prompt dicts.

        Returns:
            List of EvalResult objects.
        """
        results = []

        for ep in eval_prompts:
            category = ep["category"]
            eval_prompt = ep["prompt"]
            expected = ep["expected_output"]

            # Emit eval_prompt event
            self._emit_event(
                "eval_prompt",
                {
                    "prompt": eval_prompt,
                    "category": category,
                    "expected": expected,
                },
            )

            # Run agent with stochastic runs
            stochastic_scores = []
            eval_result = None
            num_runs = max(1, self.args.stochastic_runs)
            for run_idx in range(num_runs):
                result = self.runner.run(
                    agent=self.agent_name,
                    prompt=eval_prompt,
                    format="json",
                )

                actual_output = result.stdout if result.returncode == 0 else ""
                ndjson_lines = (
                    result.stdout.strip().split("\n") if result.stdout else []
                )

                # Parse events
                self.listener.parse_stream(ndjson_lines)

                # Evaluate
                eval_result = self.evaluator.evaluate(
                    prompt=eval_prompt,
                    expected_output=expected,
                    actual_output=actual_output,
                    category=category,
                )
                stochastic_scores.append(eval_result.score)

                if self.args.verbose:
                    print(
                        f"  [{category}] score={eval_result.score:.2f} expected={expected[:50]}"
                    )

            # Aggregate stochastic scores
            if len(stochastic_scores) > 1 and eval_result is not None:
                mean, std = self.evaluator.aggregate_stochastic(stochastic_scores)
                eval_result.stochastic_mean = mean
                eval_result.stochastic_std = std
                eval_result.runs = len(stochastic_scores)

            if eval_result is not None:
                results.append(eval_result)

                # Emit score_update event
                self._emit_event(
                    "score_update",
                    {
                        "composite": eval_result.score,
                        "standalone": eval_result.score,
                        "composite_ex": eval_result.score,
                        "std": eval_result.stochastic_std or 0.0,
                    },
                )

        return results

    def _compute_scores(
        self, results: List[EvalResult]
    ) -> Tuple[float, float, float, float]:
        """
        Compute composite, standalone, composite_ex, and std scores.

        Args:
            results: List of EvalResult objects.

        Returns:
            Tuple of (composite, standalone, composite_ex, std).
        """
        if not results:
            return 0.0, 0.0, 0.0, 0.0

        standalone_results = [
            r
            for r in results
            if r.category in ("rejection", "delegation", "compliance", "accuracy")
        ]
        composite_results = [r for r in results if r.category == "composite"]

        standalone_scores = [
            r.stochastic_mean if r.stochastic_mean is not None else r.score
            for r in standalone_results
        ]
        composite_ex_scores = [
            r.stochastic_mean if r.stochastic_mean is not None else r.score
            for r in composite_results
        ]

        standalone_avg = (
            sum(standalone_scores) / len(standalone_scores)
            if standalone_scores
            else 0.0
        )
        composite_ex_avg = (
            sum(composite_ex_scores) / len(composite_ex_scores)
            if composite_ex_scores
            else 0.0
        )

        # Composite = (1 - weight) * standalone + weight * composite_ex
        composite = (
            1 - self.args.composite_weight
        ) * standalone_avg + self.args.composite_weight * composite_ex_avg

        # Overall std
        all_means = [
            r.stochastic_mean for r in results if r.stochastic_mean is not None
        ]
        if len(all_means) > 1:
            import statistics

            overall_std = statistics.stdev(all_means)
        else:
            overall_std = 0.0

        return composite, standalone_avg, composite_ex_avg, overall_std

    def run_round(self, round_num: int) -> RoundResult:
        """
        Execute one optimization round.

        Args:
            round_num: Round number.

        Returns:
            RoundResult for this round.
        """
        print(f"\n=== Round {round_num} ===")

        # Emit round_start event
        prompt_content = self.current_prompt or ""
        prompt_hash = hashlib.sha1(prompt_content.encode()).hexdigest()[:8]
        self._emit_event(
            "round_start",
            {
                "round": round_num,
                "prompt_hash": prompt_hash,
            },
        )

        # Step 1: Load current prompt
        current_prompt = self.load_agent_prompt()

        # Step 2: Get prev_score (baseline or last round)
        prev_score = (
            self.baseline_score if not self.rounds else self.rounds[-1].composite_score
        )

        # Step 3: Build optimizer prompt
        program_text = self.load_program()
        round_data = self.get_round_summary_data(round_num, prev_score)
        optimizer_prompt = self.build_optimizer_prompt(
            program_text, current_prompt, round_data
        )

        # Step 4: Call optimizer agent
        result = self.runner.run("optimizer", optimizer_prompt, format="json")

        # Step 5: Parse optimizer output
        try:
            proposed_prompt, reasoning = self.parse_optimizer_ndjson(result.stdout)
        except ValueError as e:
            print(f"Failed to parse optimizer output: {e}", file=sys.stderr)
            return self._restore_and_skip_round(round_num, f"parse_error: {e}")

        # Step 6: Validate proposed prompt
        if not self.validate_proposed_prompt(proposed_prompt):
            print(
                f"Invalid proposed prompt (length={len(proposed_prompt) if isinstance(proposed_prompt, str) else 'non-string'})",
                file=sys.stderr,
            )
            return self._restore_and_skip_round(round_num, "invalid_prompt")

        # Step 7: Backup current and write proposed
        self.save_agent_prompt(proposed_prompt, backup=True)

        # Step 8: Evaluate proposed prompt
        eval_prompts = self.load_eval_prompts()
        results = self._run_evaluation(proposed_prompt, eval_prompts)

        # Step 9: Compute scores
        proposed_composite, proposed_standalone, proposed_composite_ex, proposed_std = (
            self._compute_scores(results)
        )
        proposed_category_scores = self._compute_category_scores(results)

        # F-07: Handle zero score
        if proposed_composite == 0:
            print("Proposed prompt scored 0 — restoring backup", file=sys.stderr)
            self._restore_from_backup()
            return self._restore_and_skip_round(round_num, "zero_score")

        # Step 10: Decision
        accepted = proposed_composite > prev_score + self.args.score_threshold

        if not accepted:
            # Restore from backup
            self._restore_from_backup()
            # Reload current_prompt for round_result (it was restored)
            current_prompt = self.load_agent_prompt()

        # Build confusion matrix
        cm = self.evaluator.confusion_matrix
        confusion_matrix = {"tp": cm.tp, "tn": cm.tn, "fp": cm.fp, "fn": cm.fn}

        # Get tools used
        tools_used = self.listener.get_tools_used()
        subagent_selected = self.detector.detect([])

        round_result = RoundResult(
            round_number=round_num,
            prompt_preview=current_prompt[:100],
            composite_score=proposed_composite,
            standalone_score=proposed_standalone,
            composite_score_ex=proposed_composite_ex,
            overall_std=proposed_std,
            accepted=accepted,
            confusion_matrix=confusion_matrix,
            rejection_recall=self.evaluator.rejection_recall(),
            false_acceptance_rate=self.evaluator.false_acceptance_rate(),
            category_scores=proposed_category_scores,
            tools_used=tools_used,
            subagent_selected=subagent_selected,
            prompt_length=len(current_prompt),
            eval_results=[self._eval_result_to_dict(r) for r in results],
        )

        self.rounds.append(round_result)

        # Emit round_end event
        self._emit_event(
            "round_end",
            {
                "round": round_num,
                "score": proposed_composite,
                "accepted": accepted,
                "composite": proposed_composite,
                "standalone": proposed_standalone,
                "composite_ex": proposed_composite_ex,
                "std": proposed_std,
            },
        )

        # Save round snapshot
        self._save_round_snapshot(round_num, round_result)

        print(
            f"Round {round_num}: composite={proposed_composite:.4f}, accepted={accepted}"
        )

        return round_result

    def _eval_result_to_dict(self, result: EvalResult) -> Dict[str, Any]:
        """Convert EvalResult to dict for JSON serialization."""
        return {
            "prompt": result.prompt,
            "expected": result.expected,
            "actual": result.actual,
            "category": result.category,
            "score": result.score,
            "matched": result.matched,
            "stochastic_mean": result.stochastic_mean,
            "stochastic_std": result.stochastic_std,
            "runs": result.runs,
        }

    def _compute_category_scores(self, results: List[EvalResult]) -> Dict[str, float]:
        """Compute per-category scores."""
        scores: Dict[str, List[float]] = {
            "rejection": [],
            "delegation": [],
            "compliance": [],
            "accuracy": [],
        }

        for r in results:
            if r.category in scores:
                score = r.stochastic_mean if r.stochastic_mean is not None else r.score
                scores[r.category].append(score)

        return {
            cat: sum(vals) / len(vals) if vals else 0.0 for cat, vals in scores.items()
        }

    def check_convergence(self) -> Tuple[bool, str]:
        """
        Check if optimization has converged.

        Returns:
            Tuple of (converged, reason).
        """
        if len(self.rounds) < self.args.consecutive_no_improvement_cap:
            return False, "insufficient_rounds"

        recent = self.rounds[-self.args.consecutive_no_improvement_cap :]
        deltas = [
            r.composite_score
            - (self.rounds[i - 1].composite_score if i > 0 else self.baseline_score)
            for i, r in enumerate(recent)
        ]

        if all(d < self.args.score_threshold for d in deltas):
            return (
                True,
                f"no_improvement_{self.args.consecutive_no_improvement_cap}_rounds",
            )

        return False, "still_improving"

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emit an event to the event stream.

        Args:
            event_type: Type of event (round_start, round_end, eval_prompt, etc.).
            data: Event data payload.
        """
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        # If event_url is a file path, write there
        if self.event_url and not self.event_url.startswith("http"):
            try:
                event_path = Path(self.event_url)
                with open(event_path, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                print(f"Event emission error: {e}", file=sys.stderr)
        # Otherwise, just print to stdout if verbose
        elif self.args.verbose:
            print(f"[EVENT] {event_type}: {json.dumps(data)[:100]}")

    def _save_round_snapshot(self, round_num: int, result: RoundResult) -> None:
        """Save per-round snapshot to JSON file."""
        snapshot = {
            "round": round_num,
            "prompt": self.current_prompt,
            "composite_score": result.composite_score,
            "standalone_score": result.standalone_score,
            "composite_score_ex": result.composite_score_ex,
            "overall_std": result.overall_std,
            "accepted": result.accepted,
            "confusion_matrix": result.confusion_matrix,
            "rejection_recall": result.rejection_recall,
            "false_acceptance_rate": result.false_acceptance_rate,
            "eval_results": result.eval_results,
        }

        snapshot_path = self.results_dir / f"round_{round_num}.json"
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f, indent=2)

    def _save_optimization_log(self) -> None:
        """Save optimization log to JSON."""
        best_round = (
            max(range(len(self.rounds)), key=lambda i: self.rounds[i].composite_score)
            if self.rounds
            else 0
        )

        log = {
            "agent": self.agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "max_rounds": self.args.max_rounds,
            "score_threshold": self.args.score_threshold,
            "composite_weight": self.args.composite_weight,
            "baseline_score": self.baseline_score,
            "final_score": self.rounds[-1].composite_score
            if self.rounds
            else self.baseline_score,
            "rounds_run": len(self.rounds),
            "converged": len(self.rounds) >= self.args.max_rounds
            or (self.rounds and not self.rounds[-1].accepted),
            "convergence_reason": self.check_convergence()[1]
            if self.rounds
            else "not_started",
            "best_round": best_round + 1,  # 1-indexed
            "rounds": [
                {
                    "round": r.round_number,
                    "composite_score": r.composite_score,
                    "standalone_score": r.standalone_score,
                    "composite_score_ex": r.composite_score_ex,
                    "accepted": r.accepted,
                    "category_scores": r.category_scores,
                    "tools_used": r.tools_used,
                    "subagent_selected": r.subagent_selected,
                    "prompt_length": r.prompt_length,
                }
                for r in self.rounds
            ],
        }

        log_path = self.results_dir / "optimization_log.json"
        with open(log_path, "w") as f:
            json.dump(log, f, indent=2)

    def _save_results_tsv(self) -> None:
        """Save results as TSV file."""
        tsv_path = self.results_dir / "results.tsv"

        header = [
            "round",
            "prompt_hash",
            "metric_composite",
            "metric_standalone",
            "metric_compliance",
            "metric_rejection",
            "metric_accuracy",
            "metric_delegation",
            "status",
            "description",
        ]

        rows = [header]
        for r in self.rounds:
            prompt_hash = hashlib.sha1(r.prompt_preview.encode()).hexdigest()[:8]
            status = "keep" if r.accepted else "discard"
            description = f"Round {r.round_number}: composite={r.composite_score:.2f}"

            row = [
                str(r.round_number),
                prompt_hash,
                f"{r.composite_score:.4f}",
                f"{r.standalone_score:.4f}",
                f"{r.category_scores.get('compliance', 0):.4f}",
                f"{r.category_scores.get('rejection', 0):.4f}",
                f"{r.category_scores.get('accuracy', 0):.4f}",
                f"{r.category_scores.get('delegation', 0):.4f}",
                status,
                description,
            ]
            rows.append(row)

        with open(tsv_path, "w") as f:
            f.write("\n".join("\t".join(row) for row in rows) + "\n")

    def run(self) -> int:
        """
        Main loop entry point.

        Returns:
            Exit code (0=completed, 4=baseline zero).
        """
        print(f"AutoResearch optimization starting for agent '{self.agent_name}'")
        print(
            f"Max rounds: {self.args.max_rounds}, Score threshold: {self.args.score_threshold}"
        )

        # Check agent file exists
        if not self.agent_file.exists():
            print(f"Error: Agent file not found: {self.agent_file}", file=sys.stderr)
            return 1

        # Check opencode binary exists
        try:
            subprocess.run(["opencode", "--version"], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("Error: opencode binary not found", file=sys.stderr)
            return 3

        # Check eval prompts exist
        eval_prompts = self.load_eval_prompts()
        if not eval_prompts and not self.args.dry_run:
            print(
                f"Warning: No eval prompts found in {self.eval_prompts_dir}",
                file=sys.stderr,
            )
            # Don't fail - eval prompts might be generated later

        # Compute baseline
        try:
            self.baseline_score = self.compute_baseline()
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 4

        if self.args.dry_run:
            print("Dry run complete. Exiting.")
            return 0

        # Main loop
        for round_num in range(1, self.args.max_rounds + 1):
            # Run round
            result = self.run_round(round_num)

            # Check convergence
            converged, reason = self.check_convergence()
            if converged:
                print(f"Converged: {reason}")
                break

        # Save results
        self._save_optimization_log()
        self._save_results_tsv()

        print(f"\nOptimization complete. Results saved to {self.results_dir}")

        return 0


def main():
    """Main entry point."""
    from .config import parse_args

    args = parse_args()
    driver = OptimizationDriver(args)
    exit_code = driver.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
