---
name: Meta Skill
description: Creates new skills based on user requirements. Use when the user wants to create a new skill, automate a workflow, or define a reusable capability for the system.
aliases: []
id: SKILLS
tags: []
---

# Meta Skill - Skill Generator

This meta skill takes a user's skill request and generates a complete SKILL.md file following the canonical skill format used in Claude Code.

## Purpose

Skills are reusable capabilities that define how to accomplish specific tasks. This meta skill automates the creation of new skills by analyzing the user's requirements and generating properly structured SKILL.md files with clear workflows, prerequisites, configuration details, and examples.

## Variables

USER_SKILL_REQUEST: The user's description of the skill they want to create

## Understanding Skill Types

Skills can be categorized by their purpose:

### Execution Skills
- Start/stop services or applications
- Run scripts or commands
- Execute specific workflows
- Example: "start-orchestrator", "deploy-service", "run-tests"

### Analysis Skills
- Analyze code, logs, or data
- Generate reports or summaries
- Perform diagnostics
- Example: "analyze-performance", "check-dependencies", "audit-security"

### Generation Skills
- Create files, configurations, or code
- Generate documentation
- Scaffold projects
- Example: "create-api-endpoint", "generate-docs", "scaffold-component"

### Integration Skills
- Connect to external services
- Perform API operations
- Sync data between systems
- Example: "sync-database", "deploy-to-cloud", "fetch-analytics"

## Workflow

### 1. Analyze the Skill Request

Parse the USER_SKILL_REQUEST to identify:
- **Core functionality**: What does the skill do?
- **Trigger conditions**: When should this skill be used?
- **Prerequisites**: What needs to exist or be installed?
- **Input parameters**: What arguments or configuration does it need?
- **Expected outcomes**: What should happen after execution?

### 2. Determine Skill Type and Structure

Based on the analysis, determine:
- Skill category (execution, analysis, generation, integration)
- Required sections (Prerequisites, Configuration, Flags, etc.)
- Complexity level (simple script vs. multi-step workflow)
- Example scenarios needed

### 3. Define Prerequisites and Configuration

Identify:
- Dependencies (languages, frameworks, tools)
- File locations and paths
- Environment variables or .env configurations
- Running services or databases
- Default values and fallbacks

### 4. Create Detailed Workflow Steps

Structure the workflow as numbered steps with:
- Clear action descriptions
- Specific commands in code blocks
- Conditional logic (if needed)
- Error handling guidance
- Wait times or dependencies between steps

### 5. Generate Concrete Examples

Create 2-4 example scenarios showing:
- Basic usage (most common case)
- Advanced usage (with flags or custom configuration)
- Edge cases or alternatives
- User request → Execution flow format

### 6. Write Complete SKILL.md File

Generate the file following the Specified Format below, ensuring:
- YAML frontmatter is complete
- All sections are properly formatted
- Code blocks use appropriate syntax highlighting
- Paths and commands are accurate
- Examples are executable

### 7. Save to Skills Directory

Write the skill file to `_ard/assets/skills/[skill-name]/SKILL.md`

## Specified Format

Every generated skill MUST follow this structure:
````markdown
---
name: [Descriptive Skill Name]
description: [One-line description of what the skill does and when to use it. Include trigger phrases like "Use when the user asks to...", "launch...", "run...", "open...". Mention supported flags if applicable.]
---

# [Skill Title]

[2-3 sentence overview of what the skill does and its purpose]

## Prerequisites

[List all requirements with clear descriptions]
- [Dependency 1]: [Why it's needed]
- [Dependency 2]: [Version or specifics]
- [File/directory location]: [Path and what it contains]
- [Service requirement]: [What needs to be running]

## Configuration

[Describe configurable settings]

Default [values/ports/settings] (configurable via `.env`):
- **[Config Item 1]**: [Value] (default fallback: [fallback value])
- **[Config Item 2]**: [Value]

[Additional configuration sections as needed]

## [Optional Sections Based on Skill Type]

### Backend Flags
(For execution skills with command-line options)

The [script name] (`[script.sh]`) accepts:

| Flag | Description | Priority |
|------|-------------|----------|
| `--[flag1] <value>` | [Description] | CLI > .env (`[ENV_VAR]`) > current dir |
| `--[flag2] <id>` | [Description] | CLI > .env (`[ENV_VAR]`) > new session |

### API Endpoints
(For integration skills)

[List of endpoints, methods, and parameters]

### File Structure
(For generation skills)

[Expected directory structure or output format]

## Workflow

### 1. [First Major Step]

[Detailed description with specific actions]
```bash
[command or code block]
```

### 2. [Second Major Step]

[Description with sub-steps if needed]

a. [Sub-step]
b. [Sub-step]
```bash
[command or code block]
```

### 3. [Continue numbering steps...]

[Each step should be clear and actionable]

### [Final Step]. [Completion or Verification]

[What indicates successful completion]

## Examples

### Example 1: Basic Usage

**User request:**
````
[Natural language request from user]
