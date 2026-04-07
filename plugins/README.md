# Plugins Directory

This directory contains plugin source code for the just-oc mono repo.

## Structure

Each plugin should be in its own subdirectory:

```
plugins/
├── my-plugin/
│   ├── README.md
│   ├── src/
│   └── package.json
└── another-plugin/
    ├── README.md
    └── ...
```

## Creating a New Plugin

1. Create a new directory under `plugins/`
2. Add a `README.md` with plugin documentation
3. Add your plugin code
4. Update the main `AGENTS.md` if the plugin includes new agents or skills

## Plugin Integration

Plugins can provide:
- Custom agents (in `.opencode/agents/plugins/`)
- Custom skills (in `.opencode/skills/plugins/`)
- Custom commands (in `.opencode/commands/plugins/`)

See the respective README files for the exact format.
