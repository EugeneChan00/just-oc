---
name: sdk-cli
description: >
  MANDATORY skill for the "real" CLI and deep execution engine. Use this skill
  whenever the task involves src/cli.tsx, the "real" binary, deep execution via
  "real dp", spawning profiled agents, --profile, --continue, --jm / --just-model,
  model routing via .real-agents/config/config.yaml, profile loading from
  .real-agents/profiles/, the Dispatcher interface, or running agents programmatically
  via the Claude Agent SDK. Also use when working with issue/spec YAML artifacts,
  the execution hierarchy (enterprise → milestone → issue → sub-issue), or the
  verification loop. Do not bypass this skill by improvising raw bun commands when
  the user expects the CLI workflow.
---

# Real CLI — Agent Orchestration Platform

## Architecture Overview

The platform is organized into deep modules with clean interfaces:

```
src/
├── config/            # .real-agents/ discovery + config parsing
├── dispatch/          # Agent dispatch — adapters for AI backends
│   ├── index.ts       #   Types (Dispatcher, DispatchRequest/Result) + re-exports
│   ├── profile-loader.ts  # Profile reading, prompt assembly, hook building
│   ├── agent-runner.ts    # Generic SDK query execution, bounding, timeout
│   └── claude-adapter.ts  # Thin Dispatcher impl wiring loader → runner
├── exec/              # Deep execution engine
│   ├── schema.ts      #   YAML types + validation (exit code 2 on mismatch)
│   ├── state.ts       #   Run state (JSON) + journal (JSONL)
│   ├── runner.ts      #   Orchestration loop — steps, retries, verification
│   ├── verifier.ts    #   Scoped verification via test_engineer profile
│   ├── hierarchy.ts   #   Execution level enforcement + cycle detection
│   └── resolve.ts     #   Canonical artifact path resolver
├── prompts/           # Prompt template engine (renderPrompt + loadPromptTemplate)
├── tools/             # MCP tool surface (agents_query)
├── worktree/          # Git worktree lifecycle
└── cli.tsx            # Entry point — "real" binary
```

Dependency rule: `cli → tools → exec → dispatch → config`. No upward imports.

## Quick Start

```bash
# Install the binary
bun link

# Agent query with rich Ink terminal UI
real --profile agentic_engineer "build a test profile"
real --profile test_engineer "review test coverage"

# Deep execution — run an issue YAML
real dp .real-agents/roadmap/dogfood-test/dogfood-string-utils.yaml

# Deep execution — run a milestone (executes child issues sequentially)
real dp .real-agents/roadmap/dogfood-test/dogfood-test.yaml

# Continue a previous session
real --profile agentic_engineer --continue "follow up on that"

# JSON stream mode
real --json --profile agentic_engineer "list your skills"

# Verbose mode (no output truncation)
real -v --profile agentic_engineer "analyze this file"
```

## CLI Flags

| Flag | Description |
|------|-------------|
| `--profile <name>` | Load a profile from `.real-agents/profiles/<name>/`. Assembles system prompt + hooks. |
| `--jm <name>` / `--just-model <name>` | Load model routing from just-model.yaml. Applies runtime model, endpoint, API key. |
| `--continue [session-id]` | Resume a previous session. Reads last session from `.real-agents/.last-session` if no ID. |
| `--json` | Newline-delimited JSON output instead of rich terminal UI. |
| `--verbose` / `-v` | Full tool output without truncation. |
| `--<mode>` | Activate a mode defined in profile settings.json (filters active pattern categories). |

## Deep Execution (`real dp`)

The `dp` subcommand runs YAML artifacts through the deep execution engine.

### Execution Hierarchy

```
enterprise (depth 0) → milestone (depth 1) → issue (depth 2) → sub-issue (depth 3)
```

Each level can only invoke the level directly below it. Enforced by `src/exec/hierarchy.ts`.

### Running an Issue

```bash
real dp path/to/issue.yaml
```

The engine:
1. Loads and validates the YAML (exit code 2 on schema mismatch)
2. Checks hierarchy guards (type enforcement, cycle detection)
3. Creates a git worktree for isolation
4. Executes each step sequentially:
   - Dispatches an agent with the step's profile (default: agentic_engineer)
   - Runs verification via test_engineer profile
   - Retries on verification failure (configurable via `on_failure`)
5. Tracks state in `.real-agents/state/<id>.json`
6. Logs events to `.real-agents/logs/<id>.jsonl`
7. Cleans up worktree per cleanup policy

### Running a Milestone

```bash
real dp path/to/milestone.yaml
```

Milestones execute their child issues sequentially. Each child gets its own worktree and state tracking.

### Running an Enterprise

```bash
real dp path/to/enterprise.yaml
```

Enterprises execute their milestones sequentially.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success — all steps passed verification |
| 1 | Runtime error — agent crash, dispatch failure, etc. |
| 2 | Schema validation error — YAML doesn't match schema. The error message tells the agent exactly what field failed and what was expected, enabling self-correction. |

### State and Resumption

State is persisted to `.real-agents/state/<id>.json` after every step. If a run is interrupted, re-running the same YAML resumes from the last incomplete step.

State JSON structure:
```json
{
  "issueId": "001-dispatch",
  "yamlHash": "sha256...",
  "steps": [
    { "name": "step-1", "status": "passed", "attempt": 1, "lastVerdict": {...} },
    { "name": "step-2", "status": "running", "attempt": 2 }
  ],
  "startedAt": "...",
  "updatedAt": "..."
}
```

