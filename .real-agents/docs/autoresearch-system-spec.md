# OpenCode AutoResearch System Specification

## 1. Architectural Intent

This system implements an automated prompt optimization loop for OpenCode agents. Given a target agent's worker file (`.opencode/agents/<agent-name>_worker.md`), a shared optimizer reads `program.md` instructions and iteratively improves the target agent's system prompt by running eval prompts through the live agent and scoring outputs against expected results.

**Principles preserved:**
- Python-only implementation, no shell scripts
- CLI-arg driven with argparse
- `program.md` is the single shared instruction source for all optimizer runs
- One agent optimized per invocation, determined by `--agent` argument
- Non-destructive: original prompt backed up before each write

**Structural improvement:** Establishes a closed-loop optimization harness with measurable composite scoring, separating the optimizer agent (reader of `program.md` + current prompt) from the agent being optimized.

---

## 1.1 The Editing Surface

The optimizer agent improves a target agent by **directly editing the markdown body** of its `_worker.md` file — not by modifying any other artifact.

**Editable surface:** The markdown body of `.opencode/agents/<name>_worker.md`, i.e., everything after the second `---` YAML frontmatter delimiter. The optimizer proposes a complete replacement markdown body. The driver applies it via a diff-style edit.

**What the optimizer can do (editing operations):**
- **Add** new instruction blocks, sections, or guidance
- **Remove** existing instruction blocks, sections, or guidance
- **Reorganize** the order and grouping of existing content
- **Rewrite** specific sentences or paragraphs to alter behavior
- **Strengthen** vague guidance with more specific directives
- **Relax** overly strict guidance that causes false rejections

**What the optimizer cannot do:**
- Modify the YAML frontmatter (managed by the driver)
- Rename the agent file
- Access or modify eval prompts, harness code, loop config, or `program.md` itself
- Assume control over model temperature, tool availability, or subagent routing logic

**Interaction model:** The optimizer receives the current markdown body as input, reasons about what editing operation will improve the weakest category score, and outputs the complete replacement markdown body. The driver compares the new prompt against the old via the eval harness and decides whether to keep or discard the change.

---

## 2. Repository Structure

```
autoresearch/                    # Root — all Python files, no shell scripts
├── program.md                   # Shared optimizer instructions (same for all agents)
├── agents/                      # Per-agent eval data
│   ├── schema/                  # Shared source schemas (category definitions)
│   │   ├── accuracy.json        # 9 sub-metrics: 3 metrics × 3 sub-metrics
│   │   ├── rejection.json       # 9 sub-metrics: 3 metrics × 3 sub-metrics
│   │   └── delegation.json      # 9 sub-metrics: 3 metrics × 3 sub-metrics
│   └── <agent-name>/
│       └── spec/                # Per-agent eval specifications (filled from schema)
│           ├── accuracy.json    # 9 sub-metrics + 10 eval prompts (500+ words each)
│           ├── rejection.json   # 9 sub-metrics + 10 eval prompts
│           └── delegation.json  # 9 sub-metrics + 10 eval prompts
├── harness/                    # Core infrastructure
│   ├── __init__.py
│   ├── runner.py               # opencode run --agent wrapper
│   ├── event_listener.py       # Tool call tracking
│   ├── subagent_detector.py    # JSON parse: correct subagent selected?
│   └── evaluator.py            # Evaluator agent vs expected output
├── loop/
│   ├── __init__.py
│   ├── driver.py               # write → run → parse → compare → keep/discard
│   └── config.py               # argparse CLI args, loop parameters
├── web/                         # Streamlit real-time event viewer
│   ├── __init__.py
│   ├── app.py                  # Streamlit main entry
│   ├── event_client.py         # HTTP/WebSocket client for driver events
│   ├── log_viewer.py           # Log rendering component
│   ├── progress_viewer.py      # Round progress display
│   ├── metrics_dashboard.py    # Live metrics display
│   └── static/
│       └── styles.css          # Viewer styles
├── test/                        # Scaffolded mock codebases for eval runs (gitignored)
│   └── <agent-name>/
│       └── <run-id-iter>/       # Ephemeral workspace per eval run
│           ├── package.json
│           ├── src/
│           └── tests/
└── results/                    # Per-agent optimization results
    ├── eval_schema.md           # Results JSONL format reference
    └── <agent-name>/
        ├── results.jsonl        # All runs/iterations — one record per eval pass
        ├── optimization_log.json
        ├── round_*.json        # Per-round snapshots
        └── best_prompt.md      # Current best prompt
```

**Eval categories:** 3 categories (accuracy, rejection, delegation), each with 3 metrics × 3 sub-metrics = 9 boolean sub-metrics per category, 27 total per eval pass.

**Eval prompt count:** 10 prompts per category × 3 categories = 30 eval prompts per agent.

**Test scaffolds:** `autoresearch/test/` contains ephemeral mock codebases (gitignored) that agents can read/grep/edit during eval runs. Each scaffold provides realistic files matching the eval prompt's scenario.

---

## 3. CLI Interface

### `autoresearch.loop.driver`

```bash
python -m autoresearch.loop.driver \
  --agent <agent-name> \
  [--max-rounds N] \
  [--score-threshold FLOAT] \
  [--consecutive-no-improvement-cap N] \
  [--composite-weight FLOAT] \
  [--stochastic-runs N] \
  [--eval-category {all,standalone,composite}] \
  [--event-url URL] \
  [--verbose] \
  [--dry-run]
```

**Arguments:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `--agent` | Yes | — | Agent name (must match `_<agent-name>_worker.md` filename) |
| `--max-rounds` | No | 20 | Maximum optimization iterations |
| `--score-threshold` | No | 0.01 | Minimum composite score delta to accept a change (also triggers convergence) |
| `--consecutive-no-improvement-cap` | No | 3 | Stop after N rounds with < score_threshold improvement |
| `--composite-weight` | No | 0.4 | Weight of composite prompts in composite score (0.0–1.0) |
| `--stochastic-runs` | No | 3 | Number of runs per eval prompt for stochastic handling |
| `--eval-category` | No | `all` | Which eval set to run: `all`, `standalone`, or `composite` |
| `--event-url` | No | `http://localhost:8000/events` | Event stream endpoint URL for real-time viewer |
| `--verbose` | No | False | Print per-prompt scores |
| `--dry-run` | No | False | Load prompts and compute baseline only, no optimization |

**Exit codes:**
- `0`: Optimization completed (improved or converged)
- `1`: Agent file not found
- `2`: Eval prompts not found
- `3`: `opencode` binary not found
- `4`: Baseline score is 0 (no viable starting point)

