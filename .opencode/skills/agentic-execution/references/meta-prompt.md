---
allowed-tools: Read, Write, Edit, Glob, Bash, Task
description: Create structured prompts aligned with the Prompt Engineering framework. Supports workflow, control-flow, and delegation prompt types.
argument-hint: <prompt_request> <prompt_type:workflow|control-flow|delegation> <difficulty:C|B|A|S>
model: opus
doc-class: threads-framework-commands
---

# Meta-Prompt v3 — Structured Command Generator

This meta-prompt creates slash commands aligned with the Prompt Engineering framework. It takes a `USER_PROMPT`, `PROMPT_TYPE`, and `PROMPT_DIFFICULTY` to generate appropriately structured command files.

**Core Principle:** A Prompt is the atomic primitive of agent execution.
Agent Execution = Interaction Model + Reflexion Model + Context.
Type (workflow, control-flow, delegation) and difficulty (C, B, A, S)
are orthogonal dimensions. This meta-prompt generates prompts that each
serve exactly one module: interaction, reflexion, or context.

## Variables

USER_PROMPT: $1
PROMPT_TYPE: $2 (workflow | control-flow | delegation)
PROMPT_DIFFICULTY: $3 (C | B | A | S)

## Output Path Detection
Determine the output directory based on project context:

```bash
# Check if in a git project (project root)
if git rev-parse --git-dir > /dev/null 2>&1; then
    # Project root present
    OUTPUT_DIR=".claude/commands"
else
    # No project root - use home directory
    OUTPUT_DIR="$HOME/.claude/commands"
fi
mkdir -p "$OUTPUT_DIR"
```

**Output Rules:**
- **Project present** (has `.git`): Save to `.claude/commands/[command-name].md`
- **No project**: Save to `~/.claude/commands/[command-name].md`

## Instructions

- **IMPORTANT: Validate PROMPT_TYPE** must be one of: `workflow`, `control-flow`, `delegation`
- **IMPORTANT: Validate PROMPT_DIFFICULTY** must be one of: `C`, `B`, `A`, `S`
- **IMPORTANT: Include sections based on difficulty tier** (see Section Inclusion Matrix below)
- **IMPORTANT: Embed control flow within Workflow** using `<loop>` blocks when PROMPT_TYPE is `control-flow`
- **IMPORTANT: Embed delegation within Instructions and Workflow** using `Task` tool patterns when PROMPT_TYPE is `delegation`
- **IMPORTANT: Use appropriate model selection** — `opus` for complex reasoning, `sonnet` for execution, `haiku` for simple operations

### Section Inclusion Matrix

Difficulty determines which optional sections to include:

| Section           | C Tier | B Tier | A Tier | S Tier |
|-------------------|--------|--------|--------|--------|
| Metadata          | ✓      | ✓      | ✓      | ✓      |
| Workflow          | ✓      | ✓      | ✓      | ✓      |
| Reflexion         | ✓      | ✓      | ✓      | ✓      |
| Report            | ✓      | ✓      | ✓      | ✓      |
| Information       |        | ✓      | ✓      | ✓      |
| Variables         |        |        | ✓      | ✓      |
| Context Map       |        |        | ✓      | ✓      |

- **C Tier**: Minimal structure — Metadata, Workflow, Reflexion, Report
- **B Tier**: + Information for system context
- **A Tier**: + Variables, Context Map
- **S Tier**: Full structure (Reflexion depth scales with complexity)

### Types of Prompts

Prompt type determines HOW the Workflow and Instructions are written:

#### `Workflow` Prompt
This is fundamental unit of prompting. A prompt for execution

Workflow serve as a common denominator of all prompts. It marks a way
to execute on a sequential basis. All prompts share this common dominator of
sequential execution

Use workflow prompt when the instruction is a simple, context invariant and
conditional invariant execution.

```markdown
## Workflow Example

1. [First step with `tool_name`]
2. [Second step]
3. [Third step]
```

#### Control Flow (`control-flow`)

Control flow elevates the `Workflow` prompt with the following:
1. Conditions
  - Condition variance lead to different execution patterns
2. Context
  - Context injection in providing interactive mechanism, boundary of operations
    and constraints
3. Verification
  - Verification and improvement loop blocks to ensure execution is done within
    the boundaries of conditions and context
  - Conditions and/or loops embedded within Workflow using `<loop>` XML blocks.

```markdown
## Workflow

1. [Setup step]
2. [Context and Conditions]

3. [context and conditional based execution]
- Conditional execution
- Context bounded execution

<loop until="[exit condition]">
- [Execution Loop block with repeated operations]
- [Process each item, can use `Task` tool]
- [Save results]
</loop>

4. [Verification]

<loop until="[all verification metrics pass]">
  - [Evaluate output against verification metrics]
  - [Apply improvement action if evaluation fails]
</loop>
```

Every `<loop>` block MUST declare:
- `max` — maximum iterations (prevents runaway)
- `until` — exit condition (what success looks like)

#### Delegation (`delegation`)

This is built upon the `Control-flow` execution domain
- As execution complexity increases - delegation is done to preserve context
window
Sub-agent delegation embedded in Instructions and Workflow using `Task` tool.

