# .real-agents/docs — Research Index

## Available Research

| Document | Description |
|----------|-------------|
| `system-prompt-length-research.md` | Full 10-query research synthesis with deep detail and all task IDs |
| `system-prompt-design-tldr.md` | TL;DR reference card for quick lookup |
| `opencode-plugin-ecosystem.md` | OpenCode plugin architecture: types, hooks, tools, lifecycle, config |

## How to Use

1. **Quick question** → start with `system-prompt-design-tldr.md`
2. **Deep investigation** → read `system-prompt-length-research.md`
3. **Follow-up** → use task IDs from either document with `task resume`

## Research Metadata

- **Topic**: Optimal system prompt length
- **Date**: 2026-04-07
- **Lead**: SCOPER-LEAD
- **Workers Dispatched**: 10 researcher agents (8 completed, 2 blocked)
- **Confidence Summary**: 
  - High: Attention sinks, hierarchy failures, instruction density
  - Medium: Position effects, model variation
  - Low: Literature synthesis (benchmarks don't study length)
  - Unknown: Repetition effects, noise tolerance

## Blocked Queries Requiring Follow-Up

| Query | Issue | Fix Required |
|-------|-------|-------------|
| Q6 (Repetition) | Agent stopped early without returning | New dispatch needed |
| Q8 (Noise tolerance) | Agent blocked on chaining budget clarification | Resume with chaining budget |
