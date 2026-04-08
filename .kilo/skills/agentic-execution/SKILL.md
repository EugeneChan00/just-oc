---
name: agentic-execution
description: Orchestration index for agentic planning and multi-layer execution. Routes to references for spawning subagents, domain agents, and applying systematic thinking frameworks.
---

# Agentic Execution Reference Index

This skill orchestrates multi-layer agentic execution through systematic references.

## Context Invariants

Every execution applies three core components:

1. **Dependencies** - Abstraction of what depends on what
2. **Parallelization** - Concurrent execution patterns
3. **Reflexivity Metrics** - Self-assessment and improvement loops

## Model Boundaries

Execution operates within three models:

1. **Interaction Model** - How agents communicate and coordinate
2. **Reflexion Model** - Verification and self-improvement
3. **Context Model** - State and memory management

## References

| Reference | Purpose | Use When |
|-----------|---------|----------|
| `meta-skills/` | Create new skills and capabilities | User asks to create/define a new skill or automation |
| `~/.claude/skills/first-principle-thinking/` | First-principle reasoning from ground truth | Problem requires reasoning from fundamentals, not pattern-matching |
| `meta-prompt.md` | Create structured prompts | User needs prompt engineering for workflows |
| `orchastration.md` | Multi-agent coordination patterns | Orchestrating parallel or cascaded agent workflows |
| `verification.md` | Output verification patterns | Validating agent outputs against goals |
| `test-driven-development.md` | Serena-first red/green/refactor execution | User asks for feature implementation, bug fixes, or behavior changes with test-first discipline |
| `test-specs.md` | Reusable scenario specs and tool mapping | User asks to define or select concrete frontend/backend/integration test scenarios |

## Execution Techniques

Apply to obtain context invariants:

1. **Abstraction** - Extract essential patterns and dependencies
2. **Refactor** - Restructure for clarity and efficiency
3. **Derive** - Generate new insights from existing context

## Spawning Subagents

When spawning subagents, you **must** use the format and framework enlisted in `meta-prompt.md`. This ensures consistent prompt structure, delegation patterns, and output protocols across all agent interactions.

## Usage

Always refer to `index.yaml` for project-context execution when available.

## Default Implementation Policy

For feature implementation, bug fixes, and behavior changes, execution must route through
`test-driven-development.md` as the primary workflow reference.

Required defaults:
1. Follow red/green/refactor.
2. Use Serena-first code investigation before implementation edits.
3. Prefer modifying/reducing existing code before adding new code.
4. Do not use mock-based tests for feature behavior verification.
5. Select or adapt a scenario from `test-specs.md` before broad implementation.