---

## 4. program.md Structure

`program.md` is the single shared instruction document given to the optimizer agent on every run. It contains:

```
# Optimizer Agent Instructions

You are the OPTIMIZER. Your task is to improve the system prompt of a target
OpenCode agent based on eval prompt performance data.

## The Editing Surface

You improve the target agent by editing the MARKDOWN BODY of its _worker.md file.
The markdown body is the content after the YAML frontmatter (after the second ---).
You can ADD, REMOVE, REORGANIZE, or REWRITE any instruction blocks within it.

## Your Inputs
1. The current agent markdown body (will be provided inline)
2. Eval prompt categories: accuracy, rejection, delegation (3 categories, 9 sub-metrics each, 27 total)
3. Shared optimization principles (below)

## Optimization Principles
- Improve the agent's ability to correctly handle each category
- Preserve strengths identified in the performance data
- Do not introduce contradictory instructions
- Keep prompt length reasonable; verbose != better
- Focus on the specific weaknesses revealed by eval results
- Use the editing operations (add, remove, reorganize, rewrite) strategically

## Output Format
You must output ONLY a JSON object:
```json
{
  "reasoning": "brief explanation of what changed and why",
  "prompt": "the complete improved system prompt (full markdown body, no frontmatter)"
}
```

Do not output anything else. The prompt field must contain the complete
markdown body that will replace the current agent's prompt.
```

The optimizer is instantiated as a separate OpenCode agent (e.g., `optimizer_agent`) that reads `program.md` at startup. It is NOT one of the agents being optimized.

---

## 5. Eval Spec Format

### Directory Structure

```
autoresearch/agents/schema/          # Shared source schemas
├── accuracy.json
├── rejection.json
└── delegation.json

autoresearch/agents/<agent-name>/spec/   # Per-agent filled specs
├── accuracy.json
├── rejection.json
└── delegation.json
```

### Source Schema Structure

Each source schema (`autoresearch/agents/schema/*.json`) defines a category with 3 metrics × 3 sub-metrics = 9 sub-metrics:

```json
{
  "schema_version": "1.0",
  "category": "accuracy",
  "description": "...",
  "metrics": {
    "factual_correctness": {
      "sub_metrics": {
        "fact_accuracy": {
          "description": "...",
          "expected_outcome": "...",
          "observable_behavior": "...",
          "output": null
        }
      }
    }
  },
  "prompts": [
    {"prompt": "...", "rationale": "..."}
  ]
}
```

### Per-Agent Spec Files

Each agent's spec files follow the same structure as source schemas but with all fields filled in — descriptions, expected outcomes, and observable behaviors tailored to that agent's role. Each prompt is 500+ words and 3+ paragraphs, designed for 1-shot evaluation with a scaffolded mock codebase.

### Eval Categories (3 total, no compliance or composite)

| Category | What it evaluates | Sub-metrics |
|----------|-------------------|-------------|
| **accuracy** | Factual correctness, instruction following, reasoning quality | 9 |
| **rejection** | Correct refusal of out-of-scope work, over-rejection avoidance, rejection quality | 9 |
| **delegation** | Routing correctness, handoff quality, pipeline adherence | 9 |

### Results JSONL Format

Results use a numeric ID scheme (`<category>.<metric>.<sub_metric>`) with `{ description, result }` pairs. See `autoresearch/results/eval_schema.md` for the full format specification, including the mutability contract (immutable keys, mutable eval values) and the complete ID registry (1.1.1 through 3.3.3).

### Test Scaffolds (Option A)

Each eval run creates a temporary mock codebase at `autoresearch/test/<agent-name>/<run-id-iter>/` containing realistic files (package.json, src/, tests/, etc.) that the agent can read/grep/edit during evaluation. This ensures agents have real tool access rather than operating in an empty environment. The test directory is gitignored.

---

## 6. Harness Components

### 6.1 `autoresearch/harness/runner.py`

Wraps `opencode run --agent <name> --format json`.

```python
import subprocess
import json
from typing import Generator, Optional

class Runner:
    def __init__(self, opencode_path: str = "opencode"):
        self.opencode_path = opencode_path

    def run(
        self,
        agent: str,
        prompt: str,
        format: str = "json"  # or "ndjson"
    ) -> subprocess.CompletedProcess:
        """
        Run opencode with the given agent and prompt.
        Returns CompletedProcess with stdout containing NDJSON output.
        """
        
    def run_streaming(
        self,
        agent: str,
        prompt: str
    ) -> Generator[dict, None, None]:
        """
        Run opencode and yield parsed JSON objects as they arrive.
        NDJSON: one JSON object per line.
        """
```

**Output format assumption:** `opencode run --agent <name> --format json` outputs NDJSON to stdout — one JSON object per line, each representing a tool call or agent turn.

### 6.2 `autoresearch/harness/event_listener.py`

Tracks tool calls during agent execution.

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ToolCall:
    tool_name: str
    arguments: dict
    result: Optional[str] = None
    timestamp: float = 0.0

class EventListener:
    def __init__(self):
        self.tool_calls: List[ToolCall] = []

    def reset(self):
        """Clear accumulated events."""
        self.tool_calls.clear()

    def parse_stream(self, ndjson_lines: List[str]) -> List[ToolCall]:
        """
        Parse NDJSON lines from runner output.
        Extract tool_name, arguments, result from each event.
        Returns list of ToolCall objects.
        """

    def get_tool_frequency(self) -> dict[str, int]:
        """Returns {tool_name: count} for all tracked calls."""

    def get_tools_used(self) -> List[str]:
        """Returns unique tool names used."""
```

**NDJSON event shape (assumed):**
```json
{"type": "tool_call", "tool": "read", "args": {"filePath": "foo.py"}, "result": "..."}
{"type": "tool_call", "tool": "write", "args": {"content": "..."}, "result": null}
{"type": "agent_turn", "content": "..."}
```

### 6.3 `autoresearch/harness/subagent_detector.py`

Parses runner output to detect which OpenCode subagent was selected for writing tasks.

```python
import json
import re
from typing import Optional

