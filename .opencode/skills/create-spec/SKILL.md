---
name: create-spec
description: >
  Create a spec YAML file for the deep execution engine. Use this skill whenever
  the user wants to define acceptance criteria, plan a feature's verification
  requirements, write a spec for an issue, or create a new spec.yaml file. Also
  use when the user says "spec this", "write a spec", "define criteria for",
  or describes what a feature should do and needs it formalized into testable
  acceptance criteria. Specs are always written BEFORE issues.
---

# Create Spec

Write a spec YAML file that defines phases, features, acceptance criteria, and
adversarial verification rules. Specs are the verification contract — they define
what "done" means for an issue.

## When to Use

- User wants to define what a feature should do before implementation
- User describes requirements that need to be formalized
- A new issue needs a paired spec
- User says "spec this", "write a spec", "define acceptance criteria"

## Schema

Every spec follows this structure. Do not deviate.

```yaml
# Required comment header
# Spec: <Human-readable name>
# Conforms to .real-agents/docs/issue-creation/spec_schema.yaml

id: "<issue-id>"                    # mirrors the paired issue ID
milestone: "<milestone-slug>"       # which milestone this belongs to
goal: >
  One paragraph describing the high-level outcome this spec validates.

phases:
  P01:                              # Phase key: P01, P02, P03...
    name: "<short phase name>"
    description: >
      What this phase covers and why it exists as a group.

    features:
      FEAT-01:
        description: "<what this feature does, behaviorally>"
      FEAT-02:
        description: "<another feature>"

    acceptance_criteria:
      CRIT-01:
        description: >
          Observable, testable behavioral statement.
          What must be true — not structural properties.
        assertion:
          type: "behavioral | structural | performance | integration"
          check: >
            Concrete verification instruction.
            "Given X, expect Y" format.
        # Optional but encouraged:
        test_assertions:
          - assert: "<specific check>"
            against: "<expected value>"
        example:                    # Optional
          input: "<concrete input>"
          expected: "<concrete output>"

      CRIT-02:
        description: "..."
        assertion:
          type: behavioral
          check: "..."

  P02:                              # Additional phases as needed
    name: "..."
    # ... same structure

adversarial:                        # Required — guides the verifier
  strategy: >
    How to probe for faking, shortcuts, superficial compliance.
  mutations: >
    How to mutate inputs to confirm dynamic behavior.
  structural: >
    What to look for in source code.
  test_quality: >
    How to verify tests are meaningful.
```

## Rules

1. **Specs come BEFORE issues.** Always write the spec first, then the issue
   references it.

2. **Phase numbering** — P01, P02, P03. Criteria numbering resets per phase.
   Full reference is always phase-qualified: P01.CRIT-01, P02.CRIT-01.

3. **Criteria must be testable.** "The function works correctly" is not a
   criterion. "capitalize('hello world') returns 'Hello World'" is.

4. **Use `|` block scalar for multi-line text** in YAML to avoid parsing
   issues with colons and special characters. For single-line values,
   use quoted strings.

5. **test_assertions are concrete.** Each one has an `assert` (what to check)
   and `against` (expected value). These guide the verification agent.

6. **adversarial block is required.** This tells the verification agent how
   to probe beyond surface-level compliance.

7. **Features are behavioral descriptions**, not implementation details.
   "JWT token validation with expiry checking" not "Add validateToken()
   function to auth.ts".

8. **File naming convention:** `<id>.spec.yaml` as a sibling to the issue YAML
   in the milestone folder.

9. **File location:** `.real-agents/roadmap/<milestone-folder>/<id>.spec.yaml`

## Process

1. **Understand the scope** — ask the user what the feature should do
2. **Identify phases** — group related features and criteria logically
3. **Write concrete criteria** — each with assertion type and check instructions
4. **Add test_assertions** — specific input/output pairs where possible
5. **Write adversarial block** — how to catch cheating implementations
6. **Save to the milestone folder** as `<id>.spec.yaml`

## Example

A well-written spec for a config module:

```yaml
id: "001-config-folder"
milestone: "m02-platform-features"
goal: >
  Migrate from single config.yaml to config/ directory with
  config.yaml and prompts/ subdirectory.

phases:
  P01:
    name: "Config Directory Migration"
    description: >
      Move config.yaml into config/ subdirectory. Update discovery
      code to resolve new path.

    features:
      FEAT-01:
        description: "config/ directory with config.yaml moved inside"
      FEAT-02:
        description: "ProjectConfig gains configDir and promptsDir fields"

    acceptance_criteria:
      CRIT-01:
        description: >
          loadProjectConfig() returns ProjectConfig where configDir
          points to .real-agents/config/ and promptsDir points to
          .real-agents/config/prompts/.
        assertion:
          type: behavioral
          check: >
            Call loadProjectConfig(). Verify configDir and promptsDir
            are correct absolute paths.
        test_assertions:
          - assert: "config.configDir ends with .real-agents/config"
            against: "true"

adversarial:
  strategy: "Verify code reads from config/config.yaml not root config.yaml"
  mutations: "Test with both paths present, config/ missing, empty YAML"
  structural: "Must not hardcode config.yaml at .real-agents/ root"
  test_quality: "Tests must use real directories, not mock fs"
```
