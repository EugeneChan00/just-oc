# Skills Configuration

This directory contains skill definitions following the Agent Skills open standard.

## Structure

```
skills/
├── README.md
├── api-design/
│   └── SKILL.md
├── code-review/
│   └── SKILL.md
└── plugins/
    └── */SKILL.md
```

## SKILL.md Format

```yaml
---
name: skill-name
description: When to use this skill (1-1024 chars)
---

# Instructions
Detailed instructions for the agent...
```

## Skills

- `api-design/` - REST API design best practices
- `code-review/` - Code review guidelines and checklist

## Usage

Skills are loaded on-demand when the agent determines a task matches the skill's description. Skills in this directory are automatically discovered by OpenCode/Kilo when symlinked to:
- `~/.config/opencode/skills/`
- `~/.config/kilo/opencode/skills/`

## Name Matching

The `name` field in SKILL.md must match the parent directory name:
- `skills/api-design/SKILL.md` → name: api-design
- `skills/my-skill/SKILL.md` → name: my-skill