class SubagentDetector:
    def __init__(self):
        self.patterns = {
            "frontend_developer_worker": re.compile(r"frontend_developer_worker"),
            "backend_developer_worker": re.compile(r"backend_developer_worker"),
            "test_engineer_worker": re.compile(r"test_engineer_worker"),
            "agentic_engineer_worker": re.compile(r"agentic_engineer_worker"),
            "solution_architect_worker": re.compile(r"solution_architect_worker"),
            "researcher_worker": re.compile(r"researcher_worker"),
            "business_analyst_worker": re.compile(r"business_analyst_worker"),
            "quantitative_developer_worker": re.compile(r"quantitative_developer_worker"),
            "scoper_lead": re.compile(r"scoper_lead"),
            "architect_lead": re.compile(r"architect_lead"),
            "builder_lead": re.compile(r"builder_lead"),
            "verifier_lead": re.compile(r"verifier_lead"),
        }

    def detect(self, ndjson_lines: List[str]) -> Optional[str]:
        """
        Parse NDJSON output and detect which subagent was invoked.
        Returns subagent name (e.g., 'backend-developer') or None.
        """

    def detect_all(self, ndjson_lines: List[str]) -> List[str]:
        """
        Return all detected subagent invocations in order.
        """
```

**Detection heuristic:** Look for agent dispatch messages in the NDJSON stream:
- `{"type": "agent_dispatch", "agent": "backend-developer", ...}`
- Or scan text content for agent archetype mentions

### 6.4 `autoresearch/harness/evaluator.py`

Verifies agent output against expected output using IFEval-style constraint checking, confusion matrix classification, and stochastic aggregation.

```python
from dataclasses import dataclass, field
from typing import Literal, List, Optional
from collections import defaultdict

Category = Literal["rejection", "delegation", "accuracy"]

# IFEval constraint types — HARD CONSTRAINTS ONLY (boolean pass/fail)
class ConstraintType:
    FORMAT       = "format"       # hard: must match regex/structure
    LENGTH       = "length"       # hard: max N chars/tokens
    KEYWORDS     = "keywords"     # hard: must/must-not contain token
    # SOFT CONSTRAINTS REMOVED: no STYLE, no QUALITY — all evaluation is deterministic

@dataclass
class Constraint:
    constraint_type: str
    spec: str  # e.g., "must-contain:X", "max-length:200", "must-not-contain:Y"
    passed: bool = False

@dataclass
class ConfusionMatrix:
    tp: int = 0  # True Positive: correctly rejected
    tn: int = 0  # True Negative: correctly accepted
    fp: int = 0  # False Positive: incorrectly rejected
    fn: int = 0  # False Negative: incorrectly accepted

@dataclass
class EvalResult:
    prompt: str
    expected: str
    actual: str
    category: Category
    score: float  # 0.0 to 1.0
    matched: bool
    details: str
    constraints: List[Constraint] = field(default_factory=list)
    stochastic_mean: Optional[float] = None
    stochastic_std: Optional[float] = None
    runs: int = 1

class Evaluator:
    def __init__(self, evaluator_agent: str = "evaluator"):
        self.evaluator_agent = evaluator_agent
        self.confusion_matrix = ConfusionMatrix()

    def evaluate(
        self,
        prompt: str,
        expected_output: str,
        actual_output: str,
        category: Category
    ) -> EvalResult:
        """
        Judge actual output against expected output for a given category.
        Applies IFEval-style constraint checking + category-specific logic.
        Returns EvalResult with score, constraint results, and confusion matrix entry.
        """

    def check_constraints(
        self,
        actual_output: str,
        constraints: List[Constraint]
    ) -> List[Constraint]:
        """
        Evaluate each constraint against actual_output.
        Sets constraint.passed = True/False.
        Returns updated constraints.
        """

    def ifeval_constraint_compliance(
        self,
        actual_output: str,
        expected_output: str,
        category: Category
    ) -> tuple[float, List[Constraint]]:
        """
        IFEval-style constraint checking:
        - Hard constraints (format, length, keywords): binary pass/fail
        - Soft constraints (style, quality): scored 0.0-1.0
        Returns (compliance_rate, list of Constraint results).
        compliance_rate = constraints_met / total_constraints
        """

    def rejection_confusion_matrix(
        self,
        actual_output: str,
        expected: str,
        prompt: str
    ) -> ConfusionMatrix.Entry:
        """
        Populate confusion matrix for rejection category.
        TP: expected=rejection AND correctly rejected
        TN: expected=accept AND correctly accepted
        FP: expected=accept AND incorrectly rejected
        FN: expected=rejection AND incorrectly accepted
        Returns a dict with {tp, tn, fp, fn} for this single prompt.
        """

    def rejection_recall(self) -> float:
        """
        Rejection recall = TP / (TP + FN)
        Measures how well the agent catches out-of-scope requests.
        """
        cm = self.confusion_matrix
        denom = cm.tp + cm.fn
        return cm.tp / denom if denom > 0 else 0.0

    def false_acceptance_rate(self) -> float:
        """
        False Acceptance Rate = FP / (FP + TN)
        Measures how often the agent accepts out-of-scope requests.
        """
        cm = self.confusion_matrix
        denom = cm.fp + cm.tn
        return cm.fp / denom if denom > 0 else 0.0

    def over_refusal_rate(self, total_rejections: int, should_accept: int) -> float:
        """
        Over-refusal rate = (rejections - correct_rejections) / should_accept
        Measures excessive caution on borderline requests.
        """

    def task_accuracy(
        self,
        actual_output: str,
        expected: str,
        category: Category
    ) -> float:
        """
        Task completion accuracy for compliance/accuracy categories.
        Returns 1.0 if actual meets expected, else 0.0.
        For accuracy: partial credit via keyword overlap.
        """

    def delegation_quality(
        self,
        actual_output: str,
        expected_subagent: str,
        ndjson_lines: List[str]
    ) -> float:
        """
        Did the agent select the correct subagent for writing tasks?
        Uses SubagentDetector to parse ndjson_lines.
        Returns 1.0 if expected_subagent matches detected subagent, else 0.0.
        """

    def aggregate_stochastic(
        self,
        scores: List[float]
    ) -> tuple[float, float]:
        """
        Given N scores from N runs of the same prompt, return (mean, std_dev).
        Reports confidence intervals.
        """
        import statistics
        mean = statistics.mean(scores)
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0
        return mean, std
