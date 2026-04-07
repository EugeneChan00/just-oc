---
name: directive-creation
description: >
  Create directive artifacts (milestone, directive, subdirective) for the deep execution
  engine using the unified markdown+XML format. Use this skill whenever the user wants to
  create an executable directive, plan implementation steps, write a spec with acceptance
  criteria, define a milestone, or create any artifact for the "real dp" execution system.
  Also use when the user says "create a directive", "plan the implementation", "write
  steps for", "spec this", "write a spec", "define criteria for", or wants to formalize
  requirements into testable acceptance criteria. This replaces the old /create-issue and
  /create-spec skills — ALL new artifacts use the markdown+XML format, never YAML.
---

# Directive Creation

Create execution artifacts for the deep execution engine using the **unified markdown+XML
format**. This skill covers the full artifact lifecycle: spec (verification contract),
directive (execution plan), and the combined format.

The canonical format reference is at `references/unified-schema.md` — read it when you
need field-level detail beyond what this skill provides.

## Artifact Types

| Type | Purpose | Has Steps | Has Subdirectives |
|------|---------|-----------|-------------------|
| `enterprise` | Groups milestones | No | No (uses `<milestones>`) |
| `milestone` | Groups directives | Yes | Yes → directive files |
| `directive` | Execution plan | Yes | Yes → subdirective files |
| `subdirective` | Leaf execution | Yes | **No** (leaf node) |

## File Format

Every artifact is a single `.md` file with three layers:

1. **YAML frontmatter** — scalar metadata between `---` fences
2. **`<spec>` section** — verification contract (features, criteria, adversarial)
3. **`<directive>` section** — execution plan (scope, principle, steps)

Standalone directive files (most common) do NOT use `<spec>`/`<directive>` wrapper tags —
those are for combined schema reference documents only. Standalone files have flat
frontmatter and body content directly.

### Frontmatter (all types)

```yaml
---
id: unique-kebab-case-id
title: "Human-readable title"
goal: >
  What this artifact delivers and why it matters.
base_branch: main
directive_type: executable    # executable (default) | reference
merge_strategy: auto          # auto | agentic | none
---
```

**Directive/subdirective** additionally need:
- `cleanup: on-success` — worktree cleanup policy (`on-success | always | never`)

**Subdirective** additionally needs:
- `parent_directive: parent-id` — id of the spawning parent directive

### Spec Section (`<spec>`)

The spec defines the verification contract — what "done" means. It organizes acceptance
criteria into features, each containing criteria that the verification agent checks.

```xml
<spec>

<feature id="FEAT-01" name="Feature Name">
<description>
What this capability does. Free markdown.
</description>

<criterion id="CRIT-01" type="behavioral">
Observable, testable behavioral statement. What must be true.

<implementation>
Concrete verification scenario. "Given X, expect Y" format.
Code blocks and shell commands render verbatim.
</implementation>

<test_assertions>
  assert: "specific check description"    against: expected_value
  assert: "another check"                 against: true
</test_assertions>
</criterion>

<criterion id="CRIT-02" type="structural">
Source code structure requirement.

<implementation>
grep -rn 'pattern' src/ returns zero matches.
bun tsc --noEmit exits 0.
</implementation>
</criterion>
</feature>

<adversarial>
<strategy>
How to probe for faking, shortcuts, superficial compliance.
</strategy>
<mutations>
Inputs to mutate to confirm real implementation, not hardcoded.
</mutations>
<structural>
Source code patterns that signal quality failure.
</structural>
<test_quality>
How to verify tests assert specific meaningful values.
</test_quality>
</adversarial>

</spec>
```

**Key rules:**
- Feature IDs: `FEAT-01`, `FEAT-02`, etc.
- Criterion IDs: `CRIT-01`, `CRIT-02`, etc. (reset per feature)
- Criterion types: `behavioral | structural | performance | integration`
- Dot notation for references: `FEAT-01.CRIT-01`
- All four `<adversarial>` sub-tags are **required**
- `<implementation>` is required on every criterion

### Directive Section (`<directive>`)

The directive defines the execution plan — sequential steps with optional parallel fan-out.

```xml
<directive>

<scope>
Boundaries of the work. What is in scope, what is out.
Free markdown — use bullet lists, code blocks, whatever communicates clearly.
</scope>

<principle>
Guiding constraint for all steps. Injected into every agent dispatch prompt
as "## Principle:". Step-level principle overrides this per-step.
</principle>


<step number="1" worktree="agents/my-directive" merge_strategy="none">
<name>implement-core</name>
<profile>backend_developer</profile>
<acceptance_criteria>
- FEAT-01.CRIT-01
- FEAT-01.CRIT-02
</acceptance_criteria>
<prompt>
Full task description for the execution agent. Be specific — name files to
create/modify, functions to implement, expected behavior. The agent has no
context outside this prompt and the principle.
</prompt>
<verify>
Natural language verification strategy. NOT a shell command — a description
of what to check, expected results, and anti-patterns to detect.

**What to check:** ...
**Expected results:** ...
**Anti-patterns to detect:** ...
</verify>
<on_failure retry="2" escalate="abort"/>
</step>


<step number="2" worktree="agents/my-directive" merge_strategy="auto">
<name>parallel-fan-out</name>
<depends_on>implement-core</depends_on>
<prompt>
Preparatory work before fan-out. Can create the subdirective files
that <subdirectives> will execute.
</prompt>
<subdirectives>
  child-a.md
  child-b.md
</subdirectives>
<verify>
Verification runs AFTER all subdirectives complete and merge back.
Check the combined result.
</verify>
</step>

</directive>
```

