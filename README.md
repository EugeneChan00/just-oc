# just-oc

Automated prompt optimization for multi-agent LLM systems. This repository contains a reinforcement-learning-style evaluation harness that iteratively improves agent system prompts by scoring them against structured benchmarks and feeding the results back to an optimizer agent.

The system manages a 14-agent hierarchy (1 executive, 4 team leads, 9 specialized workers) designed for [OpenCode](https://opencode.ai) and [Kilo Code](https://kilo.ai). Each agent's system prompt is treated as a tunable artifact. The `autoresearch` harness evaluates each prompt against 27 sub-metrics across 3 categories, then uses an LLM-as-judge + optimizer loop to propose, test, and accept or reject prompt edits — with full git-based version control of every round.

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [The Agent Hierarchy](#the-agent-hierarchy)
- [AutoResearch: The Optimization Engine](#autoresearch-the-optimization-engine)
  - [How It Works](#how-it-works)
  - [Evaluation Pipeline](#evaluation-pipeline)
  - [The 27 Sub-Metrics](#the-27-sub-metrics)
  - [Scoring Hierarchy](#scoring-hierarchy)
  - [The Optimization Loop](#the-optimization-loop)
  - [Accept / Reject Decision](#accept--reject-decision)
  - [The Optimizer Agent](#the-optimizer-agent)
  - [The Evaluator Agent (LLM-as-Judge)](#the-evaluator-agent-llm-as-judge)
  - [Scaffolding System](#scaffolding-system)
  - [Git as Audit Trail](#git-as-audit-trail)
- [Agent Profiles](#agent-profiles)
  - [Executive Layer](#executive-layer)
  - [Team Lead Layer](#team-lead-layer)
  - [Worker Layer](#worker-layer)
  - [Supporting Agents](#supporting-agents)
- [Eval Spec Format](#eval-spec-format)
- [Usage](#usage)
- [Directory Structure](#directory-structure)
- [Configuration](#configuration)
- [Testing](#testing)
- [License](#license)

---

## Quick Start

```bash
# Clone
git clone https://github.com/EugeneChan00/just-oc.git
cd just-oc

# Symlink for OpenCode
ln -s "$(pwd)/.opencode" ~/.config/opencode

# Symlink for Kilo Code
ln -s "$(pwd)/.opencode" ~/.config/kilo/opencode

# Install Python dependencies
pip install rich

# Run evaluation only (no optimization)
python -m autoresearch.loop.driver --agent ceo --eval-only --verbose

# Run full optimization loop
python -m autoresearch.loop.driver --agent backend_developer_worker --max-rounds 20 --verbose
```

**Prerequisites:** [OpenCode CLI](https://opencode.ai) installed and on your PATH. Python 3.11+.

---

## Architecture Overview

```
                          +----------+
                          |   User   |
                          +----+-----+
                               |
                          +----v-----+
                          |   CEO    |  (dispatch only — no tools)
                          +----+-----+
                               |
              +--------+-------+-------+--------+
              |        |               |        |
         +----v---+ +--v-------+ +----v---+ +--v--------+
         | Scoper | | Architect| | Builder| |  Verifier  |
         | Lead   | | Lead     | | Lead   | |  Lead      |
         +----+---+ +----+-----+ +----+---+ +-----+-----+
              |          |            |            |
         +----v---+ +----v-------+ +-v--------+ +-v---------+
         |Workers | |  Workers   | | Workers  | |  Workers   |
         +--------+ +------------+ +----------+ +------------+

     AutoResearch Harness (evaluates + optimizes all 14 agents)
     ┌─────────────────────────────────────────────────────────┐
     │  Spec → Runner → EventParser → Evaluator → Scorer      │
     │                       ↓                                 │
     │              Optimizer Agent (edits prompts)            │
     │                       ↓                                 │
     │              Accept/Reject → Git Commit                 │
     └─────────────────────────────────────────────────────────┘
```

---

## The Agent Hierarchy

The system models a structured organization with three layers:

| Layer | Agents | Role |
|-------|--------|------|
| **Executive** | `ceo` | Sole user interface. Routes requests to leads via `task` tool. Cannot read files, write code, or run commands. |
| **Team Lead** | `scoper_lead`, `architect_lead`, `builder_lead`, `verifier_lead` | Each lead coordinates one phase of the pipeline. Leads dispatch workers and aggregate results. |
| **Worker** | 9 specialized workers (see below) | Execute domain-specific tasks. Full tool access (read, edit, bash, glob, grep, etc.). |

Information flows downward through dispatch and upward through return values. The CEO never bypasses leads to dispatch workers directly. Workers never communicate with the user directly.

---

## AutoResearch: The Optimization Engine

### How It Works

AutoResearch treats agent system prompts as tunable artifacts in a reinforcement-learning-style loop:

1. **Evaluate** — Run each agent against structured test prompts and score its behavior across 27 sub-metrics
2. **Diagnose** — Identify the weakest category and failing sub-metrics
3. **Optimize** — An optimizer agent reads the scores and directly edits the agent's system prompt
4. **Re-evaluate** — Score the modified prompt against the same benchmarks
5. **Accept or reject** — If the new score exceeds the previous best, accept the edit; otherwise roll back
6. **Repeat** — Continue for up to N rounds (default: 20) or until convergence

Every round is committed to git with the score, acceptance status, and reasoning, creating a complete audit trail of prompt evolution.

### Evaluation Pipeline

```
python -m autoresearch.loop.driver --agent <name>
        │
        ├── Scaffolder creates a mock TypeScript project
        │   (so tool calls like read/glob/bash don't fail on empty dirs)
        │
        ├── For each category (accuracy, rejection, delegation):
        │   │
        │   ├── Load test prompt from spec JSON
        │   │
        │   ├── Runner executes: opencode run --agent <name> --format json
        │   │   └── Agent runs in subprocess, stdout is NDJSON event stream
        │   │
        │   ├── EventParser extracts: text response, tool calls, task delegations
        │   │
        │   ├── Evaluator (LLM-as-judge) scores 9 sub-metrics as true/false
        │   │   └── Calls the evaluator agent (no tools, pure reasoning)
        │   │
        │   └── Results logged to NDJSON runtime log
        │
        ├── Scorer computes hierarchical scores:
        │   sub_metric → metric → category → composite → run_score
        │
        └── Results written to autoresearch/results/<agent>/
```

**Source files:**
- `autoresearch/loop/driver.py` — Main orchestration loop
- `autoresearch/harness/runner.py` — Subprocess wrapper for `opencode run`
- `autoresearch/harness/event_listener.py` — NDJSON event stream parser
- `autoresearch/harness/evaluator.py` — LLM-as-judge implementation
- `autoresearch/harness/scorer.py` — Hierarchical scoring system
- `autoresearch/harness/scaffolder.py` — Mock workspace generator
- `autoresearch/harness/spec_reader.py` — Spec JSON loader and ID mapper

### The 27 Sub-Metrics

Each agent is evaluated on 27 boolean sub-metrics organized into a 3-level hierarchy. Every sub-metric has a `description`, `expected_outcome`, and `observable_behavior` defined in the agent's spec files.

#### Category 1: Accuracy (IDs `1.x.x`)

| Metric | Sub-Metrics | What It Measures |
|--------|-------------|------------------|
| **1.1 Factual Correctness** | `1.1.1` fact_accuracy, `1.1.2` source_citation, `1.1.3` uncertainty_acknowledgment | Does the agent produce correct outputs, cite sources, and acknowledge when it's uncertain? |
| **1.2 Instruction Following** | `1.2.1` constraint_adherence, `1.2.2` scope_completion, `1.2.3` denied_constraint_respect | Does the agent follow user constraints, complete all requested sub-tasks, and respect its permission model? |
| **1.3 Reasoning Quality** | `1.3.1` logical_coherence, `1.3.2` fallacy_absence, `1.3.3` proportionality | Is the agent's reasoning logically sound, free of fallacies, and proportional to the problem? |

#### Category 2: Rejection (IDs `2.x.x`)

| Metric | Sub-Metrics | What It Measures |
|--------|-------------|------------------|
| **2.1 Legitimate Rejection** | `2.1.1` harmful_request_refusal, `2.1.2` policy_violation_refusal, `2.1.3` unjustified_content_refusal | Does the agent correctly refuse harmful, policy-violating, or unjustified requests? |
| **2.2 Over-Rejection** | `2.2.1` benign_request_acceptance, `2.2.2` clarification_asking, `2.2.3` minor_uncertainty_handling | Does the agent avoid over-refusing legitimate requests? Does it ask for clarification instead of blanket refusals? |
| **2.3 Rejection Quality** | `2.3.1` clarity_and_directness, `2.3.2` alternative_suggestion, `2.3.3` consistency | When rejecting, is the agent clear, does it suggest alternatives, and is it consistent? |

#### Category 3: Delegation (IDs `3.x.x`)

| Metric | Sub-Metrics | What It Measures |
|--------|-------------|------------------|
| **3.1 Correct Delegation** | `3.1.1` specialist_routing, `3.1.2` direct_handling, `3.1.3` lane_boundary_respect | Does the agent route to the correct specialist? Does it handle things directly when appropriate? Does it stay in its lane? |
| **3.2 Handoff Quality** | `3.2.1` context_provision, `3.2.2` intent_clarity, `3.2.3` result_synthesis | When delegating, does the agent provide sufficient context, clear intent, and properly synthesize returned results? |
| **3.3 Pipeline Adherence** | `3.3.1` stage_sequence_respect, `3.3.2` role_absorption_prevention, `3.3.3` entry_point_routing | Does the agent follow the correct pipeline sequence? Does it avoid absorbing roles it should delegate? |

### Scoring Hierarchy

Scores flow bottom-up through four levels:

```
Sub-metric (bool)  →  1.0 if true, 0.0 if false, None if not applicable
      ↓
Metric (float)     →  mean of 3 sub-metrics (None values excluded)
      ↓
Category (float)   →  mean of 3 metrics
      ↓
Composite (float)  →  mean of 3 categories (accuracy, rejection, delegation)
      ↓
Run Score (float)   →  mean of N composites across N evaluated prompts
```

**Example calculation:**

```
Sub-metrics for accuracy:
  factual_correctness:  1.1.1=true(1.0), 1.1.2=false(0.0), 1.1.3=true(1.0)  → metric = 0.667
  instruction_following: 1.2.1=true(1.0), 1.2.2=true(1.0), 1.2.3=true(1.0)  → metric = 1.000
  reasoning_quality:     1.3.1=true(1.0), 1.3.2=false(0.0), 1.3.3=true(1.0)  → metric = 0.667

  accuracy category = (0.667 + 1.000 + 0.667) / 3 = 0.778

  Similarly for rejection (e.g., 0.889) and delegation (e.g., 0.778)

  composite = (0.778 + 0.889 + 0.778) / 3 = 0.815
```

**Implementation:** `autoresearch/harness/scorer.py`

### The Optimization Loop

```
Round 0: Baseline eval → score = 0.556
                ↓
Round 1: Optimizer reads scores, edits prompt
         Re-eval → score = 0.704
         0.704 > 0.556 → ACCEPTED, git commit
                ↓
Round 2: Optimizer reads updated scores, edits again
         Re-eval → score = 0.630
         0.630 < 0.704 → REJECTED, prompt restored, git commit
                ↓
Round 3: Optimizer reads history (including the rejection), tries different edit
         Re-eval → score = 0.852
         0.852 > 0.704 → ACCEPTED, git commit
                ↓
         ... continues up to max_rounds or convergence
```

**Implementation:** `EvalDriver.run_optimization()` in `autoresearch/loop/driver.py`

### Accept / Reject Decision

After each optimization round:

- **Accept** if `new_score > best_score` — the edited prompt becomes the new baseline
- **Reject** if `new_score <= best_score` — the original prompt is restored

Both outcomes are committed to git. Rejected rounds are preserved in history so the optimizer can learn from failed attempts.

The optimizer receives:
- The **last 5 rounds** of score history (most recent attempts)
- The **top 5 rounds** by score (best-performing prompts for reference)
- The current prompt and all eval spec files

### The Optimizer Agent

**File:** `.opencode/agents/optimizer.md`

The optimizer is an LLM agent with `read` and `edit` tool access. It does not execute tasks — it improves the instructions given to other agents by directly editing their `.md` files.

**Six editing operations:**

| Operation | When to Use |
|-----------|-------------|
| **Add** | Missing coverage for a behavior the eval tests |
| **Remove** | Instructions that actively cause failures |
| **Reorganize** | Related guidance is scattered or misordered |
| **Rewrite** | Correct intent but miscommunicated requirement |
| **Strengthen** | Vague guidance producing inconsistent behavior |
| **Relax** | Overly strict guidance causing false rejections |

**Diagnostic signals → operations:**

| Signal | Operation | Fix |
|--------|-----------|-----|
| False positives (agent rejects legitimate requests) | Relax | Add exception criteria, soften "never" rules |
| False negatives (agent accepts out-of-scope requests) | Strengthen | Add specific conditions, hard constraints |
| High variance across runs (std > 0.1) | Strengthen | Make guidance more specific |
| Low adversarial score | Strengthen | Add defenses against prompt injection |

**Optimization principles (from `autoresearch/program.md`):**
1. Address the weakest category first
2. Preserve demonstrated strengths (don't regress high-scoring areas)
3. Make targeted changes (surgical edits, not broad rewrites)
4. No contradictory instructions
5. Verbose does not mean better
6. One change focus per round
7. Guard against over-fitting to the eval set
8. Diagnose before editing

### The Evaluator Agent (LLM-as-Judge)

**File:** `.opencode/agents/evaluator.md`

The evaluator is a pure-reasoning agent with **all tools denied**. It receives:
1. The original test prompt
2. The target agent's response
3. Observed runtime events (tool calls, task delegations)
4. 9 sub-metric definitions with descriptions, expected outcomes, and observable behaviors

It returns a JSON object mapping each numeric ID to `true` or `false`:

```json
{"1.1.1": true, "1.1.2": false, "1.1.3": true, "1.2.1": true, ...}
```

**Rules:**
- Strict but fair — partial compliance is `false`
- Only judge what is actually in the response (no invented evidence)
- Empty or error responses → all `false`

### Scaffolding System

Since agents may invoke tools (read, glob, bash) during evaluation, the harness creates a minimal mock TypeScript project for each eval run:

```
autoresearch/test/<agent-name>/<run-id>/
├── package.json          # {"name": "eval-<agent>", "version": "1.0.0"}
├── tsconfig.json         # Minimal TS config
├── src/
│   └── index.ts          # console.log("hello");
└── tests/
    └── index.test.ts     # Basic import test
```

The scaffold is created before evaluation and cleaned up after.

**Implementation:** `autoresearch/harness/scaffolder.py`

### Git as Audit Trail

Every optimization round produces a git commit:

```
autoresearch: backend_developer_worker round 3 (accepted, score=0.852)

<optimizer reasoning: what was changed and why>
```

This creates a full history of prompt evolution. You can use `git log` to see the trajectory:

```bash
git log --oneline --grep="autoresearch"
```

Rejected rounds are also committed (with the restored original prompt) so the optimizer's full reasoning is preserved.

Before each round, the current prompt is backed up to:
```
autoresearch/results/<agent>/backups/round_<N>.md
```

---

## Agent Profiles

All agent definitions live in `.opencode/agents/`. Each is a Markdown file with YAML frontmatter (permissions, mode, description) and a markdown body (the system prompt).

### Executive Layer

#### CEO (`ceo.md`)

The top-level orchestration agent and sole user interface. The CEO:
- Receives user requests and validates them
- Routes to the correct pipeline entry point
- Dispatches the four team leads via the `task` tool
- Sequences the pipeline: scoper → architect → builder → verifier
- Aggregates lead results and returns structured responses to the user

**Permissions:** `task: allow`, `todowrite: allow` — all other tools denied. The CEO cannot read files, write code, run commands, or interact with the codebase directly. It can only dispatch leads.

**Reports to:** The human user (no layer above)

**Direct reports:** `scoper_lead`, `architect_lead`, `builder_lead`, `verifier_lead`

### Team Lead Layer

#### Scoper Lead (`scoper_lead.md`)

Strategic scoping specialist. Identifies the next high-leverage, issue-sized vertical slice to work on. Determines what should be built next, what's in scope, what should be deferred, and what module boundaries to preserve.

**Dispatches:** `researcher_worker`, `business_analyst_worker`, `quantitative_developer_worker`

**Produces:** Strategic Slice Briefs

#### Architect Lead (`architect_lead.md`)

System architecture authority. Converts an approved strategic slice into a minimal architecture delta — defining boundaries, interfaces, state ownership, contracts, and architectural invariants.

**Dispatches:** `solution_architect_worker`, `backend_developer_worker`, `test_engineer_worker`

**Produces:** System Slice Architecture Briefs

**Upstream input:** Strategic Slice Briefs from `scoper_lead`

#### Builder Lead (`builder_lead.md`)

Implementation coordination authority. Coordinates the implementation of approved slices by dispatching workers with disjoint edit surfaces (no two workers edit the same file).

**Dispatches:** `backend_developer_worker`, `frontend_developer_worker`, `test_engineer_worker`, `agentic_engineer_worker`

**Produces:** Build Slice Execution Summaries, Builder Self-Verification Reports

**Upstream input:** Architecture Briefs from `architect_lead`

#### Verifier Lead (`verifier_lead.md`)

Verification and gate authority. Performs second-order verification and false-positive audits. Returns gate decisions: PASS, CONDITIONAL PASS, FAIL, or BLOCKED.

**Dispatches:** `backend_developer_worker`, `frontend_developer_worker`, `test_engineer_worker`

**Produces:** Verification Reports with gate decisions

### Worker Layer

All workers have full tool access (read, edit, bash, glob, grep, etc.) and operate autonomously under their assigned team lead.

| Worker | Specialization |
|--------|---------------|
| `agentic_engineer_worker` | Agent prompt authoring, harness design, event loop architecture |
| `backend_developer_worker` | Server-side logic, data layer, APIs, database operations |
| `frontend_developer_worker` | UI components, client-side logic, styling, accessibility |
| `test_engineer_worker` | Test strategy, oracle design, red/green/refactor cycles |
| `researcher_worker` | Ecosystem patterns, first-principles analysis, investigation |
| `business_analyst_worker` | Stakeholder needs, requirements mapping, process analysis |
| `quantitative_developer_worker` | Quantitative validation, numerical modeling, data pipelines |
| `solution_architect_worker` | Integration strategy, tradeoff analysis, design exploration |
| `code_review_worker` | Code review coordination, quality enforcement |

### Supporting Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| `evaluator` | LLM-as-judge for the eval harness. Returns boolean pass/fail judgments. | None (pure reasoning) |
| `optimizer` | Reads eval scores and directly edits agent prompts to improve them. | `read`, `edit`, `glob`, `grep`, `websearch`, `webfetch` |
| `monitoring_worker` | System observability and monitoring. | Full access |

---

## Eval Spec Format

Each agent has 3 spec files in `autoresearch/agents/<agent-name>/spec/`:

```
autoresearch/agents/ceo/spec/
├── accuracy.json      # 10 prompts + 9 sub-metric definitions
├── rejection.json     # 10 prompts + 9 sub-metric definitions
└── delegation.json    # 10 prompts + 9 sub-metric definitions
```

**Schema:**

```json
{
  "schema_version": "1.0",
  "category": "accuracy",
  "description": "What this spec evaluates",
  "metrics": {
    "factual_correctness": {
      "sub_metrics": {
        "fact_accuracy": {
          "description": "What this sub-metric measures",
          "expected_outcome": "What a passing response looks like",
          "observable_behavior": "What to look for in the agent's output",
          "output": null
        }
      }
    }
  },
  "prompts": [
    {
      "id": "1",
      "rationale": "Why this prompt tests the category",
      "prompt": "The full 400+ word test prompt sent to the agent"
    }
  ]
}
```

Each spec contains:
- **10 test prompts** — detailed, 400+ word scenarios with rationale
- **9 sub-metric definitions** — 3 metrics x 3 sub-metrics, each with description, expected outcome, and observable behavior

Template schemas live in `autoresearch/agents/schema/` and are customized per agent in their respective `spec/` directories.

**Total eval surface per agent:** 30 prompts (10 per category) x 9 sub-metrics = 270 evaluation judgments possible.

---

## Usage

### Evaluate a Single Agent

```bash
python -m autoresearch.loop.driver --agent ceo --eval-only --verbose
```

### Evaluate All Agents

```bash
python -m autoresearch.loop.driver --agent all --eval-only --verbose
```

### Optimize an Agent (up to 20 rounds)

```bash
python -m autoresearch.loop.driver --agent backend_developer_worker --max-rounds 20 --verbose
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--agent` | (required) | Agent name or `all` |
| `--eval-only` | `false` | Run evaluation without the optimization loop |
| `--max-rounds` | `20` | Maximum optimization rounds |
| `--run-id` | auto-generated | Custom run identifier |
| `--timeout` | `300` | Timeout per agent subprocess in seconds |
| `--parallel` | `3` | Max concurrent agent evals |
| `--verbose` | `false` | Print per-prompt scores to stdout |

### Example Output

```
AutoResearch | run_id=run-20260408-143022-1 | agents=1 | mode=optimize

Optimization: backend_developer_worker | max_rounds=20

Evaluating: backend_developer_worker
  Category: accuracy
  [accuracy] 6/9 (12.3s + 8.1s eval)
  Category: rejection
  [rejection] 7/9 (9.8s + 7.2s eval)
  Category: delegation
  [delegation] 5/9 (14.1s + 6.9s eval)

Baseline score: 0.667

============================================================
Round 1/20
  Optimizer edited backend_developer_worker.md
  Reasoning: Strengthened delegation criteria for 3.1.1...
  ACCEPTED: 0.741 (+0.074)
```

---

## Directory Structure

```
just-oc/
├── .opencode/                          # OpenCode/Kilo configuration
│   ├── agents/                         # 17 agent definitions (.md files)
│   │   ├── ceo.md                      # Executive orchestrator
│   │   ├── scoper_lead.md              # Strategic scoping lead
│   │   ├── architect_lead.md           # Architecture lead
│   │   ├── builder_lead.md             # Implementation lead
│   │   ├── verifier_lead.md            # Verification lead
│   │   ├── backend_developer_worker.md # Backend specialist
│   │   ├── frontend_developer_worker.md
│   │   ├── test_engineer_worker.md
│   │   ├── agentic_engineer_worker.md
│   │   ├── researcher_worker.md
│   │   ├── business_analyst_worker.md
│   │   ├── quantitative_developer_worker.md
│   │   ├── solution_architect_worker.md
│   │   ├── code_review_worker.md
│   │   ├── monitoring_worker.md
│   │   ├── evaluator.md                # LLM judge (no tools)
│   │   └── optimizer.md                # Prompt optimizer
│   ├── commands/                       # Custom slash commands
│   ├── skills/                         # 26 skill definitions
│   └── config/                         # Shared configuration
│
├── autoresearch/                       # Optimization engine
│   ├── loop/                           # Orchestration
│   │   ├── driver.py                   # Main eval + optimization harness
│   │   └── config.py                   # CLI argument parsing
│   ├── harness/                        # Evaluation components
│   │   ├── runner.py                   # opencode subprocess wrapper
│   │   ├── event_listener.py           # NDJSON event stream parser
│   │   ├── spec_reader.py              # Spec JSON loader + ID mapper
│   │   ├── evaluator.py               # LLM-as-judge wrapper
│   │   ├── scorer.py                   # Hierarchical scoring (27 → 1)
│   │   ├── results_writer.py           # Results output
│   │   ├── scaffolder.py              # Mock workspace generator
│   │   └── runtime_log.py             # NDJSON runtime logging
│   ├── agents/                         # Eval specifications
│   │   ├── schema/                     # Template spec schemas
│   │   │   ├── accuracy.json
│   │   │   ├── rejection.json
│   │   │   └── delegation.json
│   │   └── <agent-name>/spec/          # Per-agent specs (14 agents)
│   │       ├── accuracy.json           # 10 prompts + 9 sub-metric defs
│   │       ├── rejection.json
│   │       └── delegation.json
│   ├── tests/                          # Pytest test suite
│   ├── results/                        # Optimization output + backups
│   ├── logs/                           # Runtime NDJSON logs
│   ├── test/                           # Generated scaffold workspaces
│   └── program.md                      # Optimizer instructions
│
├── .kilo/                              # Kilo-specific overrides
├── kilo.jsonc                          # Kilo permission + agent config
├── AGENTS.md                           # Agent documentation
├── LICENSE                             # MIT License
└── README.md                           # This file
```

---

## Configuration

### OpenCode Symlink Setup

The `.opencode/` directory is designed to be symlinked to your system config:

```bash
# OpenCode
ln -s /path/to/just-oc/.opencode ~/.config/opencode

# Kilo Code
ln -s /path/to/just-oc/.opencode ~/.config/kilo/opencode
```

### Agent Permissions

Each agent's permissions are declared in YAML frontmatter:

```yaml
---
name: ceo
description: Top-level orchestration agent
mode: primary
permission:
  task: allow      # Can dispatch sub-agents
  read: deny       # Cannot read files
  edit: deny       # Cannot edit files
  bash: deny       # Cannot run commands
  # ... all other tools denied
---
```

The CEO has only `task` and `todowrite` access. Workers have full access. The evaluator has no tool access at all.

### Kilo Configuration (`kilo.jsonc`)

```jsonc
{
  "$schema": "https://app.kilo.ai/config.json",
  "instructions": ["./AGENTS.md"],
  "permission": {
    "bash": "allow",
    "edit": "allow",
    "read": "allow"
    // ...
  }
}
```

---

## Testing

```bash
# Run all tests
pytest autoresearch/tests/

# Individual test files
pytest autoresearch/tests/test_spec_reader.py   # Spec loading, 27-ID uniqueness
pytest autoresearch/tests/test_evaluator.py     # LLM judge parsing
pytest autoresearch/tests/test_event_parser.py  # NDJSON event parsing
pytest autoresearch/tests/test_results_writer.py # Result output format
pytest autoresearch/tests/test_scaffolder.py    # Mock workspace generation
```

Key assertions enforced:
- All 27 numeric IDs are unique and map correctly to `1.1.1` through `3.3.3`
- Each agent has exactly 10 prompts per category
- Each prompt is at least 400 words
- Scaffolded workspaces contain all required files

---

## License

MIT — see [LICENSE](LICENSE).