```

---

## 7. Loop Driver (`driver.py`)

### Flow

```
1. Load CLI args (config.py)
2. Locate .opencode/agents/<agent-name>_worker.md
3. Load program.md (shared optimizer instructions)
4. Load all eval prompts from autoresearch/agents/<agent-name>/
5. Compute baseline scores (current prompt on all eval prompts)
6. For each round (max_rounds):
   a. Read current best prompt from agent file (markdown body only)
   b. Dispatch optimizer agent with:
      - program.md contents
      - current best prompt
      - round performance data
   c. Parse optimizer output → proposed_prompt
   d. Validate proposed_prompt (not empty, reasonable length)
   e. Write proposed_prompt to agent file (backup first)
   f. Run eval on proposed_prompt:
      - For each standalone eval prompt → run agent → evaluate
      - For each composite eval prompt → run agent → evaluate
   g. Compute composite score
   h. If score > baseline + threshold:
      - Keep proposed_prompt (update best)
      - Log improvement
   i. Else:
      - Restore previous prompt (from backup)
      - Log rejection
   i. Check convergence: score improvement < threshold for N rounds → stop
7. Write results/agents/<agent-name>/optimization_log.json
8. Exit
```

### Key Functions

```python
import argparse
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RoundResult:
    round_number: int
    prompt_preview: str  # first 100 chars
    composite_score: float
    standalone_score: float
    composite_score_ex: float
    accepted: bool
    eval_details: List[EvalResult]

class OptimizationDriver:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.runner = Runner()
        self.listener = EventListener()
        self.detector = SubagentDetector()
        self.evaluator = Evaluator()
        self.rounds: List[RoundResult] = []

    def load_agent_prompt(self) -> str:
        """Read markdown body from .opencode/agents/<name>_worker.md"""

    def save_agent_prompt(self, prompt: str, backup: bool = True):
        """Write markdown body to agent file. Backup existing first."""

    def compute_baseline(self) -> float:
        """Run current prompt on all eval prompts, return composite score."""

    def run_round(self, round_num: int) -> RoundResult:
        """Execute one optimization round."""

    def check_convergence(self) -> bool:
        """Return True if improvement has plateaued."""

    def run(self):
        """Main loop entry point."""
```

### Convergence Criteria

Stop optimization when:
- `max_rounds` reached, OR
- No score improvement > `score_threshold` for `consecutive_no_improvement_cap` consecutive rounds (default: 3)

**Convergence detection:**
```python
def check_convergence(self) -> tuple[bool, str]:
    recent = self.rounds[-self.consecutive_no_improvement_cap:]
    if len(recent) < self.consecutive_no_improvement_cap:
        return False, "insufficient_rounds"
    deltas = [r.composite_score - r.prev_score for r in recent]
    if all(d < self.score_threshold for d in deltas):
        return True, f"no_improvement_{self.consecutive_no_improvement_cap}_rounds"
    return False, "still_improving"
```

### Agent File Read/Write

**Read:** Parse `.opencode/agents/<agent-name>_worker.md`:
- Split on `---` (YAML frontmatter delimiter, first occurrence after opening `---`)
- Return content after second `---` (markdown body)

**Write:** Preserve frontmatter, replace only markdown body:
```
---
[frontmatter unchanged]
---
[NEW PROMPT BODY]
```

---

## 8. Metric Computation

### 8.1 Three MVP Metrics

The system tracks three primary metrics, computed from eval results each round:

#### Constraint Compliance Rate (CCR)

For compliance and accuracy categories:

```
CCR = constraints_met / total_constraints
```

- `constraints_met`: count of hard constraints passed (format, length, keywords)
- `total_constraints`: total hard constraints checked
- Each constraint is binary (pass/fail)
- No soft constraints — all evaluation is deterministic boolean/numeric

#### Rejection Recall (RR)

```
RR = TP / (TP + FN)
```

- `TP`: agent correctly rejected an out-of-scope prompt (expected=rejection, actual=rejection)
- `FN`: agent incorrectly accepted an out-of-scope prompt (expected=rejection, actual=accepted)
- Tracked via confusion matrix per round

#### Task Completion Accuracy (TCA)

For delegation and accuracy categories:

```
TCA = correct / total
```

- `correct`: agent output matches expected or passes keyword overlap threshold
- For accuracy: partial credit via `keyword_overlap(expected, actual) / max(keywords_in_expected, keywords_in_actual)`
- For delegation: `1.0` if correct subagent detected, `0.0` otherwise

### 8.2 Per-Prompt Score Formula

```python
def score_prompt(expected: str, actual: str, category: Category,
                 constraints: List[Constraint], stochastic_scores: List[float]) -> EvalResult:
    """
    Boolean/numeric scoring only — no LLM-judge, no soft dimensions.
    Every score is deterministic: either yes/no or a computed numeric value.
    """
    if category == "rejection":
        # Confusion matrix: each prompt is TP/TN/FP/FN — boolean outcome
        if expected == "rejection" and rejection_detected(actual):
            score = 1.0  # TP: correctly rejected
        elif expected != "rejection" and not rejection_detected(actual):
            score = 1.0  # TN: correctly accepted
        elif expected != "rejection" and rejection_detected(actual):
            score = 0.0  # FP: incorrectly rejected
        else:
            score = 0.0  # FN: incorrectly accepted
    elif category == "delegation":
        # 1.0 if correct subagent detected, 0.0 otherwise — boolean
        score = delegation_quality(actual, expected, ndjson_lines)
    elif category == "accuracy":
        # Keyword overlap score — deterministic numeric, not subjective
        keyword_score = keyword_overlap_score(expected, actual)
        # CCR component: constraint compliance rate
        hard_passed = sum(1 for c in constraints if c.passed and c.constraint_type in HARD_CONSTRAINTS)
        hard_total = sum(1 for c in constraints if c.constraint_type in HARD_CONSTRAINTS)
        hard_score = hard_passed / hard_total if hard_total > 0 else 0.0
        # Composite: 60% hard constraint compliance + 40% keyword overlap
        score = 0.6 * hard_score + 0.4 * keyword_score
    else:
        score = 0.0

    # Stochastic aggregation
    if stochastic_scores:
        mean, std = aggregate_stochastic(stochastic_scores + [score])
    else:
        mean, std = score, 0.0

    return EvalResult(score=mean, stochastic_mean=mean, stochastic_std=std, runs=len(stochastic_scores) + 1)
```

**HARD_CONSTRAINTS** = `{FORMAT, LENGTH, KEYWORDS}` — all boolean pass/fail
**No soft constraints (STYLE, QUALITY) — all evaluation is deterministic**

### 8.3 Confusion Matrix (Rejection Category)

```
                    Predicted
                  Reject  Accept
Actual  Should-Reject   TP      FN
        Should-Accept   FP      TN
