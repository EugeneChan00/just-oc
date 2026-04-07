# Commands Configuration

This directory contains custom slash commands for OpenCode/Kilo.

## Structure

- `*.md` - Individual command definitions
- `plugins/` - Plugin-specific commands

## Command Format

```yaml
---
description: Brief description shown in TUI
agent: build
---

Prompt content with $ARGUMENTS, $1, $2, etc.
```

## Placeholders

- `$ARGUMENTS` - All arguments passed to command
- `$1`, `$2`, `$3` - Individual positional arguments
- `!`command`` - Inject bash command output
- `@filename` - Include file content

## Usage

Commands in this directory are automatically discovered by OpenCode/Kilo when symlinked to:
- `~/.config/opencode/commands/`
- `~/.config/kilo/opencode/commands/`
