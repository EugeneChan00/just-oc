# Agents Configuration

This directory contains custom agent definitions for OpenCode/Kilo.

## Structure

- `general.md` - General purpose agent for multi-step research tasks
- `explore.md` - Fast read-only agent for codebase exploration
- `plugins/` - Plugin-specific agents

## Agent Format

```yaml
---
description: Agent description
mode: subagent
model: anthropic/claude-sonnet-4-20250514
permission:
  edit: deny
  bash: ask
---
System prompt content...
```

## Modes

- `primary` - User-facing agent (switch with Tab)
- `subagent` - Only invocable via Task tool or @ mentions
- `all` - Can be both primary and subagent (default)

## Usage

Agents in this directory are automatically discovered by OpenCode/Kilo when symlinked to:
- `~/.config/opencode/agents/`
- `~/.config/kilo/opencode/agents/`