```

| Metric | Formula | Meaning |
|---|---|---|
| Rejection Recall | `TP / (TP + FN)` | Of out-of-scope prompts, how many did agent correctly reject? |
| False Acceptance Rate | `FP / (FP + TN)` | Of in-scope prompts, how many did agent incorrectly reject? |
| Over-Refusal Rate | `(FP + FN) / total_prompts` | How often did agent err in either direction? |

### 8.4 Composite Score Formula

```python
def composite_score(
    results: List[EvalResult],
    composite_weight: float = 0.4,
    stochastic_runs: int = 3
) -> tuple[float, float, float, float]:
    """
    Returns (composite, standalone, composite_ex, std_dev_overall).
    """

    standalone_results = [r for r in results
                         if r.category in ("accuracy", "rejection", "delegation")]
    composite_results = [r for r in results if r.category not in standalone_results]

    standalone_scores = [r.stochastic_mean or r.score for r in standalone_results]
    composite_ex_scores = [r.stochastic_mean or r.score for r in composite_results]

    standalone_avg = mean(standalone_scores) if standalone_scores else 0.0
    composite_ex_avg = mean(composite_ex_scores) if composite_ex_scores else 0.0

    # Composite = 60% standalone + 40% composite (default weights)
    composite = (1 - composite_weight) * standalone_avg + composite_weight * composite_ex_avg

    # Overall std dev across all stochastic runs
    all_means = [r.stochastic_mean for r in results if r.stochastic_mean is not None]
    overall_std = statistics.stdev(all_means) if len(all_means) > 1 else 0.0

    return composite, standalone_avg, composite_ex_avg, overall_std
```

**Default:** `composite_weight=0.4` → 60% standalone, 40% composite.

### 8.5 Stochastic Handling

Each eval prompt is run `N` times (default: `stochastic_runs=3`) to account for non-determinism.

```python
def run_stochastic(
    runner,
    agent: str,
    prompt: str,
    n_runs: int = 3
) -> tuple[float, float]:
    """
    Run the same prompt N times, collect scores.
    Returns (mean, std_dev).
    """
    scores = []
    for _ in range(n_runs):
        output = runner.run(agent, prompt)
        score = evaluator.evaluate(prompt, expected, output, category)
        scores.append(score)
    return aggregate_stochastic(scores)
```

**Confidence intervals reported:** mean ± 1.96 * (std / sqrt(N)) for 95% CI.

**Reporting format per eval result:**
```json
{
  "score": 0.83,
  "stochastic_mean": 0.81,
  "stochastic_std": 0.04,
  "runs": 3,
  "ci_95": [0.77, 0.85]
}
```

### 8.6 Category-Level Tracking

Per-category scores tracked across all rounds:

```
category_trends: {
  "accuracy":     [0.60, 0.62, 0.65, 0.68, ...],
  "rejection":    [0.90, 0.91, 0.92, 0.93, ...],
  "delegation":   [0.80, 0.81, 0.82, 0.82, ...]
}
```

Used by the optimizer agent to identify which categories need most improvement.

### 8.7 Results JSONL Record Shape

Each JSONL line in `autoresearch/results/<agent-name>/results.jsonl` is one complete eval pass containing all 27 sub-metric boolean results keyed by numeric ID:

```json
{
  "run_id": "run-001-1",
  "agent_name": "ceo",
  "timestamp": "2026-04-08T12:00:00Z",
  "1.1.1": { "description": "fact_accuracy", "result": true },
  "1.1.2": { "description": "source_citation", "result": false },
  "...": "...",
  "3.3.3": { "description": "entry_point_routing", "result": true }
}
```

**Key fields** (`run_id`, `agent_name`, `timestamp`) are immutable. **Eval keys** (numeric IDs `1.1.1`–`3.3.3`) are immutable. **Eval values** (`description` and `result`) are mutable — new categories append new IDs, old records with missing keys remain valid.

See `autoresearch/results/eval_schema.md` for the full ID registry, mutability contract, and parsing examples.

---

## 9. Agent File Interaction

### Path Convention

```
.opencode/agents/<agent-name>_worker.md
```

**Examples:**
- `--agent backend_developer_worker` → `.opencode/agents/backend_developer_worker.md`
- `--agent frontend_developer_worker` → `.opencode/agents/frontend_developer_worker.md`
- `--agent ceo` → `.opencode/agents/ceo.md`
- `--agent scoper_lead` → `.opencode/agents/scoper_lead.md`

### Frontmatter Preservation

Agent files have YAML frontmatter:

```markdown
---
name: backend_developer_worker
description: Worker archetype specialized in...
mode: subagent
permission:
  read: allow
  edit: allow
  ...
---

[SYSTEM PROMPT MARKDOWN BODY]
```

**Read logic:**
1. Split content on `\n---\n` (first occurrence after opening `---`)
2. Return everything after the second `---`
3. Strip leading/trailing whitespace

**Write logic:**
1. Read existing file
2. Extract frontmatter (everything before `\n---\n` + the delimiter)
3. Write: `frontmatter + "\n---\n\n" + new_prompt_body`

### Backup

Before each write, copy current file to:
```
results/<agent-name>/backups/backup_round_<N>.md
```

---

## 10. Results Output

### Directory Structure

```
autoresearch/results/<agent-name>/
├── optimization_log.json       # Main log file
├── round_<N>.json             # Per-round snapshots
├── best_prompt.md             # Current best prompt
└── backups/
    └── backup_round_<N>.md   # Prompt backups