## Step Lifecycle

Every step follows a three-phase pipeline. **Tag order = execution order:**

```
Phase 1: <prompt>          → agent executes the task
Phase 2: <subdirectives>   → fan-out children execute, then merge back
Phase 3: <verify>          → verification gate on merged result
```

Phase 2 only triggers when `<subdirectives>` is present. Without it: prompt → verify.

### Tag ordering within a step

This order is strict — declaration order reflects execution order:

1. **Metadata:** `<name>`, `<profile>`, `<depends_on>`, `<acceptance_criteria>`, `<principle>`
2. **`<prompt>`** — Phase 1
3. **`<subdirectives>`** — Phase 2 (optional)
4. **`<verify>`** — Phase 3
5. **`<on_failure .../>`** — retry/escalation policy

### Required vs optional tags

| Tag | Required | Default |
|-----|----------|---------|
| `<name>` | Yes | — |
| `<prompt>` | Yes | — |
| `<profile>` | No | `agentic_engineer` |
| `<depends_on>` | No | none |
| `<acceptance_criteria>` | No | none |
| `<principle>` | No | falls back to directive-level |
| `<subdirectives>` | No | no fan-out |
| `<verify>` | Yes* | *required with subdirectives or acceptance_criteria |
| `<on_failure>` | No | `retry="3" escalate="abort"` |

## Profiles

Choose the right profile for each step:

- `backend_developer` — implementation, API work, core logic
- `test_engineer` — tests, verification, quality review
- `agentic_engineer` — complex orchestration, multi-step reasoning (default)
- `frontend_developer` — UI work
- `solutions_architect` — design decisions, research, planning
- `researcher` — investigation, analysis
- `business_analyst` — requirements, stakeholder concerns
- `quantitative_developer` — data, algorithms, numerical work

## Writing Good Directives

### Prompts must be specific

Bad: "Implement the feature"
Good: "Create `src/exec/resolve.ts` exporting `resolveArtifactPath(ref, parentPath, roadmapDir)`.
The function resolves relative paths from the directive file's directory, not CWD."

The execution agent has no context outside the prompt and principle. Name files, functions,
expected behavior, and constraints explicitly.

### Steps build vertically

Each step builds on the previous one. A well-structured directive follows:

```
Step 1: Types/interfaces (foundation)
Step 2: Core implementation (uses types from step 1)
Step 3: Integration (wires into existing code)
Step 4: Tests (verification)
```

Aim for 2-7 steps. Single-step directives are a red flag — the work probably hasn't been
decomposed enough.

### Verify is a strategy, not a command

The `<verify>` section is a natural language verification strategy for the verification
agent. Structure it as:

```xml
<verify>
**What to check:** Concrete list of things to verify.
**Expected results:** What success looks like.
**Anti-patterns to detect:** Common failure modes to catch.
</verify>
```

### Adversarial blocks catch real issues

The adversarial section governs HOW the verifier probes, not just WHAT it checks. Write it
to catch:
- Hardcoded outputs that pass tests but don't implement real logic
- Tests that always pass regardless of implementation
- Partial fixes that update one call site but miss others
- Structural shortcuts like empty catch blocks or `any` types

### Subdirectives for parallel work

Use `<subdirectives>` when work can fan out to independent agents:
- In a **milestone**: subdirectives point to directive files
- In a **directive**: subdirectives point to subdirective files
- In a **subdirective**: `<subdirectives>` is **forbidden** (leaf node)

Subdirective files need `parent_directive` in frontmatter and must not contain
`<subdirectives>` in any step.

## File Location

All artifacts live in `.real-agents/roadmap/<milestone-folder>/`:
- Milestone: `<milestone-folder>/<milestone-id>.md`
- Directives: `<milestone-folder>/<directive-id>.md` (flat, no subfolders)
- Subdirectives: `<milestone-folder>/<subdirective-id>.md` (flat siblings)

## Process

1. **Understand the scope** — what the artifact should deliver
2. **Write the spec section** — features, criteria, adversarial block
3. **Plan steps** — decompose into sequential steps that build vertically
4. **Map criteria to steps** — each step references `FEAT-XX.CRIT-XX`
5. **Choose profiles** — match the agent persona to the work type
6. **Write verify strategies** — natural language, not shell commands
7. **Save to milestone folder** as `<id>.md`

## Common Mistakes