```markdown
## Instructions

- **IMPORTANT: Delegate to sub-agents** using `Task` tool with minimal context
- **IMPORTANT: Define expected I/O** for predictable results

## Workflow

1. [Gather context]
2. [Prepare task specifications]
3. Delegate via `Task` tool:
   - subagent_type: [type]
   - prompt: [minimal, focused prompt]
3b. Verify sub-agent output against I/O contract
3c. On failure: retry (max 1), skip, or abort
4. [Aggregate results]
```

### Tool Selection by Type

| Prompt Type   | Primary Tools                              |
|---------------|-------------------------------------------|
| workflow      | Read, Write, Edit, Bash, Glob             |
| control-flow  | Read, Write, Edit, Bash, Glob, Grep, Task |
| delegation    | Task, Read, Write, Edit, Bash, Glob, Grep |

### Model Selection

- **opus** — Complex reasoning, multi-step planning, architectural decisions
- **sonnet** — Detailed execution, code generation, formatting tasks
- **haiku** — Simple operations, quick lookups, speed-critical tasks

## Workflow

1. **Parse** the three input arguments:
   - Decompose USER_PROMPT into six elements:
      - Purpose
      - Context
      - Instructions
      - Execution
      - Validation Metrics
      - Improvement Mechanism
   - Validate PROMPT_TYPE against allowed values
   - Validate PROMPT_DIFFICULTY tier

2. **Research** existing commands if modifying:
   - Run `ls $OUTPUT_DIR/` to see existing commands
   - Read existing command if updating

2b. **Index Check** — read `framework-index.yaml`, verify no scope overlap with indexed docs

3. **Determine sections** based on PROMPT_DIFFICULTY:
   - C Tier: Metadata + Workflow + Reflexion + Report
   - B Tier: + Information
   - A Tier: + Variables + Context Map
   - S Tier: Full structure (Reflexion depth scales with complexity)

4. **Apply patterns** based on PROMPT_TYPE:
   - workflow: Sequential numbered steps in Workflow
   - control-flow: Embed `<loop>` blocks in Workflow
   - delegation: Embed `Task` tool patterns in Instructions and Workflow

5. **Generate** the complete command following the Specified Format

6. **Assign module tag** — infer `module: [interaction|reflexion|context]` from prompt purpose

7. **Verify** — execute Reflexion section checks, loop max 2 iterations

8. **Save** to `$OUTPUT_DIR/[command-name].md` (gated on verification passing)

## Reflexion

### Verification Metrics
- Prompt Format Match with respect to prompt type and difficulty
- If applicable - execution operates within condition and context boundaries
- No Logical Fallacy within flow of execution

### Improvement Mechanism
- If human in the loop, ask user question to clarify on any gaps, discrepancy
invoked through the verification metrics
- Type/difficulty invalid → reject with valid options, do not generate
- Section count mismatch → add missing / remove excess sections, re-verify
- Section order wrong → reorder to match Specified Format template

## Report

Output the command with analysis:

```
**Command:** [command-name]
**Type:** [workflow|control-flow|delegation] (Level [2|3|4])
**Difficulty:** [C|B|A|S] Tier
**Sections Included:** [list of included sections]
**Save to:** `$OUTPUT_DIR/[command-name].md`
**Invoke with:** `/[command-name] [args]`

[Complete file content]
```

## Specified Format

Generated commands MUST follow this structure order (include sections per difficulty tier):

```markdown
---
allowed-tools: [Tool1, Tool2, Tool3]
description: [One-line description]
argument-hint: <variable_name> (if applicable)
model: [opus|sonnet|haiku]
module: [interaction|reflexion|context]
doc-class: threads-framework-commands
---

# [Command Name]

[Purpose paragraph explaining goal and approach]

## Information
[B+ Tier only — system context, constraints, structural definitions]
[More useful for complex prompts requiring domain knowledge]

## Context Map
[A+ Tier only — file/codebase references to read for context]
- `path/to/relevant/files`
- `another/path/**/*.ts`

## Variables
[A+ Tier only — dynamic inputs]
VARIABLE_NAME: $1
ANOTHER_VARIABLE: $2

## Workflow

[Structure based on PROMPT_TYPE]

For workflow type:
1. [Step one]
2. [Step two]

For control-flow type:
1. [Setup]
<loop max="N" until="[exit condition]">
- [Repeated action]
</loop>
2. [Finalize]

For delegation type:
1. [Prepare context]
2. Delegate via `Task` tool
3. [Aggregate results]

## Reflexion
[Verification metrics + improvement mechanism]

### Verification Metrics
- [metric] → [signal type: pass/fail/graded]

### Improvement Mechanism
- [given failure signal X] → [specific adjustment action]

## Report

[Output format specification — final agent output]
```

## References
- Font Matter References

| Field           | Required | Description                                    |
|-----------------|----------|------------------------------------------------|
| `allowed-tools` | Yes      | Comma-separated list of permitted tools        |
| `description`   | Yes      | One-line description for `/` menu              |
| `argument-hint` | No       | Placeholder for required arguments             |
| `model`         | No       | `opus`, `sonnet`, or `haiku`                   |
| `module`        | Yes      | `interaction`, `reflexion`, or `context`       |
| `doc-class`     | No       | Document classification (e.g. `threads-framework-commands`) |