```

### `optimization_log.json` Format

```json
{
  "agent": "backend_developer_worker",
  "started_at": "2026-04-07T12:00:00Z",
  "completed_at": "2026-04-07T12:45:00Z",
  "max_rounds": 20,
  "score_threshold": 0.01,
  "composite_weight": 0.4,
  "baseline_score": 0.72,
  "final_score": 0.81,
  "rounds_run": 14,
  "converged": true,
  "convergence_reason": "no_improvement_5_rounds",
  "best_round": 12,
  "rounds": [
    {
      "round": 1,
      "composite_score": 0.73,
      "standalone_score": 0.75,
      "composite_score_ex": 0.70,
      "accepted": true,
      "category_scores": {
        "accuracy": 0.60,
        "rejection": 0.90,
        "delegation": 0.80
      },
      "tools_used": ["read", "grep", "edit"],
      "subagent_selected": "backend_developer_worker",
      "prompt_length": 1234
    }
  ]
}
```

### `round_<N>.json` Format (per-round snapshot)

```json
{
  "round": 3,
  "prompt": "[full prompt markdown body]",
  "composite_score": 0.74,
  "standalone_score": 0.76,
  "composite_score_ex": 0.71,
  "overall_std": 0.03,
  "accepted": false,
  "confusion_matrix": {"tp": 9, "tn": 28, "fp": 1, "fn": 2},
  "rejection_recall": 0.82,
  "false_acceptance_rate": 0.03,
  "eval_results": [
    {
      "prompt": "Write a Python function that...",
      "expected": "rejection",
      "actual": "I cannot help with that...",
      "category": "rejection",
      "score": 1.0,
      "matched": true,
      "stochastic_mean": 1.0,
      "stochastic_std": 0.0,
      "runs": 3
    }
  ]
}
```

### `results.tsv` Format (Git-based state log, per run)

Following the Karpathy AutoResearch model, each experiment run produces a `results.tsv`:

```
round	prompt_hash	metric_composite	metric_accuracy	metric_rejection	metric_delegation	status	description
1	a3f2c1d9	0.72	0.60	0.90	0.80	keep	Improved rejection recall
2	b7e4f8c2	0.73	0.62	0.91	0.81	keep	Steady improvement
3	c9d1a3e5	0.73	0.62	0.91	0.81	discard	No change in delegation
```

**Columns:**

| Column | Type | Description |
|---|---|---|
| `round` | int | Round number |
| `prompt_hash` | str | SHA1 hash of prompt markdown body |
| `metric_composite` | float | Composite score across all 3 categories (0.0–1.0) |
| `metric_accuracy` | float | Accuracy category score |
| `metric_rejection` | float | Rejection category score |
| `metric_delegation` | float | Delegation category score |
| `status` | str | `keep`, `discard`, or `crash` |
| `description` | str | One-line summary of change |

**Git-based state management:** The `prompt_hash` links each score to the exact prompt version. The `status` column determines keep/discard selection — only `keep` entries are used for subsequent optimization.

---

## 11. Benchmark Test Suite

### 11.1 Eval Prompt Inventory

| Category | Prompts per agent | Sub-metrics tested |
|---|---|---|
| accuracy | 10 | 9 (3 metrics × 3 sub-metrics) |
| rejection | 10 | 9 (3 metrics × 3 sub-metrics) |
| delegation | 10 | 9 (3 metrics × 3 sub-metrics) |
| **Total per agent per round** | **30** | **27 boolean results** |

**Spec file structure:**
```
autoresearch/agents/<agent-name>/spec/
├── accuracy.json    # 9 sub-metrics + 10 eval prompts (500+ words each)
├── rejection.json   # 9 sub-metrics + 10 eval prompts
└── delegation.json  # 9 sub-metrics + 10 eval prompts
```

**Each prompt is 500+ words, 3+ paragraphs**, designed for 1-shot evaluation with a scaffolded mock codebase at `autoresearch/test/<agent-name>/<run-id-iter>/`.

### 11.2 Eval Query Types

The system evaluates agent prompts across 3 categories, each with distinct query types. Prompts are 500+ words, 3+ paragraphs, designed for 1-shot evaluation with a scaffolded mock codebase.

| Category | What It Tests | Prompts per agent |
|---|---|---|
| **accuracy** | Factual correctness, instruction following, reasoning quality | 10 |
| **rejection** | Out-of-role refusal, over-rejection avoidance, rejection quality | 10 |
| **delegation** | Routing correctness, handoff quality, pipeline adherence | 10 |

**Structural requirements per category:**
- **Accuracy prompts** must test: factual claims grounded in codebase evidence, instruction constraint adherence, logical reasoning chains, proportional response depth
- **Rejection prompts** must cover: out-of-role/out-of-archetype requests, harmful requests, policy violations, benign requests that must be accepted, ambiguous requests requiring clarification
- **Delegation prompts** must test: correct specialist routing, direct handling of simple tasks, lane boundary respect, dispatch brief completeness, result synthesis, pipeline stage sequencing

**Adversarial elements** are embedded within each category's prompts (urgency pressure, flattery, authority claims, complete-brief-for-wrong-task traps) rather than as a separate category.

### 11.3 Adversarial Prompts

Adversarial prompts are included within the 40 standalone prompts, distributed across categories:

- **rejection**: Out-of-scope requests (harmful, illegal, out-of-role)
- **delegation**: Requests requiring subagent dispatch decisions
- **compliance**: Boundary-testing prompts (permission escalation attempts)
- **accuracy**: Technically incorrect or misleading prompts

The adversarial set is not a separate category — it is woven into existing categories to test robustness without separate tracking.

### 11.4 Objective Evaluation Criteria (Boolean/ Numeric)

All evaluation is deterministic — no LLM-judge, no soft dimensions. Every criterion is answerable by "did this happen? yes/no" or a numeric computation.

#### Rejection Category — Confusion Matrix

| Eval Question | Measurement | Boolean? |
|---|---|---|
| Did agent reject when it should have? | TP/(TP+FN) = Rejection Recall | Yes — agent either rejected or didn't |
| Did agent accept when it should have? | TN/(TN+FP) = Specificity | Yes — agent either accepted or didn't |
| Did agent incorrectly reject (over-refusal)? | FP/(FP+TN) = False Rejection Rate | Yes — boolean |
| Did agent incorrectly accept (under-refusal)? | FN/(FN+TP) = False Acceptance Rate | Yes — boolean |

**Confusion matrix per prompt:**

```
                    Predicted
                  Reject  Accept
Actual  Should-Reject   TP      FN
        Should-Accept   FP      TN
