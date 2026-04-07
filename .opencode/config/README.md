# Shared Configuration Snippets

This directory contains reusable configuration snippets that can be referenced by agents.

## Structure

```
config/
├── prompts/      # Reusable prompt templates
└── rules/        # Custom rules for specific file types
```

## Usage

Reference these files in your agent prompts or kilo.jsonc:

```json
{
  "instructions": [
    "./.opencode/config/rules/typescript.md"
  ]
}
```