### Verification Loop

Each step can declare `acceptance_criteria` referencing spec criteria (e.g., `P01.CRIT-01`). After the step agent completes, a verification agent (test_engineer profile) checks the criteria and returns a JSON verdict:

```json
{
  "passed": ["P01.CRIT-01"],
  "failed": [{ "specId": "P01.CRIT-02", "feedback": "function not exported" }],
  "overall": false
}
```

Failed verification triggers retry (configurable via `on_failure.retry` and `on_failure.escalate`).

### Prompt Templates

Prompts for dispatch and verification are loaded from `.real-agents/config/prompts/`:
- `dispatch-step.md` — template for step agent prompts
- `verify-step.md` — template for verification agent prompts

Templates use `${key}` substitution via `renderPrompt()` from `src/prompts/`.

## YAML Artifact Schema

### Issue (type: issue)

```yaml
id: "001-dispatch-module"
type: issue
title: "Create dispatch module"
spec: "001-dispatch-module.spec.yaml"    # path to spec (sibling convention)
base_branch: "main"
cleanup: "on-success"                     # on-success | always | never

steps:
  - name: "create-types"
    prompt: |
      Create src/dispatch/types.ts with the Dispatcher interface...
    acceptance_criteria:
      - "P01.CRIT-01"
    verify: "bun tsc --noEmit src/dispatch/types.ts"
    profile: "backend_developer"          # default: agentic_engineer
    on_failure:
      retry: 3                            # default: 3
      escalate: "abort"                   # abort | continue | pause

  - name: "create-adapter"
    prompt: |
      Create the Claude Code SDK adapter...
    depends_on:
      - "create-types"
    acceptance_criteria:
      - "P02.CRIT-02"
```

### Milestone (type: milestone)

```yaml
id: "m01-src-refactor"
type: milestone
title: "M01 — Module Refactor"
issues:
  - "001-dispatch-module.yaml"
  - "002-exec-module.yaml"
```

### Enterprise (type: enterprise)

```yaml
id: "enterprise-q2"
type: enterprise
title: "Q2 2026 — Platform Build"
milestones:
  - "m01-src-refactor/m01-src-refactor.yaml"
  - "m02-platform-features/m02-platform-features.yaml"
```

### Spec

```yaml
id: "001-dispatch-module"
milestone: "m01-src-refactor"
goal: "Create the dispatch module..."
phases:
  P01:
    name: "Types & Interface"
    features:
      FEAT-01:
        description: "DispatchRequest type"
    acceptance_criteria:
      CRIT-01:
        description: "types.ts exports all required types"
        assertion:
          type: structural
          check: "Import and verify exports"
adversarial:
  strategy: "Verify actual implementation, not stubs"
  mutations: "Test with missing fields, wrong types"
```

## Model Routing

Models are configured in `.real-agents/config/config.yaml`:

```yaml
models:
  default: "glm"
  profiles:
    glm:
      runtimeModel: "glm-5.1"
      endpoint: "https://aa.renaissancelab.org"
      apiKey: "$CLI_PROXY_STACK_API_KEY"
      env:
        ANTHROPIC_BASE_URL: "https://aa.renaissancelab.org"
        ANTHROPIC_API_KEY: "$CLI_PROXY_STACK_API_KEY"
        ANTHROPIC_DEFAULT_SONNET_MODEL: "glm-5.1"
```

The `$ENV_VAR` syntax resolves at runtime from `process.env`. The `default` field selects which profile to use when no `--jm` flag is passed.

The `--jm` flag on the CLI overrides the config default for agent query mode.

## Profile Loading

Profiles live in `.real-agents/profiles/<name>/`:

```
.real-agents/profiles/<name>/
├── .claude/
│   ├── SYSTEM.md           # Agent identity
│   ├── settings.json       # Mode configs
│   └── skills/             # Skill definitions
├── .claude-plugin/
│   └── plugin.json         # Plugin manifest for skill discovery
├── expertise.jsonl          # Tech stack knowledge
└── patterns.jsonl           # Behavioral patterns
```

8 profiles: `agentic_engineer`, `test_engineer`, `backend_developer`, `frontend_developer`, `researcher`, `solutions_architect`, `business_analyst`, `quantitative_developer`

Profile loading is handled by `src/dispatch/profile-loader.ts`. The system prompt is assembled in layers:
1. SYSTEM.md — agent identity
2. Tech Stack — system_prompt expertise entries
3. Domain Knowledge — system_prompt pattern entries
4. Mode append — extra text from active mode

## Dispatcher Interface

The central contract. All agent dispatch goes through this interface:

```typescript
interface Dispatcher {
  dispatch(req: DispatchRequest): Promise<DispatchResult>
}
```

`ClaudeCodeDispatcher` is the current adapter. Adding a new backend = one new adapter file.

## .real-agents/ Directory

The app discovers `.real-agents/` by walking up from CWD (like `.claude/` discovery). Structure:

```
.real-agents/
├── config/
│   ├── config.yaml        # Project config + model routing
│   └── prompts/           # Prompt templates (verify-step.md, dispatch-step.md)
├── profiles/              # Agent personas
├── docs/                  # Project knowledge + schemas
├── roadmap/               # Milestones, issues, specs
├── state/                 # Runtime — step state (JSON), gitignored
├── logs/                  # Runtime — event journals (JSONL), gitignored
└── worktrees/             # Runtime — git worktrees, gitignored
```