- **YAML format** — the old `.yaml` format is deprecated. Use markdown+XML.
- **Tags out of order** — `<verify>` before `<prompt>` misrepresents execution order
- **Missing adversarial block** — all four sub-tags are required in every spec
- **Subdirective with `<subdirectives>`** — subdirectives are leaf nodes
- **Vague prompts** — the agent has zero context outside the prompt
- **`<verify>` as a shell command** — it's a strategy description, not `bun test`
- **Wrong profile** — don't use `agentic_engineer` for writing tests
- **Using `>` for multi-line in YAML frontmatter** — use `>` only for `goal` and
  similar single-value fields; the body is free markdown, not YAML

## Example: Complete Directive with Spec

```markdown
---
id: 003-auth-middleware
title: "Implement JWT authentication middleware"
goal: >
  Add JWT token validation middleware that protects API routes.
  Tokens are validated against a shared secret with expiry checking.
base_branch: main
directive_type: executable
cleanup: on-success
merge_strategy: auto
---


<spec>

<feature id="FEAT-01" name="Token Validation">
<description>
JWT tokens are validated on every protected route request. Invalid or expired
tokens return 401 with a descriptive error body.
</description>

<criterion id="CRIT-01" type="behavioral">
Valid JWT tokens pass validation and the request proceeds to the handler.

<implementation>
Given a request with `Authorization: Bearer <valid-token>` where the token
is signed with the shared secret and not expired: the middleware calls `next()`
and the handler receives the decoded payload in `req.auth`.
</implementation>

<test_assertions>
  assert: "valid token request returns 200"           against: 200
  assert: "req.auth contains decoded payload"         against: true
</test_assertions>
</criterion>

<criterion id="CRIT-02" type="behavioral">
Expired tokens are rejected with 401.

<implementation>
Given a request with an expired JWT: the middleware returns 401 with body
`{ "error": "Token expired" }`. The handler is never called.
</implementation>
</criterion>
</feature>

<adversarial>
<strategy>
Send tokens signed with wrong secret, tokens with future nbf, tokens with
missing required claims. Verify each returns 401, not 500.
</strategy>
<mutations>
Mutate the token payload after signing (flip one bit). Confirm the middleware
detects tampering and rejects — not a blanket pass.
</mutations>
<structural>
The middleware must not hardcode a token value. It must use crypto verification,
not string comparison. Check for `jwt.verify()` or equivalent.
</structural>
<test_quality>
Tests must use real JWT tokens generated in the test, not fixture strings.
Each test must assert the specific status code and error message.
</test_quality>
</adversarial>

</spec>


<directive>

<scope>
- `src/middleware/auth.ts` — JWT validation middleware
- `src/middleware/auth.test.ts` — tests

Out of scope: token generation, refresh tokens, user database.
</scope>

<principle>
No hardcoded values. All validation must use cryptographic verification.
Tests must generate real tokens, not use fixtures.
</principle>


<step number="1" worktree="agents/003-auth-middleware" merge_strategy="none">
<name>implement-middleware</name>
<profile>backend_developer</profile>
<acceptance_criteria>
- FEAT-01.CRIT-01
- FEAT-01.CRIT-02
</acceptance_criteria>
<prompt>
Create `src/middleware/auth.ts` exporting `authMiddleware(secret: string)`.

The middleware:
1. Extracts the Bearer token from the Authorization header
2. Verifies the token signature using the provided secret
3. Checks token expiry
4. Attaches decoded payload to `req.auth`
5. Returns 401 with descriptive error for invalid/expired/missing tokens

Use the `jsonwebtoken` package. No other dependencies.
</prompt>
<verify>
**What to check:** `src/middleware/auth.ts` exports `authMiddleware`. The function
signature accepts a secret string. The implementation uses `jwt.verify()`, not
string comparison or hardcoded values.

**Anti-patterns to detect:**
- Hardcoded token validation (string comparison instead of crypto)
- Missing expiry check
- Swallowing errors with empty catch blocks
</verify>
<on_failure retry="2" escalate="abort"/>
</step>


<step number="2" worktree="agents/003-auth-middleware" merge_strategy="auto">
<name>write-tests</name>
<profile>test_engineer</profile>
<depends_on>implement-middleware</depends_on>
<acceptance_criteria>
- FEAT-01.CRIT-01
- FEAT-01.CRIT-02
</acceptance_criteria>
<prompt>
Create `src/middleware/auth.test.ts` using bun test.

Tests must generate real JWT tokens in the test using `jsonwebtoken`:
1. Valid token → 200, req.auth has payload
2. Expired token → 401, "Token expired"
3. Wrong secret → 401, "Invalid token"
4. Missing Authorization header → 401, "No token provided"
5. Malformed token string → 401

At least 5 tests. Each asserts specific status codes and response bodies.
</prompt>
<verify>
**What to check:** `bun test src/middleware/auth.test.ts` passes. Tests generate
real tokens, not fixture strings. Each test asserts a specific status code.

**Anti-patterns to detect:**
- Tests using hardcoded token strings instead of generating them
- Tests that only check "response is not null" instead of specific values
- Missing edge cases (expired, wrong secret, malformed)
</verify>
<on_failure retry="1" escalate="abort"/>
</step>

</directive>
```
