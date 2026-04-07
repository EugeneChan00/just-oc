# Just-OC OpenCode/Kilo Configuration

This repository contains unified OpenCode/Kilo plugin configurations for a mono repo structure.

## Structure

```
.just-oc/
├── .opencode/          # OpenCode/Kilo config (symlink to system)
│   ├── agents/         # Custom agent definitions
│   ├── commands/       # Custom slash commands
│   ├── skills/         # Skill definitions
│   └── config/         # Shared configuration snippets
├── .kilocode/          # Kilo-specific overrides
│   └── skills/         # Kilo-specific skills
├── plugins/            # Plugin source code
├── kilo.jsonc          # Kilo configuration
└── AGENTS.md           # This file
```

## Symlink Setup

To use this configuration with OpenCode/Kilo, create symlinks:

```bash
# For OpenCode
ln -s /path/to/just-oc/.opencode ~/.config/opencode

# For Kilo Code
ln -s /path/to/just-oc/.opencode ~/.config/kilo/opencode
# OR
ln -s /path/to/just-oc/.opencode ~/.kilo/opencode
```

## Available Agents

- **general** - General purpose research and multi-step task execution
- **explore** - Fast read-only codebase exploration

## Available Skills

- **api-design** - REST API design best practices
- **code-review** - Code review guidelines and checklist

## Available Commands

Commands can be invoked with `/command-name` in the OpenCode/Kilo interface.

## Adding New Agents

1. Create a `.md` file in `.opencode/agents/`
2. Follow the agent format with YAML frontmatter
3. Commit and push to update the symlinked configuration

## Adding New Skills

1. Create a directory in `.opencode/skills/`
2. Add a `SKILL.md` file with name matching the directory
3. Follow the Agent Skills standard format

## License

See individual plugin and skill directories for respective licenses.