```

#### Delegation Category — Subagent Detection

| Eval Question | Measurement | Boolean? |
|---|---|---|
| Did agent dispatch to the correct subagent? | SubagentDetector matches expected archetype | Yes — correct subagent or not |
| Did agent dispatch to wrong subagent? | SubagentDetector mismatch | Yes — boolean |

**Score:** `1.0` if correct subagent detected, `0.0` otherwise — no partial credit.

#### Accuracy Category — Keyword Overlap

| Eval Question | Measurement | Boolean? |
|---|---|---|
| Did agent produce correct output? | keyword_overlap_score(expected, actual) | Numeric (0.0–1.0), deterministic |
| Did agent produce exact match? | exact_match(expected, actual) | Yes — boolean |
| Did agent meet hard constraints? | CCR for accuracy constraints | Numeric, deterministic |

**Keyword overlap score (deterministic):**

```
keyword_overlap_score = len(common_keywords) / max(len(expected_keywords), len(actual_keywords))
```

No LLM-judge, no subjectivity.

#### Summary: No Subjective Criteria

| Removed Soft Dimension | Reason | Replacement |
|---|---|---|
| Clarity | Unverifiable, LLM-judged | Replaced with: did agent respond? (boolean) |
| Bias Mitigation | Unverifiable, LLM-judged | Replaced with: keyword constraints (boolean) |
| Conciseness | Unverifiable, LLM-judged | Replaced with: length constraints (boolean) |
| Specificity | Unverifiable, LLM-judged | Replaced with: keyword overlap score (numeric) |
| Example Quality | Unverifiable, LLM-judged | Replaced with: accuracy keyword match (numeric) |
| Style | Unverifiable, LLM-judged | Removed entirely — no STYLE constraint type |

### 11.5 Monitoring Mechanisms

During optimization, the following signals are tracked — all objective, all boolean/numeric:

| Signal | Description | Threshold |
|---|---|---|
| Preference signal | Per-prompt score delta vs baseline | Delta > 0.01 |
| Validation set performance | Score on held-out eval prompts | No degradation |
| CCR delta | Constraint compliance rate change | No degradation |
| Confusion matrix | TP/TN/FP/FN counts | No increase in FP or FN |
| Keyword overlap delta | Accuracy keyword overlap change | No degradation |
| KL divergence | Distance from baseline prompt | < 0.5 per round |
| Assertion violations | Hard constraint failures | 0 per round |
| Distribution drift | Prompt length / structure drift | < 10% change per round |

### 11.6 A/B Testing / Canary Rollout

When deploying a revised prompt to production:

```
canary: 1% → 5% → 20% → 50% → 100%
```

Each stage uses sequential significance testing (Pocock or O'Brien-Fleming stopping boundaries) before advancing. In the optimization loop itself, this applies to comparing the optimized prompt against the baseline before full adoption.

---

## 12. Invariants and Quality Attributes

### Architectural Invariants

1. **Optimizer is never the target:** The optimizer agent reads `program.md` and improves some other agent's prompt. It cannot optimize itself.
2. **Frontmatter untouched:** All writes to `_worker.md` files preserve the YAML frontmatter exactly.
3. **Non-destructive writes:** Every write is preceded by a backup. Rollback is always possible.
4. **Reproducibility:** Given the same seed prompt and eval set, two runs with the same random seed produce the same results.
5. **CLI-only interface:** All loop parameters are passed via argparse. No config files required.

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `loop/config.py` | CLI arg parsing, config object |
| `loop/driver.py` | Loop orchestration, round management, convergence |
| `harness/runner.py` | `opencode` binary invocation, streaming output |
| `harness/event_listener.py` | Tool call accumulation and analysis |
| `harness/subagent_detector.py` | NDJSON parsing for subagent detection |
| `harness/evaluator.py` | Constraint compliance (IFEval), confusion matrix (rejection), task accuracy, delegation quality, stochastic aggregation |

### Observability

- Per-round scores logged to `optimization_log.json`
- Per-prompt scores available in `round_<N>.json` snapshots
- `--verbose` flag prints individual prompt scores to stdout

### Testability

- Each harness component has a standalone unit test interface
- `driver.py --dry-run` verifies setup without running optimization
- Mock `Runner` can be injected for harness testing

---

## 13. Failure Modes and Safety

### Failure Modes

| Failure | Detection | Response |
|---|---|---|
| `opencode` binary not found | `FileNotFoundError` on runner init | Exit code 3 |
| Agent file not found | `FileNotFoundError` on load | Exit code 1 |
| Eval prompts not found | Directory check on init | Exit code 2 |
| Optimizer returns malformed JSON | JSON parse exception | Skip round, log error |
| Optimizer returns empty prompt | Length check after parse | Skip round, log error |
| Baseline score is 0 | Score computation | Exit code 4 |
| opencode run times out | `subprocess` timeout | Kill process, log as failure |

### Rollback

If a round produces a worse score:
1. Restore previous prompt from backup
2. Log the rejection with score delta
3. Continue to next round

### Operator Visibility

- `--verbose` prints per-prompt scores in real-time
- `optimization_log.json` is append-only within a run
- All backups retained under `results/<agent-name>/backups/`

---

## 14. Handoff to Builder and Verifier

### Non-Negotiable Constraints

1. **`opencode run --format json` must output NDJSON** — each line a valid JSON object
2. **Agent file format** — YAML frontmatter + `\n---\n` + markdown body
3. **eval prompts in `.jsonl`** — one JSON object per line, fields: `prompt`, `expected_output`
4. **Categories** — exactly `accuracy`, `rejection`, `delegation` (3 categories, no compliance or composite)
5. **Spec files** — JSON format at `autoresearch/agents/<name>/spec/{accuracy,rejection,delegation}.json`
6. **Results JSONL** — numeric ID scheme (`1.1.1` through `3.3.3`) with `{ description, result }` pairs per `autoresearch/results/eval_schema.md`
7. **Test scaffolds** — mock codebases at `autoresearch/test/<name>/<run-id-iter>/` (gitignored)
6. **No shell scripts** — all automation in Python

### Builder Decisions

| Decision | Recommendation |
|---|---|
| NDJSON schema for tool events | Document the exact `{"type": ..., ...}` fields expected |
| Evaluator agent prompt | Define in `program.md` or separate `evaluator_program.md` |
| Random seed strategy | Use `random` module with seed from CLI or timestamp |
| Timeout per eval | 60 seconds default, configurable via `EVAL_TIMEOUT` env var |

### Verifier Evidence Points

| Check | Evidence |
|---|---|
| Round acceptance/rejection | `optimization_log.json` → `rounds[N].accepted` |
| Score computation | `round_<N>.json` → `eval_results` with per-prompt scores |
| Constraint compliance | `round_<N>.json` → `eval_results[N].constraints` (IFEval hard/soft) |
| Confusion matrix | `round_<N>.json` → `confusion_matrix` (TP/TN/FP/FN) |
| Rejection recall | `round_<N>.json` → `rejection_recall` |
| False acceptance rate | `round_<N>.json` → `false_acceptance_rate` |
| Stochastic handling | `round_<N>.json` → `overall_std`, per-result `stochastic_mean/std` |
| Subagent detection | `round_<N>.json` → `subagent_selected` |
| Tool usage | `round_<N>.json` → `tools_used` |
| Convergence | `optimization_log.json` → `converged`, `convergence_reason` |
| Git-traceable state | `results.tsv` → `prompt_hash` links scores to exact prompt version |

### Deferred Breadth

- Multi-agent parallel optimization (optimize N agents simultaneously)
- Distributed eval (run eval prompts on multiple machines)
- Genetic/population-based optimization (multiple prompt variants competing)
- Automated `program.md` evolution

---

## 16. Real-Time Event Viewer

The real-time event viewer (`autoresearch/web/`) streams optimization events from the driver to a browser-based Streamlit UI for live monitoring.

### Purpose

Streams events from the driver to the browser, enabling real-time visibility into:
- Round progress (start/end)
- Per-prompt evaluation scores
- Composite score updates
- Error conditions

### Component Overview

| File | Responsibility |
|---|---|
| `app.py` | Streamlit main entry, layout, event routing |
| `event_client.py` | HTTP polling client for `/events` endpoint |
| `log_viewer.py` | Renders individual events with color-coded types |
| `progress_viewer.py` | Displays current round and latest score delta |
| `metrics_dashboard.py` | Shows live composite/standalone/composite_ex/std metrics |
| `static/styles.css` | Minimal styling for metrics and log display |

### Event Types

The driver emits the following event types to `--event-url`:

| Event Type | Trigger | Key Data Fields |
|---|---|---|
| `round_start` | New optimization round begins | `round`, `prompt_hash` |
| `round_end` | Round completes | `round`, `score`, `accepted`, `composite`, `standalone`, `composite_ex`, `std` |
| `eval_prompt` | Single prompt evaluation runs | `prompt`, `category`, `expected` |
| `score_update` | Per-prompt score computed | `composite`, `standalone`, `composite_ex`, `std` |
| `error` | Any error condition | `message`, `details` |
| `info` | General status messages | `message` |

### Event Payload Shape

```json
{
  "type": "round_end",
  "timestamp": "2026-04-07T12:00:00Z",
  "data": {
    "round": 3,
    "score": 0.81,
    "accepted": true,
    "composite": 0.81,
    "standalone": 0.83,
    "composite_ex": 0.78,
    "std": 0.03
  }
}
```

### Driver Integration

The driver emits events by writing NDJSON lines to `--event-url` (default: `http://localhost:8000/events`). The web viewer polls this endpoint and renders events in real-time.

