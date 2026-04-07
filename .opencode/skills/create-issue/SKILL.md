---
name: create-issue
description: >
  Create an issue YAML file for the deep execution engine. Use this skill
  whenever the user wants to create an executable issue, plan implementation
  steps, write a vertically integrated issue with sequential steps, or create
  any YAML artifact (issue, milestone, enterprise, sub-issue) for the "real dp"
  execution system. Also use when the user says "create an issue", "plan the
  implementation", "write steps for", or wants to turn a spec into executable
  steps. Issues MUST reference an existing spec — write the spec first using
  /create-spec.
---

# Create Issue

Write an issue YAML file that defines executable steps for the deep execution
engine. Issues are vertically integrated — each step builds on the previous one,
with verification gates between steps.

## When to Use

- User wants to plan implementation steps for a feature
- A spec exists and needs a paired issue with executable steps
- User says "create an issue", "plan the steps", "make this executable"
- User wants to create a milestone or enterprise YAML

## Golden Rule

**Issues depend on specs.** Always confirm a spec exists before writing an issue.
If no spec exists, invoke `/create-spec` first.

## Schema — Issue (type: issue)

```yaml
id: "<unique-id>"
type: issue
title: "<human readable title>"
spec: "<id>.spec.yaml"              # path to paired spec (sibling in milestone folder)
base_branch: "main"
cleanup: "on-success"               # on-success | always | never

scope: >
  Multi-line description of what this issue delivers.

principle: >
  Guiding constraint for the entire issue.

steps:
  - name: "<unique-step-name>"      # kebab-case, descriptive
    prompt: |                        # ALWAYS use | for multi-line prompts
      What the agent should do.
      Can include numbered sub-steps.
      Be specific — name files, functions, expected behavior.
    acceptance_criteria:             # dot-notation refs to spec criteria
      - "P01.CRIT-01"
      - "P01.CRIT-02"
    verify: "<shell command to verify>"   # optional
    profile: "backend_developer"          # optional, default: agentic_engineer
    on_failure:                           # optional
      retry: 3                            # default: 3
      escalate: "abort"                   # abort | continue | pause

  - name: "<next-step>"
    prompt: |
      Build on the previous step's work...
    depends_on:                      # steps this depends on
      - "<previous-step-name>"
    acceptance_criteria:
      - "P01.CRIT-02"
    verify: "bun test src/module/"
    profile: "test_engineer"
```

## Schema — Milestone (type: milestone)

```yaml
id: "<milestone-slug>"
type: milestone
title: "<human readable title>"
base_branch: "main"
issues:                              # child issue filenames (flat siblings)
  - "001-feature-a.yaml"
  - "002-feature-b.yaml"
```

## Schema — Enterprise (type: enterprise)

```yaml
id: "<enterprise-id>"
type: enterprise
title: "<human readable title>"
milestones:                          # paths to milestone YAMLs
  - "m01-refactor/m01-refactor.yaml"
  - "m02-features/m02-features.yaml"
```

## Rules for Writing Steps

1. **Steps are vertically integrated.** Each step builds on the previous one.
   Step 1 creates types, step 2 uses those types, step 3 tests them, etc.

2. **Multiple steps per issue.** Single-step issues are a red flag — they
   usually mean the work hasn't been decomposed enough. Aim for 3-7 steps.

3. **Use `|` block scalar for prompts.** Never use `>` folded scalar for
   prompts containing code, colons, or special characters — YAML will
   misparse them.

4. **Prompts are specific.** Name the files to create/modify, the functions
   to implement, the expected behavior. Vague prompts like "implement the
   feature" produce vague results.

5. **acceptance_criteria reference the spec.** Use dot notation: P01.CRIT-01,
   P02.FEAT-03. These tell the verification agent what to check.

6. **depends_on creates ordering.** Steps execute sequentially by default,
   but depends_on makes the dependency explicit for documentation.

7. **verify is a shell command.** The runner executes this after the step
   to quick-check results. Common: `bun tsc --noEmit`, `bun test`, `ls`.

8. **profile selects the agent.** Use the right profile for the job:
   - `backend_developer` — implementation, API work
   - `test_engineer` — tests, verification, quality review
   - `agentic_engineer` — complex orchestration (default)
   - `frontend_developer` — UI work
   - `solutions_architect` — design decisions

9. **File naming:** `<id>.yaml` as sibling to the spec in the milestone folder.

10. **File location:** `.real-agents/roadmap/<milestone-folder>/<id>.yaml`

## Step Decomposition Pattern

A well-structured issue follows this pattern:

```
Step 1: Create types/interfaces (foundation)
Step 2: Implement core logic (uses types from step 1)
Step 3: Wire into existing code (integration)
Step 4: Write tests (verification)
Step 5: Run tests + review (quality gate)
```

Not every issue needs all five, but the principle is: **build up, then verify.**

## Process

1. **Confirm spec exists** — check the milestone folder for `<id>.spec.yaml`
2. **Read the spec** — understand phases, features, criteria
3. **Plan steps** — decompose the work into sequential steps that build on each other
4. **Map criteria to steps** — each step should cover specific P0X.CRIT-XX refs
5. **Choose profiles** — backend_developer for impl, test_engineer for tests
6. **Write verify commands** — quick-check shell commands for each step
7. **Save to milestone folder** as `<id>.yaml`

## Common Mistakes

- **Single-step issues** — decompose further. If it's truly one step, it's
  probably a sub-issue, not an issue.
- **Using `>` for prompts** — use `|` instead. Folded scalars break with
  code content.
- **Vague prompts** — "implement the feature" vs "Create src/exec/resolve.ts
  with resolveArtifactPath(ref, parentYamlPath, roadmapDir) that..."
- **Missing acceptance_criteria** — every step should reference at least one
  spec criterion.
- **Wrong profile** — don't use agentic_engineer for writing tests, use
  test_engineer.
- **No depends_on** — makes the dependency chain implicit and harder to debug.

## Example

A well-written issue with 3 steps:

```yaml
id: "dogfood-string-utils"
type: issue
title: "Create string utils module with capitalize and slugify"
spec: "dogfood-string-utils.spec.yaml"
base_branch: "main"
cleanup: "on-success"

scope: "Create string-utils.ts with capitalize and slugify, fully tested."
principle: "Pure functions. No external deps. Tests must pass."

steps:
  - name: "implement-functions"
    prompt: |
      Create /tmp/dogfood-output/string-utils.ts with two exported functions.

      capitalize(str) - capitalizes the first letter of each word.
      slugify(str) - converts to lowercase URL-safe slug with hyphens.
    acceptance_criteria:
      - "P01.CRIT-01"
      - "P01.CRIT-02"
    verify: "ls /tmp/dogfood-output/string-utils.ts"
    profile: "backend_developer"

  - name: "write-tests"
    prompt: |
      Create /tmp/dogfood-output/string-utils.test.ts using bun test.
      At least 4 tests per function with specific value assertions.
    depends_on:
      - "implement-functions"
    acceptance_criteria:
      - "P01.CRIT-01"
      - "P01.CRIT-02"
    verify: "bun test /tmp/dogfood-output/string-utils.test.ts"
    profile: "test_engineer"

  - name: "verify-quality"
    prompt: |
      Review the implementation. Run tests. Add edge case tests.
      Confirm all pass.
    depends_on:
      - "write-tests"
    acceptance_criteria:
      - "P01.CRIT-01"
      - "P01.CRIT-02"
    verify: "bun test /tmp/dogfood-output/string-utils.test.ts"
    profile: "test_engineer"
```
