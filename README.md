# Just-OC: OpenCode/Kilo Mono Repo

Unified OpenCode and Kilo Code configuration repository for managing plugins, agents, skills, and commands in a mono repo structure.

## Quick Start

```bash
# Clone this repository
git clone <repo-url> ~/just-oc

# Symlink for OpenCode
ln -s ~/just-oc/.opencode ~/.config/opencode

# Symlink for Kilo Code
ln -s ~/just-oc/.opencode ~/.config/kilo/opencode
# OR
ln -s ~/just-oc/.opencode ~/.kilo/opencode

# Restart OpenCode/Kilo to load the new configuration
```

## Directory Structure

| Directory | Purpose |
|-----------|---------|
| `.opencode/agents/` | Custom agent definitions |
| `.opencode/commands/` | Custom slash commands |
| `.opencode/skills/` | Agent skills (api-design, code-review, etc.) |
| `.opencode/config/` | Shared configuration snippets |
| `.kilocode/skills/` | Kilo-specific skills |
| `plugins/` | Plugin source code repositories |

## Features

- **Unified Configuration**: Single `.opencode/` directory works for both OpenCode and Kilo
- **Mono Repo Structure**: All plugins and configs in one place
- **Symlink-Based**: Easy system integration without copying files
- **Extensible**: Add new agents, skills, and commands by adding files

## Managing Configuration

### Adding a Custom Agent

```bash
# Create agent file
cat > .opencode/agents/my-agent.md << 'AGENT_EOF'
---
description: My custom agent
mode: subagent
permission:
  edit: deny
  bash: ask
---
Your agent prompt here...
AGENT_EOF
```

### Adding a Skill

```bash
# Create skill directory and file
mkdir -p .opencode/skills/my-skill
cat > .opencode/skills/my-skill/SKILL.md << 'SKILL_EOF'
---
name: my-skill
description: Use when needing my skill
---
# Instructions
SKILL_EOF
```

### Adding a Command

```bash
# Create command file
cat > .opencode/commands/my-command.md << 'CMD_EOF'
---
description: My custom command
agent: build
---
Run my custom command with $ARGUMENTS
CMD_EOF
```

## Documentation

- [OpenCode Documentation](https://opencode.ai/docs)
- [Kilo Documentation](https://kilo.ai/docs)
- [Agent Skills Specification](https://agentskills.io)

## License

MIT - See individual components for their respective licenses.