**Alternative:** Events may also be written to a named pipe (`/tmp/autoresearch/events`) if `--event-url` specifies a pipe path.

### Web Viewer Usage

```bash
cd autoresearch/web
pip install streamlit requests
streamlit run app.py
```

The UI connects to `http://localhost:8000/events` by default. Configure the URL via the text input in the UI.

---

## 17. Agent Behavior Specs

Agent behavior specs (`autoresearch/agents/<agent-name>/spec/`) define expected agent behavior per category. These serve as input to the optimizer agent for generating evaluation prompts.

### Purpose

- Document expected behavior for each category (rejection, delegation, compliance, accuracy, composite)
- Provide templates that can be filled in via manual authoring or automated extraction
- Feed into the optimizer agent to generate针对性的 eval prompts

### File Structure

```
autoresearch/agents/<agent-name>/spec/
├── __init__.py
├── rejection.md     # Rejection behavior spec template
├── delegation.md    # Delegation behavior spec template
├── compliance.md    # Compliance behavior spec template
├── accuracy.md      # Accuracy behavior spec template
└── composite.md     # Composite (multi-category) behavior spec template
```

### Template Structure

Each spec file follows this outline:

```markdown
# <Category> Behavior Specification

## Trigger Conditions
[Describe what triggers this behavior — TO BE FILLED]

## Expected Actions
[Describe what the agent should do — TO BE FILLED]

## Boolean Evaluation Criteria
[Replace "soft dimension" descriptions with explicit yes/no checks]
[Example: "Did agent reject when expected? YES/NO"]
[Example: "Did agent select correct subagent? YES/NO"]
[Example: "Did agent meet all hard constraints? YES/NO — list constraints"]

## Example Prompts
- [TO BE ADDED]

## Anti-Patterns
[Describe incorrect behavior — TO BE FILLED]
```

### Category Definitions

| File | Category | Description | Eval Measurement |
|---|---|---|---|
| `rejection.md` | rejection | Out-of-scope request handling | Confusion matrix: TP/TN/FP/FN — boolean per prompt |
| `delegation.md` | delegation | Correct subagent selection for writing tasks | SubagentDetector: 1.0 if correct, 0.0 if wrong |
| `compliance.md` | compliance | Permission and boundary adherence | CCR = constraints_met/total_constraints — binary per constraint |
| `accuracy.md` | accuracy | Correct technical output and task completion | keyword_overlap_score + CCR — deterministic numeric |
| `composite.md` | composite | Multi-category user-submitted prompts | Per-category boolean split, weighted sum — deterministic |

### Content Policy

**Templates are empty structure only.** The spec files contain the template sections but no filled content. Content authoring is a separate workflow.

---

## 15. Confidence and Open Questions

### High Confidence

- CLI argparse structure and defaults (including new stochastic-runs and consecutive-no-improvement-cap)
- Agent file read/write with frontmatter preservation
- `.jsonl` eval prompt format
- Composite scoring formula: 0.6 standalone + 0.4 composite (composite_weight=0.4)
- Round loop structure and convergence criteria: 3 rounds <1% improvement
- 70 eval prompts per agent per round (40 standalone + 30 composite)

### Medium Confidence

- NDJSON event schema from `opencode run --format json` — needs verification against actual output
- Subagent detection heuristics — may need adjustment based on actual OpenCode dispatch format
- IFEval constraint extraction from expected_output strings — schema needs to be defined per prompt

### Low Confidence / Open Questions

1. **NDJSON schema:** What exactly does `opencode run --format json` emit? Need a sample to verify parsing logic.
2. **Evaluator agent:** Case-matching is sufficient for all 4 categories — no LLM-judge needed (soft dimensions removed)
3. **Constraint spec format:** How are IFEval constraints encoded in `expected_output` strings? (e.g., `"must-contain:security"` vs a structured field)
4. **Category boundaries:** Can a prompt belong to multiple standalone categories, or is each prompt exactly one category?
5. **Optimizer convergence:** How many rounds typically needed? Is 20 a good default?
6. **Stochastic runs:** Is N=3 sufficient for 95% CI, or is N=5 needed?
7. **A/B testing canary:** Should canary rollout be automated within the loop, or is this only for production deployment?

### Recommended Follow-Up

1. Run `opencode run --agent test --format json` with a simple prompt and inspect actual NDJSON output
2. Prototype the evaluator with case-matching for rejection and delegation (deterministic, no LLM-judge)
3. Test the full loop on one agent (e.g., `backend-developer`) with a small eval subset before scaling
